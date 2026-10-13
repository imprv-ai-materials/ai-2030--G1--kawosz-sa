"""Kalkulator wizyt dla sprzedaży: próg, lista biur do odwiedzenia, zysk i krzywa wartości dla dowolnych s, V, C
i budżetu (ui/, strona /wizyty, przez GET /api/wizyty).

Rachunek jak w krzywa_wartosci.py (docs/prog.md), tylko z założeniami z suwaków zamiast z zalozenia.yaml:
- próg: wizyta się opłaca, gdy p × s × V > C, czyli p ≥ C / (s × V);
- lista: dzisiejsze biura (cechy_aktualne z bazy nocnego potoku, p z aktywnego modelu) z p ≥ próg, od najwyższego
  p, najwyżej budżet, z trzema powodami ryzyka biura (radar/powody.py, te same co na liście poniedziałkowej);
- zysk według modelu: suma p × s × V − C po biurach z listy (dzisiejszych odejść jeszcze nie znamy);
- zysk na historii: ta sama reguła (p ≥ próg, najwyżej budżet) na snapszotach testowych modelu z faktycznymi
  odejściami, średnio na snapszot, czyli na kwartał (plan_w_scenariuszu);
- krzywa: dla progów 0,01–0,99 zysk według modelu na dzisiejszych biurach i średni zysk na historii
  (krzywa_wartosci na każdym snapszocie), bez limitu budżetu.

Grupa kontrolna (udział listy, domyślnie 0): część biur z listy losowo nie dostaje wizyty, żeby za kwartał zmierzyć
skuteczność z porównania odejść: s = 1 − odejścia z wizytą / odejścia bez wizyty. Los biura jest ten sam co
w poniedziałkowej liście opiekunów (retention_bc/kontrola.py: stały dla biura w kwartale), a zapisem eksperymentu
jest tabela lista_wizyt. Kalkulator pokazuje koszt i dokładność pomiaru: metodą delta dla s z odsetka odejść biur
z listy w historii i założonego s. W historii były już kontakty retencyjne (ok. 60–80 na kwartał w CRM), więc ten
odsetek jest raczej zaniżony.

Suwaki startują z wartości w retention_bc/zalozenia.yaml. Zakres suwaka: przy parametrze z przedziałem od połowy
dolnej do 1,5 × górnej granicy przedziału (s najwyżej 1), bez przedziału od 0 do 2,5 × wartości.
"""

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from api.adapters.duckdb_conn import DB_PATH, connect
from api.ai.churn_model import aktywny
from api.contexts_boundaries.retention_bc.kontrola import kwartal as kwartal_dnia
from api.contexts_boundaries.retention_bc.kontrola import w_kontroli
from api.contexts_boundaries.retention_bc.radar.powody import powody
from api.contexts_boundaries.retention_bc.prog.krzywa_wartosci import (
    POCZATEK_TESTU,
    PROGI,
    SNAPSZOT,
    ZALOZENIA,
    krzywa_wartosci,
    plan_w_scenariuszu,
    zalozenia,
)

KROKI = {"V": 100, "C": 10, "s": 0.01, "budzet_wizyt": 1}
KWARTALY_POMIARU = (1, 4, 8)  # dokładność s po kwartale, roku i dwóch latach eksperymentu
Z_90 = 1.645  # 90% przedział, jak w docs/prog.md


def _zakres(klucz: str, wartosc: float, przedzial: list | None) -> tuple[float, float]:
    if przedzial:
        dol, gora = przedzial[0] / 2, przedzial[1] * 1.5
    else:
        dol, gora = 0, wartosc * 2.5
    if klucz == "s":
        dol, gora = max(dol, KROKI["s"]), min(gora, 1)
    krok = KROKI[klucz]
    return round(math.floor(round(dol / krok, 6)) * krok, 2), round(math.ceil(round(gora / krok, 6)) * krok, 2)


