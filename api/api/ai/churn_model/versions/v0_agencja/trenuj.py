"""Trening i ocena v0_agencja tak jak u agencji: agencja_features ⋈ snapshoty, losowy podział wierszy 80/20.

Dane i podział: zbior_agencji.py. Model trafia do artefakty/, AUC i ważność cech do artefakty/ocena.json, a całość
do MLflow (eksperyment churn, run v0_agencja). Wymaga serwera: poetry run pypyr start_mlflow.

    PYTHONPATH=api poetry run python -m api.ai.churn_model.versions.v0_agencja.trenuj
"""

import json
from pathlib import Path

import lightgbm as lgb
import pandas as pd
from sklearn.metrics import roc_auc_score

from api.ai.churn_model.rejestr import loguj_wersje, wykres_waznosci
from api.ai.churn_model.versions.v0_agencja.model import KATEGORYCZNE, PARAMETRY, ModelAgencji
from api.ai.churn_model.zbior_agencji import SPOSOB_OCENY, ZIARNO, dane, podzial

WERSJA = Path(__file__).parent.name
ARTEFAKTY = Path(__file__).parent / "artefakty"


def main() -> None:
    df = dane()
    uczacy, testowy = podzial(df)

    model = ModelAgencji().fit(uczacy, uczacy["odejdzie_90d"])
    model.save(ARTEFAKTY)
    model = ModelAgencji.load(ARTEFAKTY)  # oceniamy to, co zapisane
    assert model.wersja == WERSJA, "wersja modelu musi się nazywać jak folder w versions/"
    auc = roc_auc_score(testowy["odejdzie_90d"], model.predict_proba(testowy))

    gain = pd.Series(model.booster.feature_importance("gain"), index=model.booster.feature_name())
    udzial = (gain / gain.sum()).sort_values(ascending=False)
    ocena = {
        "wersja": model.wersja,
        "sposob_oceny": SPOSOB_OCENY,
        "wiersze": len(df),
        "wiersze_uczace": len(uczacy),
        "wiersze_testowe": len(testowy),
        "odsetek_jedynek": round(float(df["odejdzie_90d"].mean()), 4),
        "auc": round(float(auc), 4),
        "waznosc_gain": {k: round(float(v), 4) for k, v in udzial.items()},
    }
    (ARTEFAKTY / "ocena.json").write_text(json.dumps(ocena, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(ocena, ensure_ascii=False, indent=2))

    parametry = {
        "zbior": "agencja_features ⋈ snapshoty",
        "podzial_seed": ZIARNO,
        "podzial_test": 0.2,
        "wiersze_uczace": len(uczacy),
        "wiersze_testowe": len(testowy),
        "liczba_cech": len(model.cechy),
        "cechy_kategoryczne": ",".join(KATEGORYCZNE),
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
        {"auc": float(auc)},
        wykres,
        ARTEFAKTY,
        opis="Odtworzenie modelu agencji. AUC zawyżone przez przeciek dni_do_konca_umowy "
        "i losowy podział (evals/v0_agencja.md).",
    )
    print(f"MLflow: run {run_id}")


if __name__ == "__main__":
    main()
