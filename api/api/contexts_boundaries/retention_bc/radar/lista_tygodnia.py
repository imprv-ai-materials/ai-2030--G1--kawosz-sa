"""Poniedziałkowa lista wizyt dla każdego opiekuna: biuro, ryzyko odejścia w 90 dni, wartość wizyty i trzy powody
ryzyka prostym językiem (radar/powody.py).

Reguła jak w kalkulatorze wizyt (docs/prog.md): wizyta się opłaca, gdy p ≥ C / (s × V), a jest warta p × s × V − C.
p to prognoza aktywnego modelu churnu (api/ai/churn_model/aktywny.py: wersja z current.yaml przez kontrakt
ChurnModel) na cechach z cechy_aktualne, które nocny potok odświeża o 3:00. s, V, C i liczba wizyt opiekuna na
kwartał pochodzą z retention_bc/zalozenia.yaml.

Na liście opiekuna są jego biura (am_id w cechy_aktualne) z p ≥ próg, od najwyższego p:
- bez biur po kontakcie retencyjnym (wizyta albo telefon z crm_kontakty_am.czy_retencyjna) w OKNO_PO_KONTAKCIE
  przed dniem listy: rabat trwa 3 miesiące, a wizyta działa w 90-dniowym oknie etykiety, więc druga by nic nie dała;
- najwyżej wizyty_na_opiekuna (na kwartał) minus wizyty retencyjne u jego biur od początku kwartału.
Lista to kolejka na kwartał, odświeżana co poniedziałek, a nie plan na tydzień: biuro po wizycie z niej znika.

Grupa kontrolna (udzial_kontroli z zalozenia.yaml): biuro z listy, którego los w kwartale wypadł poniżej udziału
(retention_bc/kontrola.py), zostaje na liście z grupą „kontrola”: bez wizyty i bez rabatu do końca kwartału. Nie
zajmuje miejsca opiekuna, a do kontroli trafiają tylko biura z zakresu p, w którym opiekun jeszcze jeździ (te
poniżej ostatniej wizyty i tak by jej nie dostały). Los jest stały w kwartale, więc biuro z kontroli zostaje w niej
co tydzień. Za kwartał: s = 1 − odsetek odejść z wizytą / odsetek odejść w kontroli, liczony od pierwszego
pojawienia się biura w lista_wizyt w kwartale.

Wynik: tabela lista_wizyt, jeden zestaw wierszy na tydzień (ponowny przebieg nadpisuje tydzień). Co poniedziałek
o 6:00 liczy ją Inngest (api/api/inngest_app.py, po nocy i PSI). Ręcznie, lista jednego opiekuna bez zapisu:

    PYTHONPATH=api poetry run python -m api.contexts_boundaries.retention_bc.radar.lista_tygodnia 2026-10-05 \\
        --opiekun 2
"""

import argparse
from datetime import date, timedelta
from pathlib import Path

import duckdb
import inngest
import pandas as pd

from api.adapters.duckdb_conn import connect
from api.ai.churn_model import aktywny
from api.contexts_boundaries.retention_bc.kontrola import kwartal, w_kontroli
from api.contexts_boundaries.retention_bc.prog.krzywa_wartosci import zalozenia
from api.contexts_boundaries.retention_bc.radar.powody import LICZBA_POWODOW, powody

OKNO_PO_KONTAKCIE = timedelta(days=90)
# Cechy z nocy sprzed ponad tygodnia: lista z poprzedniego poniedziałku byłaby tak samo dobra, więc przerywamy.
MAX_WIEK_CECH = timedelta(days=7)
TABELA = "lista_wizyt"
KOLUMNY = ["am_id", "opiekun", "lp", "id_biura", "nazwa", "miasto", "p", "wartosc_wizyty", "grupa"]
POWODY = [f"powod_{i}" for i in range(1, LICZBA_POWODOW + 1)]


def poczatek_kwartalu(d: date) -> date:
    return date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)


