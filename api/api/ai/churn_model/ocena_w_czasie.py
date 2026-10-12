"""Uczciwa ocena w czasie: uczenie na starszych snapszotach, test na snapszotach od 2026-01-01.

W uczeniu są tylko snapszoty, których okno etykiety [d, d + 90 dni) kończy się przed pierwszym dniem testu. Ostatni taki
snapszot miesięczny to 2025-10-01, więc między uczeniem a testem są 3 miesiące przerwy i żadna etykieta uczenia nie
korzysta ze zdarzeń z okresu testu.

Wspólny zbiór testowy to wiersze agencji ze snapszotów 2026-01 i 2026-04, bo model agencji da się ocenić tylko tam,
gdzie agencja dała cechy. Oceniamy na nim:
- v0_agencja: uczony na wierszach agencji (kwartalnych) do 2025-10;
- v2_bez_przeciekow: uczony na wszystkich miesięcznych snapszotach do 2025-10 (kontrolnie: tylko wiersze agencji);
- regula_opiekunow: bez uczenia.
v2 i reguła są też oceniane na wszystkich miesięcznych snapszotach 2026-01 – 2026-06. Przedziały 95% to bootstrap po
biurach, bo to samo biuro jest w kilku snapszotach testu. Wynik: evals/ocena_w_czasie.{json,png,md}.

    PYTHONPATH=api poetry run python -m api.ai.churn_model.ocena_w_czasie
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from api.adapters.duckdb_conn import connect  # noqa: E402
from api.ai.churn_model.rejestr import KOLOR_SERII, TEKST, TEKST_DRUGI, TLO  # noqa: E402
from api.ai.churn_model.versions.regula_opiekunow import RegulaOpiekunow  # noqa: E402
from api.ai.churn_model.versions.regula_opiekunow.ocen import cechy as cechy_reguly  # noqa: E402
from api.ai.churn_model.versions.v0_agencja import ModelAgencji  # noqa: E402
from api.ai.churn_model.versions.v2_bez_przeciekow import ModelBezPrzeciekow  # noqa: E402
from api.ai.churn_model.zbior_agencji import dane as dane_agencji  # noqa: E402
from api.ai.features.cechy import cechy_snapszotu  # noqa: E402

POCZATEK_TESTU = pd.Timestamp("2026-01-01")
OKNO_ETYKIETY = pd.Timedelta(days=90)
SPOSOB_OCENY = (
    "podział w czasie: uczenie na snapszotach do 2025-10 (okno etykiety kończy się przed testem), "
    "test na snapszotach od 2026-01"
)
POWTORZENIA_BOOTSTRAP = 1000
ZIARNO = 42
EVALS = Path(__file__).parent / "evals"
NIEAKTYWNY = "#b5b3ad"  # słupki tła: wyróżniamy tylko v2


def podzial_w_czasie(df: pd.DataFrame, kolumna_daty: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(uczący, testowy): uczący to snapszoty z oknem etykiety przed POCZATEK_TESTU, testowy to snapszoty od niego."""
    d = pd.to_datetime(df[kolumna_daty])
    return df[d + OKNO_ETYKIETY <= POCZATEK_TESTU], df[d >= POCZATEK_TESTU]


def przedzial_bootstrap(y: pd.Series, p: pd.Series, biura: pd.Series) -> tuple[float, float]:
    """95% przedział AUC z losowania biur ze zwracaniem (wszystkie wiersze wylosowanego biura razem)."""
    rng = np.random.default_rng(ZIARNO)
    y, p = y.to_numpy(), p.to_numpy()
    wiersze_biura = [np.flatnonzero(biura.to_numpy() == b) for b in biura.unique()]
    wyniki = []
    for _ in range(POWTORZENIA_BOOTSTRAP):
        idx = np.concatenate([wiersze_biura[i] for i in rng.integers(0, len(wiersze_biura), len(wiersze_biura))])
        if 0 < y[idx].sum() < len(idx):
            wyniki.append(roc_auc_score(y[idx], p[idx]))
    dol, gora = np.percentile(wyniki, [2.5, 97.5])
    return float(dol), float(gora)


