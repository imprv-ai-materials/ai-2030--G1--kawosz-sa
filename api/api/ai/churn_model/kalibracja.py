"""Kalibracja v3_katalog: czy wynik modelu można czytać jako P(odejście w 90 dni), i kalibracja Platta i izotoniczna.

Zysk z wizyty (docs/macierz_wartosci.md) to p × s × V − C, więc p musi być prawdziwym prawdopodobieństwem.
v3_katalog uczyła się z class_weight="balanced". Liczymy:
1. na zapisanym artefakcie v3_katalog: ile biur wybiera próg 0,5 na snapszocie 2026-04-01 i wykres kalibracji na
   zbiorze testowym v3 (t0 2025-10 – 2026-04) w 10 przedziałach równej szerokości;
2. kalibrację. Walidacja to ostatnie 3 miesiące uczenia przed przerwą (t0 2025-05 – 2025-07). Kalibrator nie może
   się uczyć na wierszach, które widział model, więc model bazowy to Pipeline v3 uczony od nowa bez walidacji: na t0,
   których okno etykiety kończy się przed walidacją (2024-04 – 2025-01, ta sama zasada co foldy w v3/trenuj.py).
   Na jego wynikach na walidacji uczymy CalibratedClassifierCV(FrozenEstimator(...)) metodą sigmoid (Platt) i
   isotonic, a oceniamy na teście: przed kalibracją, po Platcie i po izotonicznej.
Wynik: evals/kalibracja.{json,png} i evals/kalibracja_przed_po.png.

    PYTHONPATH=api poetry run python -m api.ai.churn_model.kalibracja
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402
from sklearn.calibration import CalibratedClassifierCV  # noqa: E402
from sklearn.frozen import FrozenEstimator  # noqa: E402
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score  # noqa: E402

from api.adapters.duckdb_conn import connect  # noqa: E402
from api.ai.churn_model.ocena_w_czasie import POWTORZENIA_BOOTSTRAP, ZIARNO  # noqa: E402
from api.ai.churn_model.rejestr import KOLOR_SERII, TEKST, TEKST_DRUGI, TLO  # noqa: E402
from api.ai.churn_model.versions.v3_katalog.model import CECHY_WEJSCIOWE, ModelKatalog, zbuduj_pipeline  # noqa: E402
from api.ai.churn_model.versions.v3_katalog.trenuj import ARTEFAKTY, OKNO_ETYKIETY, podzial_czasowy  # noqa: E402

SNAPSZOT = pd.Timestamp("2026-04-01")
PROG = 0.5
PRZEDZIALY = np.linspace(0, 1, 11)
POCZATEK_WALIDACJI = pd.Timestamp("2025-05-01")  # ostatnie 3 miesiące uczenia v3 (t0 do 2025-07)
STALA = 0.035  # punkt odniesienia: każde biuro 3,5% (odsetek odejść na teście, zaokrąglony)
POWTORZENIA_STABILNOSCI = 200  # ile razy uczymy kalibrator na losowaniu biur z walidacji
MALO_WIERSZY = 30  # przedział z mniejszą liczbą wierszy rysujemy pustym punktem, bez linii
EVALS = Path(__file__).parent / "evals"
ZALOZENIA = Path(__file__).parents[4] / "retention_bc" / "zalozenia.yaml"


def prog_oplacalnosci() -> float:
    """p, od którego wizyta się opłaca: C / (s × V) z retention_bc/zalozenia.yaml (docs/macierz_wartosci.md)."""
    par = yaml.safe_load(ZALOZENIA.read_text())["parametry"]
    return par["C"]["wartosc"] / (par["s"]["wartosc"] * par["V"]["wartosc"])


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% przedział Wilsona dla odsetka k/n (wiersze traktowane jak niezależne)."""
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    srodek = (p + z**2 / (2 * n)) / (1 + z**2 / n)
    pol = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / (1 + z**2 / n)
    return float(srodek - pol), float(srodek + pol)