def lista_tygodnia(
    biura: pd.DataFrame,
    opiekunowie: pd.DataFrame,
    kontakty: pd.DataFrame,
    tydzien: date,
    s: float,
    V: float,
    C: float,
    limit: int,
    udzial: float = 0.0,
) -> tuple[pd.DataFrame, list[dict]]:
    """Listy wszystkich opiekunów (KOLUMNY, lp od 1 u każdego, po kolei wizyty i kontrola) i podsumowanie.

    biura: id_biura, nazwa, miasto, am_id, p; opiekunowie: am_id, imie_nazwisko; kontakty: id_biura, data, typ,
    czy_retencyjna. Liczą się tylko kontakty sprzed dnia listy. udzial: grupa kontrolna (0: bez kontroli)."""
    kw = kwartal(tydzien)
    prog = C / (s * V)
    dzien = pd.Timestamp(tydzien)
    k = kontakty.assign(data=pd.to_datetime(kontakty["data"]))
    k = k[k["czy_retencyjna"].astype(bool) & (k["data"] < dzien)]
    po_kontakcie = set(k.loc[k["data"] >= dzien - OKNO_PO_KONTAKCIE, "id_biura"])
    w_kwartale = k[(k["typ"] == "wizyta") & (k["data"] >= pd.Timestamp(poczatek_kwartalu(tydzien)))]
    wizyty_opiekunow = w_kwartale.merge(biura[["id_biura", "am_id"]], on="id_biura")["am_id"].value_counts()

    nad = biura[biura["p"] >= prog].sort_values("p", ascending=False, kind="stable")
    listy, podsumowanie = [], []
    for o in opiekunowie.sort_values("am_id").itertuples():
        jego = nad[nad["am_id"] == o.am_id]
        pominiete = jego["id_biura"].isin(po_kontakcie)
        zrobione = int(wizyty_opiekunow.get(o.am_id, 0))
        miejsca = max(0, limit - zrobione)
        kandydaci = jego[~pominiete]
        kontrola = kandydaci["id_biura"].map(lambda b: w_kontroli(b, kw, udzial)).astype(bool)
        wizyty_przed = (~kontrola).cumsum() - (~kontrola)  # ile wizyt jest na liście wyżej
        lista = kandydaci[wizyty_przed < miejsca].assign(grupa=kontrola.map({True: "kontrola", False: "wizyta"}))
        listy.append(
            lista.assign(opiekun=o.imie_nazwisko, lp=range(1, len(lista) + 1), wartosc_wizyty=lista["p"] * s * V - C)
        )
        podsumowanie.append({
            "am_id": int(o.am_id),
            "opiekun": o.imie_nazwisko,
            "nad_progiem": len(jego),
            "pominiete_po_kontakcie": int(pominiete.sum()),
            "wizyty_w_kwartale": zrobione,
            "limit": miejsca,
            "na_liscie": int((lista["grupa"] == "wizyta").sum()),
            "w_kontroli": int((lista["grupa"] == "kontrola").sum()),
        })
    return pd.concat(listy)[KOLUMNY].reset_index(drop=True), podsumowanie


def policz(con: duckdb.DuckDBPyConnection, tydzien: date) -> tuple[pd.DataFrame, dict]:
    """Lista na tydzień z bazy: cechy_aktualne, p aktywnego modelu, kontakty CRM i założenia. Zwraca wiersze do
    lista_wizyt (z modelem, t0 cech, założeniami i powodami) i podsumowanie."""
    biura = con.execute("SELECT a.*, b.nazwa FROM cechy_aktualne a LEFT JOIN crm_biura b USING (id_biura)").df()
    t0 = pd.Timestamp(biura["t0"].max()).date()
    if t0 > tydzien:
        raise inngest.NonRetriableError(
            f"cechy_aktualne są na {t0}, czyli po dniu listy {tydzien}: tabela trzyma tylko ostatni stan, więc listy "
            "na wcześniejszy tydzień nie da się odtworzyć"
        )
    if tydzien - t0 > MAX_WIEK_CECH:
        raise inngest.NonRetriableError(
            f"cechy_aktualne są na {t0}, starsze o ponad {MAX_WIEK_CECH.days} dni od dnia listy {tydzien}: "
            "sprawdź nocny potok"
        )
    opiekunowie = con.execute("SELECT am_id, imie_nazwisko FROM crm_opiekunowie").df()
    kontakty = con.execute(
        "SELECT id_biura, data, typ, czy_retencyjna FROM crm_kontakty_am WHERE czy_retencyjna AND data < ?",
        [tydzien],
    ).df()
    model = aktywny.wczytaj()
    biura["p"] = model.predict_proba(biura)
    z = zalozenia()
    s, V, C, udzial = z["s"], z["V"], z["C"], z["udzial_kontroli"]
    wiersze, podsumowanie = lista_tygodnia(
        biura, opiekunowie, kontakty, tydzien, s, V, C, z["wizyty_na_opiekuna"], udzial
    )
    # powody liczone na cechach biur z listy, a typowe biuro to wszystkie dzisiejsze biura
    cechy_listy = biura.set_index("id_biura").loc[wiersze["id_biura"]].reset_index()
    opisy = pd.DataFrame(
        [(p + [None] * LICZBA_POWODOW)[:LICZBA_POWODOW] for p in powody(model, cechy_listy, biura)],
        columns=POWODY,
        dtype=object,
    )
    wiersze = pd.concat([wiersze, opisy], axis=1).assign(
        tydzien=tydzien,
        kwartal=kwartal(tydzien),
        model=model.wersja,
        t0_cech=t0,
        s=s,
        V=V,
        C=C,
        prog=C / (s * V),
        udzial_kontroli=udzial,
    )
    return wiersze, {
        "tydzien": str(tydzien),
        "kwartal": kwartal(tydzien),
        "udzial_kontroli": udzial,
        "t0_cech": str(t0),
        "model": model.wersja,
        "prog": C / (s * V),
        "opiekunowie": podsumowanie,
    }