def wynik(nazwa: str, y: pd.Series, p: pd.Series, biura: pd.Series, oznaczonych: int) -> dict:
    """AUC z przedziałem oraz trafienia wśród `oznaczonych` wierszy z najwyższym wynikiem."""
    dol, gora = przedzial_bootstrap(y, p, biura)
    top = p.sample(frac=1, random_state=ZIARNO).sort_values(ascending=False, kind="stable").index[:oznaczonych]
    trafione = int(y.loc[top].sum())
    return {
        "model": nazwa,
        "auc": round(float(roc_auc_score(y, p)), 4),
        "auc_95": [round(dol, 4), round(gora, 4)],
        "wiersze": len(y),
        "jedynki": int(y.sum()),
        "oznaczone": oznaczonych,
        "trafione": trafione,
        "precyzja": round(trafione / oznaczonych, 4),
        "czulosc": round(trafione / int(y.sum()), 4),
    }


def _z_kluczami(df: pd.DataFrame, cechy: pd.DataFrame, kolumna_daty: str) -> pd.DataFrame:
    return df.merge(
        cechy, left_on=["id_biura", kolumna_daty], right_on=["id_biura", "data_snapszotu"], how="left",
        validate="one_to_one", suffixes=("", "_cecha"),
    ).set_index(df.index)


def _wczytaj() -> tuple[pd.DataFrame, pd.DataFrame]:
    con = connect(read_only=True)
    try:
        cechy = cechy_snapszotu(con)
        snapshoty = con.sql("SELECT id_biura, data_snapszotu, odejdzie_90d FROM snapshoty").df()
    finally:
        con.close()
    regula = cechy_reguly()
    for t in (cechy, snapshoty, regula):
        t["data_snapszotu"] = pd.to_datetime(t["data_snapszotu"])
    miesieczne = snapshoty.merge(cechy, on=["id_biura", "data_snapszotu"], validate="one_to_one")
    miesieczne = miesieczne.merge(regula, on=["id_biura", "data_snapszotu"], validate="one_to_one")
    agencja = dane_agencji()
    agencja["data_migawki"] = pd.to_datetime(agencja["data_migawki"])
    return agencja, miesieczne


def ocen() -> dict:
    agencja, miesieczne = _wczytaj()
    ag_uczacy, ag_testowy = podzial_w_czasie(agencja, "data_migawki")
    mies_uczacy, mies_testowy = podzial_w_czasie(miesieczne, "data_snapszotu")

    # Wspólny zbiór testowy: wiersze agencji od 2026-01 z naszymi cechami i cechami reguły obok cech agencji.
    test = _z_kluczami(ag_testowy, miesieczne.drop(columns="odejdzie_90d"), "data_migawki")
    assert test["dni_do_rocznicy"].notna().all() and test["dni_do_konca_okresu"].notna().all(), "brak cech"
    y, biura = test["odejdzie_90d"], test["id_biura"]

    p_regula = RegulaOpiekunow().predict_proba(test)
    oznaczonych = int((p_regula == 1).sum())  # porównujemy precyzję przy tej samej liczbie oznaczonych co reguła
    p_v0 = ModelAgencji().fit(ag_uczacy, ag_uczacy["odejdzie_90d"]).predict_proba(test)
    v2 = ModelBezPrzeciekow().fit(mies_uczacy, mies_uczacy["odejdzie_90d"])
    ag_uczacy_v2 = _z_kluczami(ag_uczacy[["id_biura", "data_migawki", "odejdzie_90d"]], miesieczne.drop(
        columns="odejdzie_90d"), "data_migawki")
    v2_agencja = ModelBezPrzeciekow().fit(ag_uczacy_v2, ag_uczacy_v2["odejdzie_90d"])

    wspolny = [
        wynik("v0_agencja", y, p_v0, biura, oznaczonych),
        wynik("v2_bez_przeciekow", y, v2.predict_proba(test), biura, oznaczonych),
        wynik("regula_opiekunow", y, p_regula, biura, oznaczonych),
        wynik("v2_bez_przeciekow (uczony tylko na wierszach agencji)", y, v2_agencja.predict_proba(test), biura,
              oznaczonych),
    ]
    ym, bm = mies_testowy["odejdzie_90d"], mies_testowy["id_biura"]
    p_regula_m = RegulaOpiekunow().predict_proba(mies_testowy)
    oznaczonych_m = int((p_regula_m == 1).sum())
    miesieczny = [
        wynik("v2_bez_przeciekow", ym, v2.predict_proba(mies_testowy), bm, oznaczonych_m),
        wynik("regula_opiekunow", ym, p_regula_m, bm, oznaczonych_m),
    ]

    def opis_zbioru(df: pd.DataFrame, kolumna: str) -> dict:
        d = pd.to_datetime(df[kolumna])
        return {"od": f"{d.min():%Y-%m}", "do": f"{d.max():%Y-%m}", "snapszoty": int(d.nunique()), "wiersze": len(df),
                "jedynki": int(df["odejdzie_90d"].sum())}

    return {
        "sposob_oceny": SPOSOB_OCENY,
        "uczenie": {
            "v0_agencja (wiersze agencji, kwartalne)": opis_zbioru(ag_uczacy, "data_migawki"),
            "v2_bez_przeciekow (snapshoty, miesięczne)": opis_zbioru(mies_uczacy, "data_snapszotu"),
        },
        "test_wspolny": {**opis_zbioru(test, "data_migawki"), "wyniki": wspolny},
        "test_miesieczny": {**opis_zbioru(mies_testowy, "data_snapszotu"), "wyniki": miesieczny},
        "bootstrap": f"{POWTORZENIA_BOOTSTRAP} losowań biur ze zwracaniem, ziarno {ZIARNO}",
    }


