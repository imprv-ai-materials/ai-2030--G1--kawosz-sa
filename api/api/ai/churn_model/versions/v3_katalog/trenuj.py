"""Trening i ocena v3_katalog na tabeli cechy_treningowe, z tym samym podziałem w czasie co v2_bez_przeciekow.

Podział (v2: trenuj.py, auc_podzial_czasowy): uczenie na t0 od 2024-04 do ostatniego snapszotu, którego okno etykiety
[t0, t0 + 90 dni) kończy się przed 2025-10-01 (czyli do 2025-07), test na t0 2025-10 – 2026-04. v2 brała z tych
miesięcy tylko wiersze agencji (kwartalne), a v3 bierze wszystkie miesięczne wiersze cechy_treningowe.

W części uczącej jest walidacja krzyżowa w czasie (cross_validate, 3 foldy kwartalne). Każdy fold uczy się na
snapszotach, których okno etykiety kończy się przed foldem. cross_validate klonuje Pipeline i uczy go od nowa na
części uczącej foldu, więc kodowanie i skalowanie nie widzą foldu walidacyjnego.

Porównanie z v2 na jej własnych wierszach (klucze agencji, ten sam podział) rozdziela zmianę AUC na dwa kroki:
v2 na cechach cechy_snapszotu.sql → v2 na cechach z cechy_treningowe (przeniesienie cech z opóźnieniami dostaw) →
v3 na cechach z cechy_treningowe (nowy Pipeline). Model trafia do artefakty/, wynik do artefakty/ocena.json i do
MLflow (eksperyment churn, run v3_katalog). Wymaga tabeli cechy_treningowe (python -m api.ai.features.build) i
serwera MLflow (poetry run pypyr start_mlflow).

    PYTHONPATH=api poetry run python -m api.ai.churn_model.versions.v3_katalog.trenuj
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import cross_validate

from api.adapters.duckdb_conn import connect
from api.ai.churn_model.ocena_w_czasie import przedzial_bootstrap
from api.ai.churn_model.rejestr import loguj_wersje, wykres_waznosci
from api.ai.churn_model.versions.v2_bez_przeciekow import ModelBezPrzeciekow
from api.ai.churn_model.versions.v2_bez_przeciekow.trenuj import z_cechami
from api.ai.churn_model.versions.v3_katalog.model import (
    CECHY_WEJSCIOWE,
    KATEGORYCZNE,
    ModelKatalog,
    waznosc_cech,
    zbuduj_pipeline,
)
from api.ai.churn_model.zbior_agencji import dane as dane_agencji
from api.ai.features.cechy import cechy_snapszotu

WERSJA = Path(__file__).parent.name
ARTEFAKTY = Path(__file__).parent / "artefakty"
OKNO_ETYKIETY = pd.Timedelta(days=90)
POCZATEK_UCZENIA = pd.Timestamp("2024-04-01")  # pierwszy snapszot agencji, od niego uczyła się v2
POCZATEK_TESTU = pd.Timestamp("2025-10-01")  # jak POCZATEK_TESTU_CZASOWEGO w v2
KONIEC_TESTU = pd.Timestamp("2026-04-01")  # ostatni snapszot agencji, na nim kończył się test v2
POCZATKI_FOLDOW = [pd.Timestamp("2024-10-01"), pd.Timestamp("2025-01-01"), pd.Timestamp("2025-04-01")]
SPOSOB_OCENY = (
    "podział w czasie jak w v2: uczenie na t0 2024-04 – 2025-07 (okno etykiety kończy się przed 2025-10-01), "
    "test na t0 2025-10 – 2026-04; wszystkie miesięczne wiersze cechy_treningowe"
)


def podzial_czasowy(df: pd.DataFrame, kolumna: str = "t0") -> tuple[pd.DataFrame, pd.DataFrame]:
    """(uczący, testowy) według daty snapszotu, jak w v2."""
    t0 = pd.to_datetime(df[kolumna])
    uczacy = (t0 >= POCZATEK_UCZENIA) & (t0 + OKNO_ETYKIETY <= POCZATEK_TESTU)
    testowy = (t0 >= POCZATEK_TESTU) & (t0 <= KONIEC_TESTU)
    return df[uczacy], df[testowy]


def foldy_czasowe(t0: pd.Series) -> list[tuple[np.ndarray, np.ndarray]]:
    """Foldy dla cross_validate (pozycje wierszy): walidacja to kwartał od POCZATKI_FOLDOW, uczenie to snapszoty,
    których okno etykiety kończy się przed tym kwartałem."""
    t0 = pd.to_datetime(t0).reset_index(drop=True)
    konce = POCZATKI_FOLDOW[1:] + [t0.max() + pd.Timedelta(days=1)]
    return [
        (np.flatnonzero(t0 + OKNO_ETYKIETY <= poczatek), np.flatnonzero((t0 >= poczatek) & (t0 < koniec)))
        for poczatek, koniec in zip(POCZATKI_FOLDOW, konce)
    ]


def _auc(model, uczacy: pd.DataFrame, testowy: pd.DataFrame) -> float:
    model.fit(uczacy, uczacy["odejdzie_90d"])
    return round(float(roc_auc_score(testowy["odejdzie_90d"], model.predict_proba(testowy))), 4)


def porownanie_z_v2(treningowe: pd.DataFrame, snapszoty: pd.DataFrame) -> dict:
    """AUC na wierszach i podziale v2 (klucze agencji): ile zmienia przeniesienie cech, a ile nowy Pipeline."""
    agencja = dane_agencji()
    agencja["data_migawki"] = pd.to_datetime(agencja["data_migawki"])
    z_tabeli = treningowe.drop(columns="odejdzie_90d").rename(columns={"t0": "data_snapszotu"})
    stare = z_cechami(agencja, snapszoty)
    nowe = z_cechami(agencja, z_tabeli)
    assert nowe["dni_do_rocznicy"].notna().all(), "wiersze agencji bez cech w cechy_treningowe"
    w_tescie = stare["data_migawki"] >= POCZATEK_TESTU  # podział z v2/trenuj.py
    return {
        "wiersze": "klucze agencji: uczenie 2024-04 – 2025-07, test 2025-10 – 2026-04 (kwartalne)",
        "wiersze_uczace": int((~w_tescie).sum()),
        "wiersze_testowe": int(w_tescie.sum()),
        "v2_cechy_snapszotu": _auc(ModelBezPrzeciekow(), stare[~w_tescie], stare[w_tescie]),
        "v2_cechy_treningowe": _auc(ModelBezPrzeciekow(), nowe[~w_tescie], nowe[w_tescie]),
        "v3_cechy_treningowe": _auc(ModelKatalog(), nowe[~w_tescie], nowe[w_tescie]),
    }


def main() -> None:
    con = connect(read_only=True)
    try:
        treningowe = con.sql("SELECT * FROM cechy_treningowe").df()
        snapszoty = cechy_snapszotu(con)
    finally:
        con.close()
    treningowe["t0"] = pd.to_datetime(treningowe["t0"])
    snapszoty["data_snapszotu"] = pd.to_datetime(snapszoty["data_snapszotu"])
    uczacy, testowy = podzial_czasowy(treningowe)

    walidacja = cross_validate(
        zbuduj_pipeline(), uczacy[CECHY_WEJSCIOWE], uczacy["odejdzie_90d"], cv=foldy_czasowe(uczacy["t0"]),
        scoring="roc_auc",
    )
    auc_foldow = [round(float(a), 4) for a in walidacja["test_score"]]

    model = ModelKatalog().fit(uczacy, uczacy["odejdzie_90d"])
    model.save(ARTEFAKTY)
    model = ModelKatalog.load(ARTEFAKTY)  # oceniamy to, co zapisane
    assert model.wersja == WERSJA, "wersja modelu musi się nazywać jak folder w versions/"
    p = model.predict_proba(testowy)
    auc = float(roc_auc_score(testowy["odejdzie_90d"], p))
    dol, gora = przedzial_bootstrap(testowy["odejdzie_90d"], p, testowy["id_biura"])
    auc_v2_te_same_wiersze = _auc(ModelBezPrzeciekow(), uczacy, testowy)

    udzial = waznosc_cech(model.pipeline)
    ocena = {
        "wersja": model.wersja,
        "sposob_oceny": SPOSOB_OCENY,
        "auc": round(auc, 4),
        "auc_95": [round(dol, 4), round(gora, 4)],
        "uczenie": {
            "snapszoty": f"{uczacy['t0'].min():%Y-%m} – {uczacy['t0'].max():%Y-%m}",
            "wiersze": len(uczacy),
            "jedynki": int(uczacy["odejdzie_90d"].sum()),
        },
        "test": {
            "snapszoty": f"{testowy['t0'].min():%Y-%m} – {testowy['t0'].max():%Y-%m}",
            "wiersze": len(testowy),
            "jedynki": int(testowy["odejdzie_90d"].sum()),
        },
        "walidacja_krzyzowa": {
            "foldy": [f"{p:%Y-%m}" for p in POCZATKI_FOLDOW],
            "auc": auc_foldow,
            "srednia": round(float(np.mean(auc_foldow)), 4),
        },
        "v2_na_tych_samych_wierszach": auc_v2_te_same_wiersze,
        "porownanie_z_v2_na_jej_wierszach": porownanie_z_v2(treningowe, snapszoty),
        "waznosc_gain": {k: round(float(v), 4) for k, v in udzial.items()},
        "bootstrap": "1000 losowań biur ze zwracaniem, ziarno 42",
    }
    (ARTEFAKTY / "ocena.json").write_text(json.dumps(ocena, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(ocena, ensure_ascii=False, indent=2))

    parametry = {
        "zbior": "cechy_treningowe (ai/features/build.py, sql/ i katalog.yaml), etykieta odejdzie_90d ze snapshoty",
        "pipeline": " → ".join(nazwa for nazwa, _ in model.pipeline.steps),
        "kodowanie": f"OneHotEncoder(handle_unknown='ignore') na {','.join(KATEGORYCZNE)}",
        "skalowanie": "StandardScaler na wszystkich kolumnach",
        "liczba_cech": len(CECHY_WEJSCIOWE),
        "wiersze_uczace": len(uczacy),
        "wiersze_testowe": len(testowy),
        "podzial_czasowy_od": f"{POCZATEK_TESTU:%Y-%m-%d}",
        "foldy_walidacji": ",".join(f"{p:%Y-%m}" for p in POCZATKI_FOLDOW),
        **{f"lgbm_{k}": v for k, v in model.pipeline.named_steps["lgbm"].get_params().items()},
    }
    porownanie = ocena["porownanie_z_v2_na_jej_wierszach"]
    metryki = {
        "auc": auc,
        "auc_walidacja_srednia": ocena["walidacja_krzyzowa"]["srednia"],
        "auc_v2_na_tych_samych_wierszach": auc_v2_te_same_wiersze,
        **{f"auc_wiersze_v2_{k}": v for k, v in porownanie.items() if k.startswith("v")},
    }
    wykres = wykres_waznosci(
        udzial,
        tytul=f"{WERSJA}: ważność cech (udział w gain, one-hot zsumowany)",
        os_x="udział w sumie gain",
        format_wartosci="{:.1%}",
    )
    run_id = loguj_wersje(
        WERSJA,
        SPOSOB_OCENY,
        parametry,
        metryki,
        wykres,
        ARTEFAKTY,
        opis="Jeden Pipeline scikit-learn (one-hot → StandardScaler → LightGBM class_weight=balanced) na cechach "
        "z cechy_treningowe, z opóźnieniami dostaw (docs/opoznienia_danych.md, evals/v3_katalog.md).",
    )
    print(f"MLflow: run {run_id}")


if __name__ == "__main__":
    main()