def tabela_kalibracji(y: pd.Series, p: pd.Series) -> pd.DataFrame:
    """Jeden wiersz na przedział [a, b) wyniku modelu (ostatni domknięty): liczba wierszy, średnie p, odejścia."""
    kosz = np.minimum(np.searchsorted(PRZEDZIALY, p.to_numpy(), side="right") - 1, len(PRZEDZIALY) - 2)
    t = pd.DataFrame({"p": p.to_numpy(), "y": y.to_numpy(), "kosz": kosz}).groupby("kosz")
    tab = t.agg(wiersze=("p", "size"), srednie_p=("p", "mean"), odejscia=("y", "sum"))
    tab = tab.reindex(range(len(PRZEDZIALY) - 1)).fillna({"wiersze": 0, "odejscia": 0}).astype(
        {"wiersze": int, "odejscia": int}
    )
    tab["odsetek_odejsc"] = tab["odejscia"] / tab["wiersze"].replace(0, np.nan)
    tab[["dol_95", "gora_95"]] = [wilson(k, n) for k, n in zip(tab["odejscia"], tab["wiersze"])]
    tab.insert(0, "przedzial", [f"{a:.1f}–{b:.1f}" for a, b in zip(PRZEDZIALY[:-1], PRZEDZIALY[1:])])
    return tab.reset_index(drop=True)


def _tabela_json(tab: pd.DataFrame) -> list[dict]:
    return [
        {k: (None if pd.isna(v) else round(float(v), 4) if isinstance(v, float) else v) for k, v in w.items()}
        for w in tab.to_dict("records")
    ]


def wybor_progiem(testowy: pd.DataFrame, p: pd.Series, prog: float) -> dict:
    """Ile biur wybiera próg na SNAPSZOT i ile z nich odeszło."""
    snap = testowy["t0"] == SNAPSZOT
    wybrane = snap & (p >= prog)
    return {
        "prog": round(prog, 4),
        "wybrane": int(wybrane.sum()),
        "wybrane_odeszly": int(testowy.loc[wybrane, "odejdzie_90d"].sum()),
    }


def miary(testowy: pd.DataFrame, p: pd.Series, prog_zysku: float) -> dict:
    y = testowy["odejdzie_90d"].astype(int)
    snap = testowy["t0"] == SNAPSZOT
    return {
        "auc": round(float(roc_auc_score(y, p)), 4),
        "brier": round(float(brier_score_loss(y, p)), 4),
        "log_loss": round(float(log_loss(y, p)), 4),
        "srednie_p": round(float(p.mean()), 4),
        "max_p": round(float(p.max()), 4),
        "suma_p_snapszot": round(float(p[snap].sum()), 1),
        "prog_0_5": wybor_progiem(testowy, p, PROG),
        "prog_oplacalnosci": wybor_progiem(testowy, p, prog_zysku),
        "przedzialy": _tabela_json(tabela_kalibracji(y, p)),
    }


def losuj_biura(biura: pd.Series, rng: np.random.Generator) -> np.ndarray:
    """Pozycje wierszy z losowania biur ze zwracaniem (wszystkie wiersze wylosowanego biura razem)."""
    pozycje = pd.Series(np.arange(len(biura))).groupby(biura.to_numpy()).apply(np.array).tolist()
    return np.concatenate([pozycje[i] for i in rng.integers(0, len(pozycje), len(pozycje))])


def porownanie_brier(y: pd.Series, prognozy: dict[str, pd.Series], biura: pd.Series, pary: list[tuple]) -> dict:
    """Brier każdej prognozy na teście i 95% przedział różnicy dla par (bootstrap po biurach)."""
    y_ = y.to_numpy()
    kwadraty = {k: (v.to_numpy() - y_) ** 2 for k, v in prognozy.items()}
    rng = np.random.default_rng(ZIARNO)
    roznice = {f"{a} − {b}": [] for a, b in pary}
    for _ in range(POWTORZENIA_BOOTSTRAP):
        idx = losuj_biura(biura, rng)
        for a, b in pary:
            roznice[f"{a} − {b}"].append(kwadraty[a][idx].mean() - kwadraty[b][idx].mean())
    return {
        "brier": {k: round(float(v.mean()), 5) for k, v in kwadraty.items()},
        "roznice_95": {
            k: {
                "roznica": round(float(kwadraty[k.split(" − ")[0]].mean() - kwadraty[k.split(" − ")[1]].mean()), 5),
                "przedzial": [round(float(x), 5) for x in np.percentile(v, [2.5, 97.5])],
                "udzial_ponizej_zera": round(float(np.mean(np.array(v) < 0)), 3),
            }
            for k, v in roznice.items()
        },
        "bootstrap": f"{POWTORZENIA_BOOTSTRAP} losowań biur testu ze zwracaniem, ziarno {ZIARNO}",
    }