def _liczba(x: float) -> str:
    # 0,9995 z trzema miejscami to „1,000”, czyli AUC idealne; tego nie wolno pokazać
    return (f"{x:.4f}" if x > 0.99 else f"{x:.3f}").replace(".", ",")


def wykres(wyniki: dict):
    test = wyniki["test_wspolny"]
    po_nazwie = {w["model"]: w for w in test["wyniki"]}
    slupki = [  # od góry: agencja, nasz model, reguła
        ("Model agencji (v0)", po_nazwie["v0_agencja"], NIEAKTYWNY, "przeciek: cechy z dnia eksportu"),
        ("Nowy model (v2_bez_przeciekow)", po_nazwie["v2_bez_przeciekow"], KOLOR_SERII, None),
        ("Reguła opiekunów", po_nazwie["regula_opiekunow"], NIEAKTYWNY, "reguła 0/1, bez uczenia"),
    ][::-1]

    fig, ax = plt.subplots(figsize=(9, 3.8), facecolor=TLO)
    ax.set_facecolor(TLO)
    for i, (nazwa, w, kolor, dopisek) in enumerate(slupki):
        dol, gora = w["auc_95"]
        ax.barh(i, w["auc"] - 0.5, left=0.5, height=0.42, color=kolor)
        ax.errorbar(w["auc"], i, xerr=[[w["auc"] - dol], [gora - w["auc"]]], fmt="none", ecolor=TEKST_DRUGI,
                    elinewidth=1.2, capsize=3)
        etykieta = f"{_liczba(w['auc'])}  ({_liczba(dol)}–{_liczba(gora)})"
        ax.annotate(etykieta, (gora, i), xytext=(6, 0), textcoords="offset points", va="center", fontsize=9,
                    color=TEKST, fontweight="bold" if kolor == KOLOR_SERII else "normal")
        if dopisek:
            ax.annotate(dopisek, (0.5, i - 0.32), xytext=(4, 0), textcoords="offset points", va="center",
                        fontsize=7.5, color=TEKST_DRUGI, style="italic")
    ax.set_yticks(range(len(slupki)), [s[0] for s in slupki], fontsize=9, color=TEKST)
    ax.set_xlim(0.5, 1.16)
    ax.set_ylim(-0.75, len(slupki) - 0.5)
    ax.set_xticks([0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:.1f}".replace(".", ",")))
    ax.set_xlabel("AUC na snapszotach 2026-01 i 2026-04 (0,5 = losowo; w nawiasie 95% przedział)", fontsize=8.5,
                  color=TEKST_DRUGI)
    wierszy = f"{test['wiersze']:,}".replace(",", "\u00a0")
    fig.text(0.01, 0.97, "Ocena w czasie: uczenie do 2025-10, 3 miesiące przerwy, test od 2026-01", fontsize=10.5,
             color=TEKST, va="top")
    fig.text(0.01, 0.905, f"Wspólny zbiór testowy: {wierszy} wierszy, {test['jedynki']} odejść", fontsize=8.5,
             color=TEKST_DRUGI, va="top")
    ax.tick_params(axis="x", colors=TEKST_DRUGI, labelsize=8, length=0)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color="#e4e3df", linewidth=0.8)
    ax.set_axisbelow(True)
    for strona in ax.spines.values():
        strona.set_visible(False)
    ax.axvline(0.5, color=TEKST_DRUGI, linewidth=0.8)
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    return fig


def main() -> None:
    wyniki = ocen()
    (EVALS / "ocena_w_czasie.json").write_text(json.dumps(wyniki, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(wyniki, ensure_ascii=False, indent=2))
    fig = wykres(wyniki)
    fig.savefig(EVALS / "ocena_w_czasie.png", dpi=150, facecolor=TLO)
    plt.close(fig)


if __name__ == "__main__":
    main()
