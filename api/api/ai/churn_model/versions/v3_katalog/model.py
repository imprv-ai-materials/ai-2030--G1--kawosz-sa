"""v3_katalog: jeden Pipeline scikit-learn na cechach z tabeli cechy_treningowe.

Cechy i ich kolejność bierzemy z api/ai/features/katalog.yaml (rodziny z sql/), więc model używa dokładnie tego, co
liczy api/ai/features/build.py, z opóźnieniami dostaw (docs/opoznienia_danych.md). Pipeline:

1. kodowanie kategorii: plan, branza, miasto i am_id → OneHotEncoder (brak to osobna kategoria, kategoria spoza
   uczenia daje same zera); liczby → float, braki zostają NaN;
2. skalowanie: StandardScaler na wszystkich kolumnach (średnia i odchylenie bez braków, braki zostają NaN);
3. LightGBM z class_weight="balanced", poza tym domyślny jak w v0 i v2.

Kodowanie i skalowanie są krokami tego samego obiektu, więc uczą się tylko w fit(), czyli na danych uczących
(w walidacji krzyżowej: na części uczącej każdego foldu). miasto_te z v2 nie ma: kodowanie etykietą zastępuje
one-hot, który etykiety nie widzi.
"""

import json
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import sklearn
import yaml
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

from api.ai.churn_model.base import ChurnModel
from api.ai.features.build import KATALOG_SQL, RODZINY

_KATALOG = yaml.safe_load((KATALOG_SQL.parent / "katalog.yaml").read_text())
CECHY_WEJSCIOWE = [cecha for rodzina in RODZINY for cecha in _KATALOG[rodzina]]
KATEGORYCZNE = ["plan", "branza", "miasto", "am_id"]  # am_id to identyfikator opiekuna, a nie liczba
LICZBOWE = [c for c in CECHY_WEJSCIOWE if c not in KATEGORYCZNE]
ZIARNO = 42
PARAMETRY = {"class_weight": "balanced", "random_state": ZIARNO, "verbose": -1}


def _na_tekst(X: pd.DataFrame) -> pd.DataFrame:
    # duckdb oddaje tekst jako string z pd.NA, a am_id jako liczbę; OneHotEncoder chce obiekty z np.nan jako brakiem.
    # Drugie astype(object): kolumna z samymi brakami (np. jedno biuro bez planu) wyszłaby z map() jako float.
    return X.astype(object).map(lambda v: np.nan if pd.isna(v) else str(v)).astype(object)


def _na_liczby(X: pd.DataFrame) -> pd.DataFrame:
    return X.astype("float64")  # Int64 z pd.NA → float z NaN


def zbuduj_pipeline() -> Pipeline:
    """Nieuczony Pipeline: kodowanie kategorii → skalowanie → LightGBM. Wejście: DataFrame z CECHY_WEJSCIOWE."""
    kodowanie = ColumnTransformer(
        [
            (
                "kategorie",
                Pipeline(
                    [
                        ("na_tekst", FunctionTransformer(_na_tekst, feature_names_out="one-to-one")),
                        ("one_hot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                    ]
                ),
                KATEGORYCZNE,
            ),
            ("liczby", FunctionTransformer(_na_liczby, feature_names_out="one-to-one"), LICZBOWE),
        ],
        verbose_feature_names_out=False,
    )
    return Pipeline(
        [
            ("kodowanie", kodowanie),
            ("skalowanie", StandardScaler()),
            ("lgbm", lgb.LGBMClassifier(**PARAMETRY)),
        ]
    ).set_output(transform="pandas")


def waznosc_cech(pipeline: Pipeline) -> pd.Series:
    """Udział cechy w gain LightGBM; kolumny one-hot kategorii sumujemy z powrotem do cechy."""
    kolumny = pipeline.named_steps["skalowanie"].feature_names_in_
    gain = pd.Series(pipeline.named_steps["lgbm"].booster_.feature_importance("gain"), index=kolumny)
    one_hot = pipeline.named_steps["kodowanie"].named_transformers_["kategorie"].named_steps["one_hot"]
    # get_feature_names_out() podaje kolumny one-hot w kolejności cech i ich kategorii
    cecha = dict(
        zip(one_hot.get_feature_names_out(), (c for c, kat in zip(KATEGORYCZNE, one_hot.categories_) for _ in kat))
    )
    gain = gain.groupby(gain.index.map(lambda kol: cecha.get(kol, kol))).sum()
    return (gain / gain.sum()).sort_values(ascending=False)


class ModelKatalog(ChurnModel):
    wersja = "v3_katalog"
    cechy = CECHY_WEJSCIOWE

    def __init__(self, pipeline: Pipeline | None = None):
        self.pipeline = pipeline

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "ModelKatalog":
        self.pipeline = zbuduj_pipeline().fit(X[self.cechy], y.astype(int))
        return self

    def predict_proba(self, X: pd.DataFrame) -> pd.Series:
        p = self.pipeline.predict_proba(X[self.cechy])[:, 1]
        return pd.Series(p, index=X.index, name="p_odejdzie_90d")

    def save(self, katalog: Path) -> None:
        katalog.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.pipeline, katalog / "model.joblib")
        meta = {
            "wersja": self.wersja,
            "cechy": self.cechy,
            "kategoryczne": KATEGORYCZNE,
            "kroki": [nazwa for nazwa, _ in self.pipeline.steps],
            "lgbm": PARAMETRY,
            # model.joblib to pickle: wczytuj tymi samymi wersjami bibliotek
            "wersje": {"scikit-learn": sklearn.__version__, "lightgbm": lgb.__version__},
        }
        (katalog / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")

    @classmethod
    def load(cls, katalog: Path) -> "ModelKatalog":
        return cls(joblib.load(katalog / "model.joblib"))