def odejscia_walidacji(walidacja: pd.DataFrame) -> dict:
    """Ile odejść widzi kalibrator: wiersze z etykietą 1 i różne biura (biuro bywa 1 w kilku kolejnych t0)."""
    jedynki = walidacja[walidacja["odejdzie_90d"] == 1]
    return {
        "wiersze": len(walidacja),
        "biura": int(walidacja["id_biura"].nunique()),
        "wiersze_z_odejsciem": len(jedynki),
        "biura_z_odejsciem": int(jedynki["id_biura"].nunique()),
        "po_miesiacach": {f"{t0:%Y-%m}": int(n) for t0, n in jedynki.groupby("t0").size().items()},
        "biura_wg_liczby_wierszy_z_odejsciem": {
            int(k): int(v) for k, v in jedynki.groupby("id_biura").size().value_counts().sort_index().items()
        },
    }


def stabilnosc(bazowy, walidacja: pd.DataFrame, testowy: pd.DataFrame, brier_stalej: float) -> dict:
    """Jak bardzo wynik metody zależy od tego, które biura trafiły do walidacji: kalibratory uczone na
    POWTORZENIA_STABILNOSCI losowaniach biur z walidacji, każdy oceniany na całym teście."""
    rng = np.random.default_rng(ZIARNO)
    X_wal, y_wal = walidacja[CECHY_WEJSCIOWE], walidacja["odejdzie_90d"].astype(int)
    X_test, y_test = testowy[CECHY_WEJSCIOWE], testowy["odejdzie_90d"].astype(int)
    wyniki = {"sigmoid": {"brier": [], "max_p": []}, "isotonic": {"brier": [], "max_p": []}}
    for _ in range(POWTORZENIA_STABILNOSCI):
        idx = losuj_biura(walidacja["id_biura"], rng)
        for metoda, w in wyniki.items():
            kal = CalibratedClassifierCV(FrozenEstimator(bazowy), method=metoda).fit(X_wal.iloc[idx], y_wal.iloc[idx])
            q = kal.predict_proba(X_test)[:, 1]
            w["brier"].append(brier_score_loss(y_test, q))
            w["max_p"].append(q.max())
    nazwy = {"sigmoid": "platt", "isotonic": "izotoniczna"}
    b_platt, b_izo = np.array(wyniki["sigmoid"]["brier"]), np.array(wyniki["isotonic"]["brier"])
    return {
        "opis": f"{POWTORZENIA_STABILNOSCI} losowań biur walidacji ze zwracaniem, ziarno {ZIARNO}; Brier na teście",
        **{
            nazwy[m]: {
                "brier_mediana": round(float(np.median(w["brier"])), 5),
                "brier_95": [round(float(x), 5) for x in np.percentile(w["brier"], [2.5, 97.5])],
                "brier_najgorszy": round(float(np.max(w["brier"])), 5),
                "gorszy_niz_stala": round(float(np.mean(np.array(w["brier"]) > brier_stalej)), 3),
                "max_p_mediana": round(float(np.median(w["max_p"])), 4),
                "udzial_z_p_1": round(float(np.mean(np.array(w["max_p"]) >= 0.999)), 3),
            }
            for m, w in wyniki.items()
        },
        "platt_lepszy_od_izotonicznej": round(float(np.mean(b_platt < b_izo)), 3),
    }



