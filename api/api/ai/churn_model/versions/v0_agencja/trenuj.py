"""Trening i ocena v0_agencja tak jak u agencji: agencja_features ⋈ snapshoty, losowy podział wierszy 80/20.

Etykieta pochodzi z naszej tabeli snapshoty (docs/target.md), a kolumnę odejdzie_90d agencji pomijamy. Na wspólnych
wierszach obie etykiety są identyczne. Model trafia do artefakty/, a AUC i ważność cech do artefakty/ocena.json.

    PYTHONPATH=api poetry run python -m api.ai.churn_model.versions.v0_agencja.trenuj
"""

import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

from api.adapters.duckdb_conn import connect
from api.ai.churn_model.versions.v0_agencja.model import ZIARNO, ModelAgencji

ARTEFAKTY = Path(__file__).parent / "artefakty"
SQL = """
SELECT a.* EXCLUDE (odejdzie_90d), s.odejdzie_90d
FROM agencja_features a
JOIN snapshoty s ON s.id_biura = a.id_biura AND s.data_snapszotu = a.data_migawki
ORDER BY a.data_migawki, a.id_biura
"""


def dane() -> pd.DataFrame:
    con = connect(read_only=True)
    try:
        return con.sql(SQL).df()
    finally:
        con.close()


def main() -> None:
    df = dane()
    y = df["odejdzie_90d"]
    X_tr, X_te, y_tr, y_te = train_test_split(df, y, test_size=0.2, random_state=ZIARNO, stratify=y)

    model = ModelAgencji().fit(X_tr, y_tr)
    model.save(ARTEFAKTY)
    model = ModelAgencji.load(ARTEFAKTY)  # oceniamy to, co zapisane
    auc = roc_auc_score(y_te, model.predict_proba(X_te))

    gain = pd.Series(model.booster.feature_importance("gain"), index=model.booster.feature_name())
    udzial = (gain / gain.sum()).sort_values(ascending=False)
    ocena = {
        "wersja": model.wersja,
        "sposob_oceny": "losowy podział wierszy 80/20, stratyfikowany, random_state=42",
        "wiersze": len(df),
        "wiersze_uczace": len(X_tr),
        "wiersze_testowe": len(X_te),
        "odsetek_jedynek": round(float(y.mean()), 4),
        "auc": round(float(auc), 4),
        "waznosc_gain": {k: round(float(v), 4) for k, v in udzial.items()},
    }
    (ARTEFAKTY / "ocena.json").write_text(json.dumps(ocena, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(ocena, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