def zapisz(con: duckdb.DuckDBPyConnection, tydzien: date, wiersze: pd.DataFrame) -> None:
    """Lista tygodnia do lista_wizyt w miejsce poprzedniego zapisu tego tygodnia."""
    con.execute(
        f"""CREATE TABLE IF NOT EXISTS {TABELA} (
            tydzien DATE, kwartal VARCHAR, am_id BIGINT, opiekun VARCHAR, lp INTEGER, id_biura BIGINT,
            nazwa VARCHAR, miasto VARCHAR, p DOUBLE, wartosc_wizyty DOUBLE, grupa VARCHAR,
            powod_1 VARCHAR, powod_2 VARCHAR, powod_3 VARCHAR, model VARCHAR, t0_cech DATE,
            s DOUBLE, V DOUBLE, C DOUBLE, prog DOUBLE, udzial_kontroli DOUBLE
        )"""
    )
    kolumny = ", ".join(
        ["tydzien", "kwartal", *KOLUMNY, *POWODY, "model", "t0_cech", "s", "V", "C", "prog", "udzial_kontroli"]
    )
    con.register("lista_tygodnia", wiersze)
    con.execute("BEGIN")
    try:
        con.execute(f"DELETE FROM {TABELA} WHERE tydzien = ?", [tydzien])
        con.execute(f"INSERT INTO {TABELA} ({kolumny}) SELECT {kolumny} FROM lista_tygodnia")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.unregister("lista_tygodnia")


def przygotuj(baza: Path, tydzien: date) -> dict:
    """Lista na tydzień policzona i zapisana w lista_wizyt; podsumowanie na opiekuna (wynik kroku Inngest)."""
    con = connect(read_only=False, db_path=baza)
    try:
        wiersze, wynik = policz(con, tydzien)
        zapisz(con, tydzien, wiersze)
    finally:
        con.close()
    return wynik


def _biura(n: int) -> str:
    """1 biuro, 2–4 biura, 5+ biur (też 12–14)."""
    if n == 1:
        return "1 biuro"
    return f"{n} biura" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else f"{n} biur"


def _drukuj(wiersze: pd.DataFrame, wynik: dict, o: dict) -> None:
    print(f"\n{o['opiekun']}: lista na poniedziałek {wynik['tydzien']}")
    print(
        f"{_biura(o['na_liscie'])} do odwiedzenia, {o['w_kontroli']} w grupie kontrolnej; nad progiem "
        f"{o['nad_progiem']}, pominięte po kontakcie retencyjnym {o['pominiete_po_kontakcie']}, wizyt retencyjnych "
        f"w kwartale {o['wizyty_w_kwartale']}, zostało miejsc {o['limit']}"
    )
    prog = f"{wynik['prog']:.3f}".replace(".", ",")
    udzial = f"{wynik['udzial_kontroli']:.0%}"
    print(f"(model {wynik['model']}, cechy na {wynik['t0_cech']}, próg p ≥ {prog}, kontrola {udzial})")
    lista = wiersze[wiersze["am_id"] == o["am_id"]]
    for grupa, naglowek in (("wizyta", "Do odwiedzenia"), ("kontrola", "Grupa kontrolna: bez wizyty i bez rabatu")):
        biura = lista[lista["grupa"] == grupa]
        if biura.empty:
            continue
        print(f"\n{naglowek}\n{'Lp.':>3}  {'Biuro':<48} {'Miasto':<12} {'Ryzyko':>7} {'Wartość wizyty':>15}")
        for lp, w in enumerate(biura.itertuples(), 1):
            biuro = f"{w.nazwa} (#{w.id_biura})"
            ryzyko = f"{w.p:.1%}".replace(".", ",")
            wartosc = f"{w.wartosc_wizyty:,.0f} zł".replace(",", " ")
            print(f"{lp:>3}  {biuro:<48} {w.miasto:<12} {ryzyko:>7} {wartosc:>15}")
            print(f"{'':>5}powody: {'; '.join(p for p in (w.powod_1, w.powod_2, w.powod_3) if p) or 'brak'}")


def main() -> None:
    from api.data_platform.noc import Ustawienia

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tydzien", type=date.fromisoformat, help="dzień listy (poniedziałek) RRRR-MM-DD")
    parser.add_argument("--opiekun", type=int, help="am_id opiekuna; bez niego wszyscy")
    parser.add_argument("--zapisz", action="store_true", help="zapisz listę w lista_wizyt, jak zadanie Inngest")
    args = parser.parse_args()
    baza = Ustawienia.z_env().baza
    if args.zapisz:
        przygotuj(baza, args.tydzien)
    con = connect(read_only=True, db_path=baza)
    try:
        wiersze, wynik = policz(con, args.tydzien)
    finally:
        con.close()
    for o in wynik["opiekunowie"]:
        if args.opiekun in (None, o["am_id"]):
            _drukuj(wiersze, wynik, o)


if __name__ == "__main__":
    main()
