"""Krzywa wartości: zysk z wizyt opiekunów dla progu ryzyka od 0,01 do 0,99 na snapszocie 2026-04-01.

Jedziemy do biur z p >= próg, gdzie p to prognoza aktywnego modelu churnu (api/ai/churn_model/current.yaml).
Wynik liczymy na faktycznych odejściach (odejdzie_90d), według macierzy wartości (docs/macierz_wartosci.md):
trafiona wizyta (biuro odeszło) daje s × V − C, zbędna (biuro zostało) kosztuje C, brak wizyty daje 0.
s, V, C i budżet wizyt czytamy z retention_bc/zalozenia.yaml. Snapszot 2026-04-01 jest w części testowej
v4_skalibrowany (uczenie na t0 do 2025-07), więc model nie widział jego etykiet.

Niepewność: POWTORZENIA_BOOTSTRAP razy losujemy biura snapszotu ze zwracaniem i liczymy zysk przy każdym progu
oraz dla top budzet_wizyt biur w losowaniu. Przedział 90% to 5. i 95. percentyl tych zysków.

Próg czy cały budżet: na każdym snapszocie testowym porównujemy wizyty u biur z p >= najlepszy próg z 2026-04-01
(najwyżej budzet_wizyt) z wizytami u budzet_wizyt biur z najwyższym p. Liczymy, ile dają dodatkowe wizyty poniżej
progu, także przy C bez kosztu wizyty (sam rabat), gdyby czas opiekuna nic nie kosztował.

Tornado: jak zmienia się średni zysk na kwartał (snapszoty testowe) planu „p >= najlepszy próg, najwyżej
budzet_wizyt”, gdy s albo V przyjmuje skrajną wartość z ZAKRESY, a drugi parametr zostaje bazowy. Obok plan z progiem
dopasowanym do scenariusza: C / (s × V).

Obok liczymy zysk oczekiwany według samego modelu: suma p × s × V − C po wybranych biurach. Dla porównania ten sam
rachunek na pozostałych snapszotach testowych v4 (t0 2025-10 – 2026-03): czy najlepszy próg jest stabilny.

Wynik: docs/img/prog_krzywa_wartosci.png i krzywa_wartosci.json obok tego pliku (opis: docs/prog.md).

    PYTHONPATH=api poetry run python -m api.contexts_boundaries.retention_bc.prog.krzywa_wartosci
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from api.adapters.duckdb_conn import connect  # noqa: E402
from api.ai.churn_model.aktywny import wczytaj as aktywny_model  # noqa: E402
from api.ai.churn_model.kalibracja import wilson  # noqa: E402
from api.ai.churn_model.ocena_w_czasie import POWTORZENIA_BOOTSTRAP, ZIARNO  # noqa: E402
from api.ai.churn_model.rejestr import KOLOR_SERII, TEKST, TEKST_DRUGI, TLO  # noqa: E402

SNAPSZOT = pd.Timestamp("2026-04-01")
POCZATEK_TESTU = pd.Timestamp("2025-10-01")  # pierwszy snapszot testowy v4_skalibrowany (artefakty/ocena.json)
PROGI = np.round(np.arange(1, 100) / 100, 2)
PROG_0_5 = 0.5
PERCENTYLE = (5, 95)  # przedział 90%
KORZEN = Path(__file__).parents[5]
ZALOZENIA = KORZEN / "retention_bc" / "zalozenia.yaml"
WYKRES = KORZEN / "docs" / "img" / "prog_krzywa_wartosci.png"
WYKRES_TORNADO = KORZEN / "docs" / "img" / "prog_tornado.png"
# Zakresy z pytania sprzedaży (2026-10-13). W zalozenia.yaml: s 0,20–0,40, V 18 816–29 568 zł.
ZAKRESY = {"s": (0.20, 0.40), "V": (18_000, 30_000)}
NAZWY = {"s": "skuteczność wizyty s", "V": "wartość biura V"}
WYNIK = Path(__file__).with_name("krzywa_wartosci.json")
KOLOR_OCZEKIWANY = "#9a9893"
KOLOR_NAJLEPSZY = "#1a9e5c"
KOLOR_TOP = "#d9822b"
KOLOR_0_5 = "#c2410c"


def zalozenia() -> dict:
    """s, V, C i budżet wizyt z retention_bc/zalozenia.yaml (wartości punktowe i przedziały)."""
    par = yaml.safe_load(ZALOZENIA.read_text())["parametry"]
    return {
        "s": par["s"]["wartosc"],
        "V": par["V"]["wartosc"],
        "C": par["C"]["wartosc"],
        "budzet_wizyt": par["budzet_wizyt"]["wartosc"],
        "wizyty_na_opiekuna": par["budzet_wizyt"]["skladniki"]["wizyty_na_opiekuna"]["wartosc"],
        "udzial_kontroli": par["udzial_kontroli"]["wartosc"],
        "C_rabat": par["C"]["wartosc"] - par["C"]["skladniki"]["koszt_wizyty"]["wartosc"],
        "s_przedzial": par["s"]["przedzial"],
        "V_przedzial": par["V"]["przedzial"],
    }


def wynik_wizyt(p: pd.Series, y: pd.Series, s: float, V: float, C: float) -> dict:
    """Wizyty u wszystkich biur z p: ile ich, ile trafionych, zysk na odejściach i zysk oczekiwany z p."""
    wizyty, trafione = len(p), int(y.sum())
    return {
        "wizyty": wizyty,
        "trafione": trafione,
        "zbedne": wizyty - trafione,
        "zysk": trafione * (s * V - C) - (wizyty - trafione) * C,
        "zysk_oczekiwany": float((p * s * V - C).sum()),
    }


def krzywa_wartosci(p: pd.Series, y: pd.Series, progi, s: float, V: float, C: float) -> pd.DataFrame:
    """Jeden wiersz na próg: wizyty u biur z p >= próg i ich wynik (wynik_wizyt)."""
    return pd.DataFrame([{"prog": float(t), **wynik_wizyt(p[p >= t], y[p >= t], s, V, C)} for t in progi])


def top_n(p: pd.Series, y: pd.Series, n: int, s: float, V: float, C: float) -> dict:
    """Wizyty u n biur z najwyższym p; prog_p to p ostatniego z nich (najniższy próg dający te same biura)."""
    wybrane = p.sort_values(ascending=False, kind="stable").index[:n]
    return {"n": n, "prog_p": float(p[wybrane].min()), **wynik_wizyt(p[wybrane], y[wybrane], s, V, C)}


def najlepszy(krzywa: pd.DataFrame, kolumna: str = "zysk") -> dict:
    """Próg z największym zyskiem; przy remisie najwyższy (mniej wizyt za ten sam zysk)."""
    w = krzywa[krzywa[kolumna] == krzywa[kolumna].max()].iloc[-1]
    return {k: (float(v) if k in ("prog", "zysk", "zysk_oczekiwany") else int(v)) for k, v in w.items()}


def wrazliwosc(p: pd.Series, y: pd.Series, z: dict) -> list[dict]:
    """Najlepszy próg na odejściach przy skrajnych s i V z przedziałów w zalozenia.yaml (C bez przedziału)."""
    wyniki = []
    for s in z["s_przedzial"]:
        for V in z["V_przedzial"]:
            k = krzywa_wartosci(p, y, PROGI, s, V, z["C"])
            wyniki.append({"s": s, "V": V, "prog_oplacalnosci": z["C"] / (s * V), **najlepszy(k)})
    return wyniki


def zyski_bootstrap(
    p: pd.Series, y: pd.Series, progi, s: float, V: float, C: float, n_top: int, rng: np.random.Generator
) -> tuple[np.ndarray, np.ndarray]:
    """Zyski w POWTORZENIA_BOOTSTRAP losowaniach biur ze zwracaniem: (losowania × progi, zysk top n_top biur).

    Losowanie to liczba wylosowań każdego biura (wiersz snapszotu = jedno biuro). Top n_top bierze biura od
    najwyższego p, aż zbierze n_top wylosowań (biuro wylosowane dwa razy to dwie wizyty).
    """
    kolejnosc = np.argsort(-p.to_numpy(), kind="stable")
    p_, y_ = p.to_numpy()[kolejnosc], y.to_numpy()[kolejnosc]
    zysk_biura = np.where(y_ == 1, s * V - C, -C)
    n = len(p_)
    krotnosci = np.stack([np.bincount(rng.integers(0, n, n), minlength=n) for _ in range(POWTORZENIA_BOOTSTRAP)])
    zyski = krotnosci @ (zysk_biura[:, None] * (p_[:, None] >= np.asarray(progi)[None, :]))
    przed = np.cumsum(krotnosci, axis=1) - krotnosci  # wylosowania biur z wyższym p
    wziete = np.clip(n_top - przed, 0, krotnosci)
    return zyski, wziete @ zysk_biura


def przedzial(x: np.ndarray, os_: int = 0) -> np.ndarray:
    return np.percentile(x, PERCENTYLE, axis=os_)


def prog_czy_budzet(p: pd.Series, y: pd.Series, prog: float, n: int, s: float, V: float, C: float) -> dict:
    """Wizyty u biur z p >= prog (najwyżej n) wobec wizyt u n biur z najwyższym p: wynik obu i dodatkowych wizyt."""
    kolejnosc = p.sort_values(ascending=False, kind="stable").index
    k = min(int((p >= prog).sum()), n)
    przy_progu = wynik_wizyt(p[kolejnosc[:k]], y[kolejnosc[:k]], s, V, C)
    budzet = wynik_wizyt(p[kolejnosc[:n]], y[kolejnosc[:n]], s, V, C)
    dodatkowe = kolejnosc[k:n]
    return {
        "wizyty_prog": k,
        "trafione_prog": przy_progu["trafione"],
        "zysk_prog": przy_progu["zysk"],
        "trafione_budzet": budzet["trafione"],
        "zysk_budzet": budzet["zysk"],
        "dodatkowe_wizyty": len(dodatkowe),
        "dodatkowe_trafione": int(y[dodatkowe].sum()),
        "dodatkowe_zysk": budzet["zysk"] - przy_progu["zysk"],
        "dodatkowe_zysk_oczekiwany": float((p[dodatkowe] * s * V - C).sum()),
        "dodatkowe_p": [float(p[dodatkowe].min()), float(p[dodatkowe].max())] if len(dodatkowe) else None,
    }


def porownanie_budzetu(dane: pd.DataFrame, p: pd.Series, prog: float, z: dict) -> dict:
    """prog_czy_budzet na każdym snapszocie, suma po snapszotach i wynik na jedną dodatkową wizytę.

    Przedział 90% wyniku na wizytę: Wilson dla odsetka trafionych wśród dodatkowych wizyt (wizyty traktowane jak
    niezależne, choć to samo biuro bywa w kilku snapszotach).
    """
    s, V, n = z["s"], z["V"], z["budzet_wizyt"]
    wyniki = {}
    for nazwa, C in (("C", z["C"]), ("C_rabat", z["C_rabat"])):
        snapszoty = [
            {"t0": f"{t0:%Y-%m-%d}", **prog_czy_budzet(p[g.index], g["odejdzie_90d"].astype(int), prog, n, s, V, C)}
            for t0, g in dane.groupby("t0")
        ]
        suma = {k: sum(w[k] for w in snapszoty) for k in snapszoty[0] if k not in ("t0", "dodatkowe_p")}
        wizyty, trafione = suma["dodatkowe_wizyty"], suma["dodatkowe_trafione"]
        dol, gora = wilson(trafione, wizyty, z=1.645)
        wyniki[nazwa] = {
            "C": C,
            "snapszoty": snapszoty,
            "suma": suma,
            "na_dodatkowa_wizyte": suma["dodatkowe_zysk"] / wizyty,
            "na_dodatkowa_wizyte_oczekiwany": suma["dodatkowe_zysk_oczekiwany"] / wizyty,
            "na_dodatkowa_wizyte_90": [dol * s * V - C, gora * s * V - C],
            "odsetek_trafionych_dodatkowych": trafione / wizyty,
            "prog_oplacalnosci": C / (s * V),
        }
    return {"prog": prog, "budzet_wizyt": n, **wyniki}


def plan_w_scenariuszu(dane: pd.DataFrame, p: pd.Series, prog: float, z: dict, s: float, V: float) -> dict:
    """Średnio na snapszot (kwartał): plan p >= prog i plan p >= C / (s × V), oba najwyżej budzet_wizyt wizyt."""
    C, n = z["C"], z["budzet_wizyt"]
    staly, dopasowany = [], []
    for _, g in dane.groupby("t0"):
        pg, yg = p[g.index], g["odejdzie_90d"].astype(int)
        staly.append(prog_czy_budzet(pg, yg, prog, n, s, V, C))
        dopasowany.append(prog_czy_budzet(pg, yg, C / (s * V), n, s, V, C))
    return {
        "s": s,
        "V": V,
        "prog_oplacalnosci": C / (s * V),
        "zysk": float(np.mean([w["zysk_prog"] for w in staly])),
        "wizyty": float(np.mean([w["wizyty_prog"] for w in staly])),
        "zysk_dopasowany": float(np.mean([w["zysk_prog"] for w in dopasowany])),
        "wizyty_dopasowany": float(np.mean([w["wizyty_prog"] for w in dopasowany])),
    }


def tornado(dane: pd.DataFrame, p: pd.Series, prog: float, z: dict) -> dict:
    """Plan p >= prog w wariancie bazowym, przy skrajnych wartościach każdego parametru z ZAKRESY (drugi bazowy)
    i przy obu skrajnych naraz."""
    baza = {"s": z["s"], "V": z["V"]}
    parametry = {
        nazwa: {
            "dol": plan_w_scenariuszu(dane, p, prog, z, **{**baza, nazwa: dol}),
            "gora": plan_w_scenariuszu(dane, p, prog, z, **{**baza, nazwa: gora}),
        }
        for nazwa, (dol, gora) in ZAKRESY.items()
    }
    for w in parametry.values():
        w["rozpietosc"] = w["gora"]["zysk"] - w["dol"]["zysk"]
    return {
        "prog": prog,
        "baza": plan_w_scenariuszu(dane, p, prog, z, **baza),
        "parametry": parametry,
        "oba": {
            "dol": plan_w_scenariuszu(dane, p, prog, z, *(d for d, _ in ZAKRESY.values())),
            "gora": plan_w_scenariuszu(dane, p, prog, z, *(g for _, g in ZAKRESY.values())),
        },
    }


def po_snapszotach(dane: pd.DataFrame, p: pd.Series, z: dict) -> list[dict]:
    """Dla każdego snapszotu: najlepszy próg na odejściach i wynik top budzet_wizyt biur."""
    s, V, C, n = z["s"], z["V"], z["C"], z["budzet_wizyt"]
    wyniki = []
    for t0, g in dane.groupby("t0"):
        pg, yg = p[g.index], g["odejdzie_90d"].astype(int)
        naj = najlepszy(krzywa_wartosci(pg, yg, PROGI, s, V, C))
        top = top_n(pg, yg, n, s, V, C)
        wyniki.append({
            "t0": f"{t0:%Y-%m-%d}", "biura": len(g), "odejscia": int(yg.sum()),
            "najlepszy_prog": naj["prog"], "wizyty": naj["wizyty"], "trafione": naj["trafione"], "zysk": naj["zysk"],
            "zysk_prog_0_174": wynik_wizyt(pg[pg >= C / (s * V)], yg[pg >= C / (s * V)], s, V, C)["zysk"],
            "top_trafione": top["trafione"], "top_zysk": top["zysk"], "top_prog_p": top["prog_p"],
        })
    return wyniki


def _zl(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ")


def _tys(x: float) -> str:
    return f"{x / 1000:.0f}"


def _ul(x: float, miejsca: int) -> str:
    return f"{x:.{miejsca}f}".replace(".", ",")


def wykres(krzywa: pd.DataFrame, top: dict, naj: dict, z: dict, opis: str):
    fig, ax = plt.subplots(figsize=(9, 5.6), facecolor=TLO)
    ax.set_facecolor(TLO)
    poza_budzetem = krzywa.loc[krzywa["wizyty"] > z["budzet_wizyt"], "prog"]
    ax.fill_between(krzywa["prog"], krzywa["zysk_5"], krzywa["zysk_95"], color=KOLOR_SERII, alpha=0.15,
                    linewidth=0, label="90% przedział zysku (bootstrap biur, 1000 losowań)")
    if len(poza_budzetem):  # progi, przy których wizyt jest więcej niż budżet na kwartał
        ax.axvspan(0, poza_budzetem.max() + 0.005, color="#efeeea", zorder=0)
        ax.text(0.012, 0.97, f"więcej niż {z['budzet_wizyt']} wizyt\n(ponad budżet)", transform=ax.transAxes,
                fontsize=8, color=TEKST_DRUGI, va="top")
    ax.axhline(0, color=TEKST_DRUGI, linewidth=0.8)
    ax.plot(krzywa["prog"], krzywa["zysk_oczekiwany"], color=KOLOR_OCZEKIWANY, linewidth=1.4,
            linestyle=(0, (4, 3)), label="zysk oczekiwany według modelu (suma p × s × V − C)")
    ax.plot(krzywa["prog"], krzywa["zysk"], color=KOLOR_SERII, linewidth=2.2,
            label="zysk na faktycznych odejściach")

    w05 = krzywa.loc[np.isclose(krzywa["prog"], PROG_0_5)].iloc[0]
    wn = krzywa.loc[np.isclose(krzywa["prog"], naj["prog"])].iloc[0]
    punkty = [
        (naj["prog"], naj["zysk"], KOLOR_NAJLEPSZY,
         f"największy zysk: próg {_ul(naj['prog'], 2)}\n{naj['wizyty']} wizyt, {naj['trafione']} trafionych, "
         f"{_zl(naj['zysk'])} zł (90%: {_tys(wn['zysk_5'])}–{_tys(wn['zysk_95'])} tys. zł)", (40, 8)),
        (top["prog_p"], top["zysk"], KOLOR_TOP,
         f"top {top['n']} (p ≥ {_ul(top['prog_p'], 3)})\n{top['wizyty']} wizyt, {top['trafione']} trafionych, "
         f"{_zl(top['zysk'])} zł (90%: {_tys(top['zysk_5'])}–{_tys(top['zysk_95'])} tys. zł)", (60, -85)),
        (PROG_0_5, w05["zysk"], KOLOR_0_5,
         f"próg 0,5: {int(w05['wizyty'])} wizyt, {_zl(w05['zysk'])} zł\n(najwyższe p w snapszocie: "
         f"{_ul(krzywa.attrs['max_p'], 2)})", (8, 30)),
    ]
    ax.errorbar([top["prog_p"]], [top["zysk"]], yerr=[[top["zysk"] - top["zysk_5"]], [top["zysk_95"] - top["zysk"]]],
                fmt="none", ecolor=KOLOR_TOP, linewidth=1.4, capsize=4, zorder=4)
    for x, y, kolor, tekst, przesuniecie in punkty:
        ax.plot([x], [y], marker="o", markersize=8, color=kolor, markeredgecolor=TLO, markeredgewidth=2, zorder=5)
        ax.annotate(tekst, (x, y), xytext=przesuniecie, textcoords="offset points", fontsize=8.5, color=kolor,
                    va="top" if przesuniecie[1] < 0 else "bottom", arrowprops={"arrowstyle": "-", "color": kolor, "linewidth": 0.8})

    dol = max(krzywa["zysk"].min(), -150_000)
    ax.set_ylim(dol, krzywa["zysk_95"].max() * 1.12)
    ax.set_xlim(0, 1)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v / 1000:,.0f} tys. zł".replace(",", " ")))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: _ul(v, 1)))
    ax.set_xlabel("próg ryzyka: jedziemy do biur z p ≥ próg", fontsize=9, color=TEKST_DRUGI)
    ax.set_ylabel("zysk z wizyt względem braku wizyt", fontsize=9, color=TEKST_DRUGI)
    ax.tick_params(colors=TEKST_DRUGI, labelsize=8, length=0)
    ax.grid(color="#e4e3df", linewidth=0.8)
    ax.set_axisbelow(True)
    for strona in ax.spines.values():
        strona.set_visible(False)
    ax.legend(loc="upper right", fontsize=8, frameon=False, labelcolor=TEKST_DRUGI)
    fig.text(0.01, 0.975, "Od jakiego ryzyka opłaca się jechać do biura", fontsize=11, color=TEKST,
             fontweight="bold", va="top")
    fig.text(0.01, 0.93, opis, fontsize=8, color=TEKST_DRUGI, va="top")
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    if dol > krzywa["zysk"].min():
        ax.text(0.99, 0.03, f"oś ucięta: przy progu 0,01 zysk {_zl(krzywa['zysk'].min())} zł",
                transform=ax.transAxes, fontsize=7.5, color=TEKST_DRUGI, ha="right", va="bottom")
    return fig


def _opis_wartosci(nazwa: str, x: float) -> str:
    return f"s = {x:.0%}" if nazwa == "s" else f"V = {_tys(x)} tys. zł"


def _tys1(x: float) -> str:
    return f"{x / 1000:.1f}".replace(".", ",").replace("-", "−") + " tys. zł"


def wykres_tornado(t: dict, opis: str):
    """Poziome słupki od zysku bazowego do zysku przy dolnej i górnej wartości parametru; najszerszy na górze."""
    baza = t["baza"]["zysk"]
    wiersze = sorted(t["parametry"].items(), key=lambda kv: kv[1]["rozpietosc"])
    wiersze = [("oba", t["oba"])] + wiersze  # na dole, oddzielone: oba parametry naraz
    zakres = {"s": f"s = {ZAKRESY['s'][0]:.0%}–{ZAKRESY['s'][1]:.0%}".replace("%–", "–"),
              "V": f"V = {_tys(ZAKRESY['V'][0])}–{_tys(ZAKRESY['V'][1])} tys. zł"}
    etykiety = {"oba": "oba naraz\n(dla porównania)",
                **{k: f"{NAZWY[k]}\n{zakres[k]}\nrozpiętość {_tys1(w['rozpietosc'])}" for k, w in t["parametry"].items()}}
    fig, ax = plt.subplots(figsize=(9, 4.4), facecolor=TLO)
    ax.set_facecolor(TLO)
    pozycje = [0, 1.4, 2.4]
    for y, (nazwa, w) in zip(pozycje, wiersze):
        for koniec, kolor in (("dol", KOLOR_TOP), ("gora", KOLOR_SERII)):
            x = w[koniec]["zysk"]
            ax.barh(y, x - baza, left=baza, height=0.56, color=kolor, alpha=0.55 if nazwa == "oba" else 1,
                    edgecolor=TLO, linewidth=2)
            if nazwa == "oba":
                tekst = ("s 20%, V 18 tys." if koniec == "dol" else "s 40%, V 30 tys.")
            else:
                tekst = _opis_wartosci(nazwa, w[koniec][nazwa])
            ax.annotate(f"{tekst}\n{_tys1(x)}", (x, y), xytext=(-6 if x < baza else 6, 0),
                        textcoords="offset points", ha="right" if x < baza else "left", va="center", fontsize=8,
                        color=TEKST)
    ax.axvline(baza, color=TEKST, linewidth=1.2)
    ax.annotate(f"bazowo (s = {t['baza']['s']:.0%}, V = {_zl(t['baza']['V'])} zł): {_tys1(baza)}",
                (baza, pozycje[-1] + 0.45), ha="center", va="bottom", fontsize=8, color=TEKST)
    ax.axvline(0, color=TEKST_DRUGI, linewidth=0.8, linestyle=(0, (4, 3)))
    ax.set_yticks(pozycje, [etykiety[n] for n, _ in wiersze], fontsize=8.5, color=TEKST)
    ax.set_ylim(-0.5, pozycje[-1] + 0.85)
    lewo = min(w["dol"]["zysk"] for _, w in wiersze)
    prawo = max(w["gora"]["zysk"] for _, w in wiersze)
    ax.set_xlim(lewo - 45_000, prawo + 45_000)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v / 1000:,.0f} tys. zł".replace(",", " ")))
    ax.set_xlabel(f"średni zysk na kwartał: wizyty u biur z p ≥ {_ul(t['prog'], 2)}, najwyżej 60",
                  fontsize=9, color=TEKST_DRUGI)
    ax.tick_params(colors=TEKST_DRUGI, labelsize=8, length=0)
    ax.grid(axis="x", color="#e4e3df", linewidth=0.8)
    ax.set_axisbelow(True)
    for strona in ax.spines.values():
        strona.set_visible(False)
    fig.text(0.01, 0.975, "Skuteczność wizyty zmienia wynik bardziej niż wartość biura", fontsize=11, color=TEKST,
             fontweight="bold", va="top")
    fig.text(0.01, 0.915, opis, fontsize=8, color=TEKST_DRUGI, va="top")
    fig.tight_layout(rect=(0, 0, 1, 0.84))
    return fig


def main() -> None:
    z = zalozenia()
    s, V, C = z["s"], z["V"], z["C"]
    con = connect(read_only=True)
    try:
        dane = con.execute(
            "SELECT * FROM cechy_treningowe WHERE t0 BETWEEN ? AND ?", [POCZATEK_TESTU.date(), SNAPSZOT.date()]
        ).df()
    finally:
        con.close()
    dane["t0"] = pd.to_datetime(dane["t0"])
    model = aktywny_model()
    p_wszystkie = model.predict_proba(dane)
    snap = dane[dane["t0"] == SNAPSZOT]
    assert snap["id_biura"].is_unique, "snapszot ma mieć jeden wiersz na biuro"
    p = p_wszystkie[snap.index]
    y = snap["odejdzie_90d"].astype(int)

    krzywa = krzywa_wartosci(p, y, PROGI, s, V, C)
    krzywa.attrs["max_p"] = float(p.max())
    top = top_n(p, y, z["budzet_wizyt"], s, V, C)

    zyski, zyski_top = zyski_bootstrap(p, y, PROGI, s, V, C, z["budzet_wizyt"], np.random.default_rng(ZIARNO))
    krzywa["zysk_5"], krzywa["zysk_95"] = przedzial(zyski)
    top["zysk_5"], top["zysk_95"] = (float(v) for v in przedzial(zyski_top))
    najlepsze_w_losowaniach = PROGI[zyski.argmax(axis=1)]
    i_015 = int(np.flatnonzero(np.isclose(PROGI, 0.15))[0])
    i_018 = int(np.searchsorted(PROGI, 0.18))  # pierwszy próg siatki ≥ C / (s × V) = 0,174
    bootstrap = {
        "opis": f"{POWTORZENIA_BOOTSTRAP} losowań biur snapszotu ze zwracaniem, ziarno {ZIARNO}, przedział 90% "
        f"(percentyle {PERCENTYLE[0]} i {PERCENTYLE[1]})",
        "najlepszy_prog_90": [float(v) for v in przedzial(najlepsze_w_losowaniach)],
        "najlepszy_prog_mediana": float(np.median(najlepsze_w_losowaniach)),
        "roznica_0_15_minus_top_90": [float(v) for v in przedzial(zyski[:, i_015] - zyski_top)],
        "udzial_0_15_lepszy_od_top": float((zyski[:, i_015] > zyski_top).mean()),
        "roznica_0_18_minus_top_90": [float(v) for v in przedzial(zyski[:, i_018] - zyski_top)],
        "udzial_zysk_dodatni_0_15": float((zyski[:, i_015] > 0).mean()),
        "udzial_zysk_dodatni_top": float((zyski_top > 0).mean()),
    }
    naj = najlepszy(krzywa)
    naj_oczekiwany = najlepszy(krzywa, "zysk_oczekiwany")
    w_budzecie = najlepszy(krzywa[krzywa["wizyty"] <= z["budzet_wizyt"]])
    wynik = {
        "snapszot": f"{SNAPSZOT:%Y-%m-%d}",
        "model": model.wersja,
        "biura": len(snap),
        "odejscia": int(y.sum()),
        "max_p": round(float(p.max()), 4),
        "zalozenia": {"s": s, "V": V, "C": C, "budzet_wizyt": z["budzet_wizyt"],
                      "zysk_trafionej": s * V - C, "prog_oplacalnosci": C / (s * V)},
        "najlepszy_prog": naj,
        "najlepszy_prog_w_budzecie": w_budzecie,
        "najlepszy_prog_oczekiwany": naj_oczekiwany,
        "top": top,
        "bootstrap": bootstrap,
        "prog_0_5": krzywa.loc[np.isclose(krzywa["prog"], PROG_0_5)].iloc[0].to_dict(),
        "odejscia_ponad_progiem_0_5": int(y[p >= PROG_0_5].sum()),
        "wrazliwosc": wrazliwosc(p, y, z),
        "po_snapszotach": po_snapszotach(dane, p_wszystkie, z),
        "prog_czy_budzet": porownanie_budzetu(dane, p_wszystkie, naj["prog"], z),
        "tornado": tornado(dane, p_wszystkie, naj["prog"], z),
        "krzywa": krzywa.round({"zysk": 2, "zysk_oczekiwany": 2, "zysk_5": 2, "zysk_95": 2}).to_dict("records"),
    }
    WYNIK.write_text(json.dumps(wynik, ensure_ascii=False, indent=2) + "\n")

    opis = (
        f"Snapszot {SNAPSZOT:%Y-%m-%d}: {_zl(len(snap))} biur, {int(y.sum())} odeszło w 90 dni. Model {model.wersja}. "
        f"Trafiona wizyta: s × V − C = {_zl(s * V - C)} zł, zbędna: −{_zl(C)} zł\n"
        f"(s = {_ul(s, 2)}, V = {_zl(V)} zł, C = {_zl(C)} zł z retention_bc/zalozenia.yaml). "
        f"Próg opłacalności według modelu: C / (s × V) = {_ul(C / (s * V), 3)}."
    )
    fig = wykres(krzywa, top, naj, z, opis)
    fig.savefig(WYKRES, dpi=150, facecolor=TLO)
    opis_tornado = (
        f"Snapszoty testowe {POCZATEK_TESTU:%Y-%m} – {SNAPSZOT:%Y-%m}, model {model.wersja}. Zmieniamy jeden parametr, "
        f"drugi zostaje bazowy; C = {_zl(C)} zł.\nPomarańczowy: dolna wartość parametru, niebieski: górna. "
        f"Przerywana linia: 0 zł."
    )
    fig = wykres_tornado(wynik["tornado"], opis_tornado)
    fig.savefig(WYKRES_TORNADO, dpi=150, facecolor=TLO)
    print(json.dumps({k: v for k, v in wynik.items() if k != "krzywa"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