def suwaki() -> list[dict]:
    """V, C, s i budżet z zalozenia.yaml: wartość startowa, zakres suwaka i opis źródła liczby."""
    par = yaml.safe_load(ZALOZENIA.read_text())["parametry"]
    wynik = []
    for klucz, krok in KROKI.items():
        p = par[klucz]
        dol, gora = _zakres(klucz, p["wartosc"], p["przedzial"])
        wynik.append({
            "klucz": klucz,
            "opis": p["opis"],
            "jednostka": p["jednostka"],
            "wartosc": p["wartosc"],
            "przedzial": p["przedzial"],
            "min": dol,
            "max": gora,
            "krok": krok,
            "wlasciciel": p["wlasciciel"],
            "rachunek": p.get("rachunek"),
            "otwarte": p.get("otwarte", []),
        })
    return wynik


def przedzial_s(r_C: float | None, s: float, n_kontrola: int, n_wizyty: int) -> dict | None:
    """Połowa 90% przedziału zmierzonego s po KWARTALY_POMIARU kwartałach z taką samą listą co kwartał. Metoda delta
    dla s = 1 − r_T / r_C, gdzie r_C to odsetek odejść bez wizyty, a r_T = r_C × (1 − s)."""
    if r_C is None or not 0 < r_C < 1 or not 0 < s < 1 or n_kontrola == 0 or n_wizyty == 0:
        return None
    r_T = r_C * (1 - s)
    wariancja = (r_T / r_C) ** 2 * ((1 - r_C) / (n_kontrola * r_C) + (1 - r_T) / (n_wizyty * r_T))
    return {str(q): Z_90 * math.sqrt(wariancja / q) for q in KWARTALY_POMIARU}


def policz(
    dzis: pd.DataFrame,
    historia: pd.DataFrame,
    s: float,
    V: float,
    C: float,
    budzet: int,
    kontrola: float = 0.0,
    kwartal: str = "",
) -> dict:
    """Wynik kalkulatora. dzis: biura z p (id_biura, nazwa, miasto, opiekun, p); historia: snapszoty testowe z p
    i faktycznym odejściem (t0, odejdzie_90d, p). kontrola: udział listy losowo bez wizyty w kwartale `kwartal`."""
    prog = C / (s * V)
    nad = dzis[dzis["p"] >= prog].sort_values("p", ascending=False, kind="stable")
    lista = nad.head(budzet).assign(wartosc_wizyty=lambda d: d["p"] * s * V - C)
    bez_wizyty = lista["id_biura"].map(lambda b: w_kontroli(b, kwartal, kontrola)).astype(bool)
    lista["grupa"] = np.where(bez_wizyty, "kontrola", "wizyta")
    wizyty = lista[lista["grupa"] == "wizyta"]
    plan = plan_w_scenariuszu(historia, historia["p"], prog, {"C": C, "budzet_wizyt": budzet}, s, V)

    # odsetek odejść biur z listy w historii: tyle odchodzi bez wizyty, czyli w grupie kontrolnej
    listy = [
        g[g["p"] >= prog].sort_values("p", ascending=False, kind="stable").head(budzet)
        for _, g in historia.groupby("t0")
    ]
    na_liscie = sum(len(g) for g in listy)
    r_C = sum(int(g["odejdzie_90d"].sum()) for g in listy) / na_liscie if na_liscie else None

    krzywe = [
        krzywa_wartosci(g["p"], g["odejdzie_90d"].astype(int), PROGI, s, V, C) for _, g in historia.groupby("t0")
    ]
    srednio = pd.concat(krzywe).groupby("prog")[["wizyty", "zysk"]].mean()
    p = dzis["p"]
    krzywa = [
        {
            "prog": float(t),
            "wizyty_dzis": int((p >= t).sum()),
            "zysk_oczekiwany_dzis": float((p[p >= t] * s * V - C).sum()),
            "wizyty_historia": float(srednio.loc[t, "wizyty"]),
            "zysk_historia": float(srednio.loc[t, "zysk"]),
        }
        for t in PROGI
    ]
    t0 = pd.to_datetime(historia["t0"])
    return {
        "zalozenia": {"s": s, "V": V, "C": C, "budzet_wizyt": budzet},
        "prog": prog,
        "zysk_trafionej": s * V - C,
        "biura_dzis": len(dzis),
        "max_p": float(p.max()),
        "nad_progiem": len(nad),
        "zysk_oczekiwany_nad_progiem": float((nad["p"] * s * V - C).sum()),
        "lista": lista[["id_biura", "nazwa", "miasto", "opiekun", "p", "wartosc_wizyty", "grupa", "powody"]].to_dict(
            "records"
        ),
        "zysk_oczekiwany": float(wizyty["wartosc_wizyty"].sum()),
        "kontrola": {
            "udzial": kontrola,
            "kwartal": kwartal,
            "biura": int(bez_wizyty.sum()),
            "koszt": float(lista.loc[lista["grupa"] == "kontrola", "wartosc_wizyty"].sum()),
            "odejscia_bez_wizyty": r_C,
            "przedzial_90": przedzial_s(r_C, s, int(bez_wizyty.sum()), len(wizyty)),
        },
        "historia": {
            "snapszoty": len(krzywe),
            "od": f"{t0.min():%Y-%m-%d}",
            "do": f"{t0.max():%Y-%m-%d}",
            "wizyty": plan["wizyty"],
            "zysk": plan["zysk"],
        },
        "krzywa": krzywa,
    }


