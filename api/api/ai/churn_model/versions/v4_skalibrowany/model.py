"""v4_skalibrowany: Pipeline v3_katalog z kalibracją Platta, żeby wynik był P(odejście w 90 dni).

v3 uczy się z class_weight="balanced" i przeszacowuje ryzyko średnio 3 razy (evals/kalibracja.md). Wzór na zysk z
wizyty p × s × V − C (docs/macierz_wartosci.md) potrzebuje prawdziwego prawdopodobieństwa. fit() dostaje zbiór uczący
(wiersze cechy_treningowe z kolumną t0) i sam dzieli go w czasie:

1. walidacja: ostatnie MIESIACE_WALIDACJI snapszotów zbioru uczącego;
2. model bazowy: Pipeline v3 (zbuduj_pipeline, bez zmian) uczony na t0, których okno etykiety [t0, t0 + 90 dni)
   kończy się przed walidacją. Ta sama zasada co foldy w v3_katalog/trenuj.py: etykiety bazowego nie opisują odejść
   z okresu walidacji;
3. kalibracja Platta: CalibratedClassifierCV(FrozenEstimator(bazowy), method="sigmoid") uczony na walidacji. Sigmoid
   dostaje surowy wynik LightGBM (decision_function = logit p) i jest rosnący, więc kolejność biur i AUC zostają
   takie jak w modelu bazowym.

Platt, a nie izotoniczna: na walidacji odchodzi tylko 87 biur, za mało na krzywą schodkową (evals/kalibracja.md,
sekcja 6).
"""

import json
from pathlib import Path

import joblib
import lightgbm as lgb
import pandas as pd
import sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.pipeline import Pipeline

from api.ai.churn_model.base import ChurnModel
from api.ai.churn_model.versions.v3_katalog.model import CECHY_WEJSCIOWE, KATEGORYCZNE, PARAMETRY, zbuduj_pipeline
from api.ai.features.build import RODZINY

OKNO_ETYKIETY = pd.Timedelta(days=90)
MIESIACE_WALIDACJI = 3


def podzial_kalibracji(t0: pd.Series) -> tuple[pd.Series, pd.Series]:
    """(bazowy, walidacja) jako maski wierszy: walidacja to ostatnie MIESIACE_WALIDACJI snapszotów, bazowy to t0
    z oknem etykiety przed walidacją."""
    t0 = pd.to_datetime(t0)
    poczatek = t0.max().to_period("M").to_timestamp() - pd.DateOffset(months=MIESIACE_WALIDACJI - 1)
    return t0 + OKNO_ETYKIETY <= poczatek, t0 >= poczatek


class ModelSkalibrowany(ChurnModel):
    wersja = "v4_skalibrowany"
    cechy = CECHY_WEJSCIOWE

    def __init__(self, kalibrowany: CalibratedClassifierCV | None = None, okresy: dict | None = None):
        self.kalibrowany = kalibrowany
        self.okresy = okresy or {}

    @property
    def bazowy(self) -> Pipeline:
        """Pipeline v3 przed kalibracją (ten sam obiekt, którego wyniki kalibruje Platt)."""
        return self.kalibrowany.calibrated_classifiers_[0].estimator.estimator

    @property
    def platt(self) -> dict:
        """Parametry sigmoidu: p = 1 / (1 + exp(a × logit_bazowy + b))."""
        kalibrator = self.kalibrowany.calibrated_classifiers_[0].calibrators[0]
        return {"a": float(kalibrator.a_), "b": float(kalibrator.b_)}

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "ModelSkalibrowany":
        if "t0" not in X:
            raise ValueError("v4_skalibrowany dzieli zbiór uczący w czasie: X musi mieć kolumnę t0")
        bazowy, walidacja = podzial_kalibracji(X["t0"])
        if not bazowy.any() or not walidacja.any():
            raise ValueError("za krótki zbiór uczący: brak wierszy dla modelu bazowego albo walidacji")
        y = y.astype(int)
        pipeline = zbuduj_pipeline().fit(X.loc[bazowy, self.cechy], y[bazowy])
        self.kalibrowany = CalibratedClassifierCV(FrozenEstimator(pipeline), method="sigmoid").fit(
            X.loc[walidacja, self.cechy], y[walidacja]
        )
        t0 = pd.to_datetime(X["t0"])
        self.okresy = {
            nazwa: {
                "snapszoty": f"{t0[maska].min():%Y-%m} – {t0[maska].max():%Y-%m}",
                "wiersze": int(maska.sum()),
                "jedynki": int(y[maska].sum()),
            }
            for nazwa, maska in (("bazowy", bazowy), ("walidacja", walidacja))
        }
        return self

    def predict_proba(self, X: pd.DataFrame) -> pd.Series:
        p = self.kalibrowany.predict_proba(X[self.cechy])[:, 1]
        return pd.Series(p, index=X.index, name="p_odejdzie_90d")

    def predict_proba_bazowy(self, X: pd.DataFrame) -> pd.Series:
        """Wynik modelu bazowego przed kalibracją (do porównania kolejności i kalibracji)."""
        p = self.bazowy.predict_proba(X[self.cechy])[:, 1]
        return pd.Series(p, index=X.index, name="p_bazowy")

    def save(self, katalog: Path) -> None:
        katalog.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.kalibrowany, katalog / "model.joblib")
        meta = {
            "wersja": self.wersja,
            "cechy": self.cechy,
            "rodziny": list(RODZINY),
            "kategoryczne": KATEGORYCZNE,
            "kroki": [nazwa for nazwa, _ in self.bazowy.steps] + ["kalibracja_platt"],
            "lgbm": PARAMETRY,
            "kalibracja": {"metoda": "sigmoid (Platt) na decision_function modelu bazowego", **self.platt},
            "okresy": self.okresy,
            # model.joblib to pickle: wczytuj tymi samymi wersjami bibliotek
            "wersje": {"scikit-learn": sklearn.__version__, "lightgbm": lgb.__version__},
        }
        (katalog / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")

    @classmethod
    def load(cls, katalog: Path) -> "ModelSkalibrowany":
        meta = json.loads((katalog / "meta.json").read_text())
        return cls(joblib.load(katalog / "model.joblib"), meta.get("okresy"))