def rysuj_kalibracje(ax, tab: pd.DataFrame, tytul: str, podpis_przekatnej: bool = True) -> None:
    """Krzywa kalibracji na osi ax: średni wynik w przedziale względem odsetka odejść, z przedziałem Wilsona."""
    tab = tab.dropna(subset=["srednie_p"])
    ax.set_facecolor(TLO)
    ax.plot([0, 1], [0, 1], color=TEKST_DRUGI, linewidth=1, linestyle=(0, (4, 3)))
    if podpis_przekatnej:
        ax.annotate("idealna kalibracja", (0.62, 0.62), rotation=45, rotation_mode="anchor", xytext=(0, 5),
                    textcoords="offset points", fontsize=8.5, color=TEKST_DRUGI)
    duze = tab[tab["wiersze"] >= MALO_WIERSZY]
    ax.errorbar(
        duze["srednie_p"], duze["odsetek_odejsc"],
        yerr=[duze["odsetek_odejsc"] - duze["dol_95"], duze["gora_95"] - duze["odsetek_odejsc"]],
        fmt="none", ecolor=KOLOR_SERII, alpha=0.45, linewidth=1.2, capsize=0,
    )
    ax.plot(duze["srednie_p"], duze["odsetek_odejsc"], color=KOLOR_SERII, linewidth=2, marker="o", markersize=7,
            markeredgecolor=TLO, markeredgewidth=2)
    male = tab[tab["wiersze"] < MALO_WIERSZY]  # bez linii i przedziału: kilka wierszy nic nie mówi o kalibracji
    ax.plot(male["srednie_p"], male["odsetek_odejsc"], linestyle="none", marker="o", markersize=7,
            markerfacecolor=TLO, markeredgecolor=KOLOR_SERII, markeredgewidth=1.5)
    for _, w in tab.iterrows():
        ax.annotate(f"{w['wiersze']:,}".replace(",", " "), (w["srednie_p"], w["odsetek_odejsc"]), xytext=(7, 4),
                    textcoords="offset points", ha="left", va="bottom", fontsize=7.5, color=TEKST_DRUGI)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    for os_ in (ax.xaxis, ax.yaxis):
        os_.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.set_title(tytul, fontsize=10, color=TEKST, loc="left")
    ax.tick_params(colors=TEKST_DRUGI, labelsize=8, length=0)
    ax.grid(color="#e4e3df", linewidth=0.8)
    ax.set_axisbelow(True)
    for strona in ax.spines.values():
        strona.set_visible(False)


OS_X = "średni wynik modelu w przedziale (przedziały co 10 pp.)"
OS_Y = "odsetek biur, które odeszły w 90 dni"
PODPIS = (
    "Przy punkcie liczba wierszy w przedziale, pionowa kreska: 95% przedział Wilsona, "
    f"pusty punkt: przedział z mniej niż {MALO_WIERSZY} wierszami"
)


def wykres(tab: pd.DataFrame, opis_testu: str):
    fig, ax = plt.subplots(figsize=(7, 6.2), facecolor=TLO)
    rysuj_kalibracje(ax, tab, "")
    ax.set_xlabel(OS_X, fontsize=9, color=TEKST_DRUGI)
    ax.set_ylabel(OS_Y, fontsize=9, color=TEKST_DRUGI)
    fig.text(0.02, 0.97, "v3_katalog: model przeszacowuje ryzyko odejścia", fontsize=11, color=TEKST,
             fontweight="bold", va="top")
    fig.text(0.02, 0.93, f"{opis_testu}\n{PODPIS}", fontsize=8, color=TEKST_DRUGI, va="top")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    return fig


def wykres_przed_po(tabele: dict[str, pd.DataFrame], opis: str):
    """Panele obok siebie: przed kalibracją, Platt, izotoniczna (ten sam model bazowy, ten sam test)."""
    fig, osie = plt.subplots(1, len(tabele), figsize=(15, 6.2), facecolor=TLO, sharey=True)
    for i, (ax, (tytul, tab)) in enumerate(zip(osie, tabele.items())):
        rysuj_kalibracje(ax, tab, tytul, podpis_przekatnej=i == 0)
        ax.set_xlabel(OS_X, fontsize=8.5, color=TEKST_DRUGI)
    osie[0].set_ylabel(OS_Y, fontsize=9, color=TEKST_DRUGI)
    fig.text(0.01, 0.97, "Kalibracja na walidacji 2025-05 – 2025-07, ocena na teście", fontsize=11, color=TEKST,
             fontweight="bold", va="top")
    fig.text(0.01, 0.915, f"{opis}\n{PODPIS}", fontsize=8, color=TEKST_DRUGI, va="top")
    fig.tight_layout(rect=(0, 0.01, 1, 0.86))
    return fig