@lru_cache(maxsize=1)
def _wczytaj(baza: Path, zmiana_bazy: float, zmiana_historii: float, wersja: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Dzisiejsze biura z bazy nocnego potoku (cechy_aktualne) i snapszoty testowe z kawosz.duckdb (cechy_treningowe
    są danymi modelu, nocny potok ich nie ma), oba z p aktywnego modelu. Klucz cache: baza, czasy zmian obu baz
    (nocny potok odświeża cechy_aktualne) i wersja modelu z current.yaml."""
    con = connect(read_only=True, db_path=baza)
    try:
        dzis = con.execute(
            """
            SELECT a.*, b.nazwa, o.imie_nazwisko AS opiekun
            FROM cechy_aktualne a
            LEFT JOIN crm_biura b USING (id_biura)
            LEFT JOIN crm_opiekunowie o ON o.am_id = a.am_id
            """
        ).df()
    finally:
        con.close()
    con = connect(read_only=True, db_path=DB_PATH)
    try:
        historia = con.execute(
            "SELECT * FROM cechy_treningowe WHERE t0 BETWEEN ? AND ?", [POCZATEK_TESTU.date(), SNAPSZOT.date()]
        ).df()
    finally:
        con.close()
    assert dzis["id_biura"].is_unique, "cechy_aktualne mają mieć jeden wiersz na biuro"
    dzis["t0"], historia["t0"] = pd.to_datetime(dzis["t0"]), pd.to_datetime(historia["t0"])
    model = aktywny.wczytaj()
    assert model.wersja == wersja
    dzis["p"], historia["p"] = model.predict_proba(dzis), model.predict_proba(historia)
    # powody nie zależą od suwaków, więc liczymy je raz dla wszystkich biur (tak samo jak lista poniedziałkowa)
    dzis["powody"] = powody(model, dzis, dzis)
    return dzis, historia


def dane(
    baza: Path, s: float | None, V: float | None, C: float | None, budzet: int | None, kontrola: float = 0.0
) -> dict:
    """Suwaki, wynik kalkulatora (brakujące parametry z zalozenia.yaml) i skąd są dane."""
    sw = suwaki()
    start = {w["klucz"]: w["wartosc"] for w in sw}
    wersja = aktywny.wersja()
    dzis, historia = _wczytaj(baza, baza.stat().st_mtime, DB_PATH.stat().st_mtime, wersja)
    t0 = dzis["t0"].max()
    wynik = policz(
        dzis,
        historia,
        start["s"] if s is None else s,
        start["V"] if V is None else V,
        start["C"] if C is None else C,
        start["budzet_wizyt"] if budzet is None else budzet,
        kontrola,
        kwartal_dnia(t0.date()),
    )
    return {
        "suwaki": sw,
        "kontrola_startowa": zalozenia()["udzial_kontroli"],
        "model": wersja,
        "dzis": f"{t0:%Y-%m-%d}",
        "baza": str(baza),
        **wynik,
    }
