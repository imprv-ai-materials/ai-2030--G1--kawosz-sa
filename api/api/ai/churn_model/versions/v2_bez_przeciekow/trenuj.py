"""Trening i ocena v2_bez_przeciekow na tych samych wierszach i tym samym podziale co v0_agencja.

Z agencja_features bierzemy tylko klucze (id_biura, data_migawki) i etykietę, a cechy liczy
api/ai/features/cechy_snapszotu.sql na stan z dnia snapszotu. Dzięki temu AUC różni się od v0 tylko cechami. Dodatkowo
liczymy AUC przy podziale w czasie (uczenie na snapszotach do 2025-07, test od 2025-10), bo losowy podział wierszy
wpuszcza to samo biuro do obu części. Model trafia do artefakty/, wynik do artefakty/ocena.json i do MLflow
(eksperyment churn, run v2_bez_przeciekow). Wymaga serwera: poetry run pypyr start_mlflow.

    PYTHONPATH=api poetry run python -m api.ai.churn_model.versions.v2_bez_przeciekow.trenuj
"""

import json
from pathlib import Path

import lightgbm as lgb
import pandas as pd
from sklearn.metrics import roc_auc_score

from api.adapters.duckdb_conn import connect
from api.ai.churn_model.rejestr import loguj_wersje, wykres_waznosci
from api.ai.churn_model.versions.v2_bez_przeciekow.model import KATEGORYCZNE, PARAMETRY, ModelBezPrzeciekow
from api.ai.churn_model.zbior_agencji import SPOSOB_OCENY, ZIARNO, dane, podzial
from api.ai.features.cechy import cechy_snapszotu

WERSJA = Path(__file__).parent.name
ARTEFAKTY = Path(__file__).parent / "artefakty"
POCZATEK_TESTU_CZASOWEGO = pd.Timestamp("2025-10-01")  # okna 90 dni snapszotów uczących kończą się przed tą datą


def z_cechami(wiersze: pd.DataFrame, cechy: pd.DataFrame) -> pd.DataFrame:
    klucze = wiersze[["id_biura", "data_migawki", "odejdzie_90d"]]
    return klucze.merge(
        cechy, left_on=["id_biura", "data_migawki"], right_on=["id_biura", "data_snapszotu"], how="left",
        validate="one_to_one",
    ).set_index(klucze.index)


def auc(uczacy: pd.DataFrame, testowy: pd.DataFrame) -> tuple[ModelBezPrzeciekow, float]:
    model = ModelBezPrzeciekow().fit(uczacy, uczacy["odejdzie_90d"])
    return model, float(roc_auc_score(testowy["odejdzie_90d"], model.predict_proba(testowy)))


def main() -> None:
    con = connect(read_only=True)
    try:
        cechy = cechy_snapszotu(con)
    finally:
        con.close()
    cechy["data_snapszotu"] = pd.to_datetime(cechy["data_snapszotu"])
    df = dane()
    df["data_migawki"] = pd.to_datetime(df["data_migawki"])
    uczacy, testowy = (z_cechami(czesc, cechy) for czesc in podzial(df))
    assert uczacy["dni_do_rocznicy"].notna().all() and testowy["dni_do_rocznicy"].notna().all(), "brak cech"

    model = ModelBezPrzeciekow().fit(uczacy, uczacy["odejdzie_90d"])
    model.save(ARTEFAKTY)
    model = ModelBezPrzeciekow.load(ARTEFAKTY)  # oceniamy to, co zapisane
    assert model.wersja == WERSJA, "wersja modelu musi się nazywać jak folder w versions/"
    auc_losowy = roc_auc_score(testowy["odejdzie_90d"], model.predict_proba(testowy))

    wszystkie = z_cechami(df, cechy)
    w_czasie = wszystkie["data_migawki"] >= POCZATEK_TESTU_CZASOWEGO
    _, auc_czasowy = auc(wszystkie[~w_czasie], wszystkie[w_czasie])

    gain = pd.Series(model.booster.feature_importance("gain"), index=model.booster.feature_name())
    udzial = (gain / gain.sum()).sort_values(ascending=False)
    ocena = {
        "wersja": model.wersja,
        "sposob_oceny": SPOSOB_OCENY,
        "wiersze": len(df),
        "wiersze_uczace": len(uczacy),
        "wiersze_testowe": len(testowy),
        "odsetek_jedynek": round(float(df["odejdzie_90d"].mean()), 4),
        "auc": round(float(auc_losowy), 4),
        "auc_podzial_czasowy": round(auc_czasowy, 4),
        "podzial_czasowy": {
            "uczace_snapszoty": f"{wszystkie.loc[~w_czasie, 'data_migawki'].min():%Y-%m} – "
            f"{wszystkie.loc[~w_czasie, 'data_migawki'].max():%Y-%m}",
            "testowe_snapszoty": f"{POCZATEK_TESTU_CZASOWEGO:%Y-%m} – {wszystkie['data_migawki'].max():%Y-%m}",
            "wiersze_uczace": int((~w_czasie).sum()),
            "wiersze_testowe": int(w_czasie.sum()),
            "jedynki_testowe": int(wszystkie.loc[w_czasie, "odejdzie_90d"].sum()),
        },
        "waznosc_gain": {k: round(float(v), 4) for k, v in udzial.items()},
    }
    (ARTEFAKTY / "ocena.json").write_text(json.dumps(ocena, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(ocena, ensure_ascii=False, indent=2))

    parametry = {
        "zbior": "agencja_features ⋈ snapshoty (tylko klucze i etykieta); cechy z ai/features/cechy_snapszotu.sql",
        "podzial_seed": ZIARNO,
        "podzial_test": 0.2,
        "wiersze_uczace": len(uczacy),
        "wiersze_testowe": len(testowy),
        "liczba_cech": len(model.booster.feature_name()),
        "cechy_kategoryczne": ",".join(KATEGORYCZNE),
        "miasto_te": "średnia etykiety w mieście, poza foldem (5 foldów po biurach), tylko zbiór uczący",
        "podzial_czasowy_od": f"{POCZATEK_TESTU_CZASOWEGO:%Y-%m-%d}",
        **{f"lgbm_{k}": v for k, v in lgb.LGBMClassifier(**PARAMETRY).get_params().items()},
    }
    wykres = wykres_waznosci(
        udzial,
        tytul=f"{WERSJA}: ważność cech (udział w gain LightGBM)",
        os_x="udział w sumie gain",
        format_wartosci="{:.1%}",
    )
    run_id = loguj_wersje(
        WERSJA,
        SPOSOB_OCENY,
        parametry,
        {"auc": float(auc_losowy), "auc_podzial_czasowy": auc_czasowy},
        wykres,
        ARTEFAKTY,
        opis="v0_agencja na cechach bez przecieków: 4 cechy usunięte, reszta liczona na dzień snapszotu, "
        "miasto_te tylko na zbiorze uczącym (docs/przecieki.md, evals/v2_bez_przeciekow.md).",
    )
    print(f"MLflow: run {run_id}")


if __name__ == "__main__":
    main()