def main() -> None:
    con = connect(read_only=True)
    try:
        treningowe = con.sql("SELECT * FROM cechy_treningowe").df()
    finally:
        con.close()
    treningowe["t0"] = pd.to_datetime(treningowe["t0"])
    uczacy, testowy = podzial_czasowy(treningowe)
    model = ModelKatalog.load(ARTEFAKTY)
    testowy = testowy.assign(p=model.predict_proba(testowy))
    y, p = testowy["odejdzie_90d"].astype(int), testowy["p"]
    prog_zysku = prog_oplacalnosci()

    # 1. Zapisany artefakt v3_katalog
    snap = testowy[testowy["t0"] == SNAPSZOT]
    wybrane = snap[snap["p"] >= PROG]
    po_snapszotach = [
        {
            "t0": f"{t0:%Y-%m-%d}",
            "biura": len(g),
            "odejscia": int(g["odejdzie_90d"].sum()),
            "wybrane": int((g["p"] >= PROG).sum()),
            "wybrane_odeszly": int(g.loc[g["p"] >= PROG, "odejdzie_90d"].sum()),
        }
        for t0, g in testowy.groupby("t0")
    ]
    tab = tabela_kalibracji(y, p)

    # 2. Kalibracja: model bazowy bez walidacji, kalibratory na walidacji, ocena na teście
    t0_uczace = uczacy["t0"]
    walidacja = uczacy[t0_uczace >= POCZATEK_WALIDACJI]
    bazowy_uczacy = uczacy[t0_uczace + OKNO_ETYKIETY <= POCZATEK_WALIDACJI]
    bazowy = zbuduj_pipeline().fit(bazowy_uczacy[CECHY_WEJSCIOWE], bazowy_uczacy["odejdzie_90d"].astype(int))
    kalibratory = {
        metoda: CalibratedClassifierCV(FrozenEstimator(bazowy), method=metoda).fit(
            walidacja[CECHY_WEJSCIOWE], walidacja["odejdzie_90d"].astype(int)
        )
        for metoda in ("sigmoid", "isotonic")
    }
    X_test = testowy[CECHY_WEJSCIOWE]
    wyniki_testu = {
        "przed": pd.Series(bazowy.predict_proba(X_test)[:, 1], index=testowy.index),
        "platt": pd.Series(kalibratory["sigmoid"].predict_proba(X_test)[:, 1], index=testowy.index),
        "izotoniczna": pd.Series(kalibratory["isotonic"].predict_proba(X_test)[:, 1], index=testowy.index),
    }
    prognozy_brier = {
        "stala_3_5": pd.Series(STALA, index=testowy.index),
        "przed": wyniki_testu["przed"],
        "platt": wyniki_testu["platt"],
        "izotoniczna": wyniki_testu["izotoniczna"],
    }
    brier = porownanie_brier(
        y,
        prognozy_brier,
        testowy["id_biura"],
        [("platt", "izotoniczna"), ("platt", "stala_3_5"), ("izotoniczna", "stala_3_5")],
    )
    izotoniczny = kalibratory["isotonic"].calibrated_classifiers_[0].calibrators[0]

    def opis_zbioru(df: pd.DataFrame) -> dict:
        return {
            "snapszoty": f"{df['t0'].min():%Y-%m} – {df['t0'].max():%Y-%m}",
            "wiersze": len(df),
            "jedynki": int(df["odejdzie_90d"].sum()),
        }

    wynik = {
        "wersja": model.wersja,
        "model": "artefakty/model.joblib v3_katalog, bez ponownego uczenia",
        "prog": {
            "snapszot": f"{SNAPSZOT:%Y-%m-%d}",
            "prog": PROG,
            "biura": len(snap),
            "odejscia": int(snap["odejdzie_90d"].sum()),
            "wybrane": len(wybrane),
            "wybrane_odeszly": int(wybrane["odejdzie_90d"].sum()),
            "precyzja": round(float(wybrane["odejdzie_90d"].mean()), 4),
            "czulosc": round(float(wybrane["odejdzie_90d"].sum() / snap["odejdzie_90d"].sum()), 4),
            "srednie_p_wybranych": round(float(wybrane["p"].mean()), 4),
            "suma_p": round(float(snap["p"].sum()), 1),
            "po_snapszotach_testu": po_snapszotach,
        },
        "kalibracja": {
            "test": f"t0 {testowy['t0'].min():%Y-%m} – {testowy['t0'].max():%Y-%m}, {len(testowy)} wierszy, "
            f"{int(y.sum())} odejść",
            "auc": round(float(roc_auc_score(y, p)), 4),
            "brier": round(float(brier_score_loss(y, p)), 4),
            "brier_stala_stopa": round(float(brier_score_loss(y, np.full(len(y), y.mean()))), 4),
            "srednie_p": round(float(p.mean()), 4),
            "odsetek_odejsc": round(float(y.mean()), 4),
            "przedzialy": _tabela_json(tab),
        },
        "uczenie_odsetek_odejsc": round(float(uczacy["odejdzie_90d"].mean()), 4),
        "kalibracja_platt_izotoniczna": {
            "model_bazowy": "Pipeline v3 (zbuduj_pipeline, class_weight=balanced) uczony od nowa na t0 z oknem "
            "etykiety przed walidacją",
            "uczenie_bazowego": opis_zbioru(bazowy_uczacy),
            "walidacja": opis_zbioru(walidacja),
            "test": opis_zbioru(testowy),
            "kalibrator": "CalibratedClassifierCV(FrozenEstimator(bazowy), method=sigmoid | isotonic)",
            "prog_oplacalnosci": round(prog_zysku, 4),
            "stala_stopa_z_walidacji": {
                "p": round(float(walidacja["odejdzie_90d"].mean()), 4),
                "brier": round(float(brier_score_loss(y, np.full(len(y), walidacja["odejdzie_90d"].mean()))), 4),
                "log_loss": round(float(log_loss(y, np.full(len(y), walidacja["odejdzie_90d"].mean()))), 4),
            },
            "odejscia_walidacji": odejscia_walidacji(walidacja),
            "brier_test": brier,
            "izotoniczna_schodki": {
                "progi_kalibratora": len(izotoniczny.X_thresholds_),
                "rozne_wyniki_na_tescie": int(wyniki_testu["izotoniczna"].nunique()),
            },
            "stabilnosc": stabilnosc(bazowy, walidacja, testowy, brier["brier"]["stala_3_5"]),
            "v3_katalog_artefakt": miary(testowy, p, prog_zysku),
            **{nazwa: miary(testowy, wyn, prog_zysku) for nazwa, wyn in wyniki_testu.items()},
        },
    }
    (EVALS / "kalibracja.json").write_text(json.dumps(wynik, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(wynik, ensure_ascii=False, indent=2))

    wierszy = f"{len(testowy):,}".replace(",", " ")
    opis = f"Test: t0 2025-10 – 2026-04, {wierszy} wierszy biuro × miesiąc, {int(y.sum())} odejść"
    fig = wykres(tab, opis)
    fig.savefig(EVALS / "kalibracja.png", dpi=150, facecolor=TLO)
    plt.close(fig)

    tytuly = {"przed": "Przed kalibracją (model bazowy)", "platt": "Platt (sigmoid)", "izotoniczna": "Izotoniczna"}
    fig = wykres_przed_po({tytuly[k]: tabela_kalibracji(y, v) for k, v in wyniki_testu.items()}, opis)
    fig.savefig(EVALS / "kalibracja_przed_po.png", dpi=150, facecolor=TLO)
    plt.close(fig)


if __name__ == "__main__":
    main()
