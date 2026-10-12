"""v2_bez_przeciekow: LightGBM z domyślnymi parametrami, jak v0_agencja, ale na cechach bez przecieków.

Cechy liczy api/ai/features/cechy_snapszotu.sql na stan z dnia snapszotu. Usunięte są 4 cechy, które powstają po
wypowiedzeniu, a dni_do_konca_umowy zastępuje dni_do_rocznicy (docs/przecieki.md, sekcje 7–8). miasto_te model
liczy sam, tylko na zbiorze uczącym (api/ai/features/kodowanie_celu.py). Parametry LightGBM są te same co w v0,
więc różnica AUC wynika z cech.
"""

import json
from pathlib import Path

import lightgbm as lgb
import pandas as pd

from api.ai.churn_model.base import ChurnModel
from api.ai.features.kodowanie_celu import KodowanieCelu

KATEGORYCZNE = ["plan", "branza", "miasto"]
CECHY_WEJSCIOWE = [
    "plan",
    "liczba_pracownikow",
    "branza",
    "miasto",
    "am_id",
    "staz_mies",
    "dni_do_rocznicy",
    "cena_mies",
    "zaparzenia_30d",
    "trend_zaparzen",
    "bledy_60d",
    "awarie_60d",
    "kontakty_am_90d",
    "sr_opoznienie_platnosci",
    "dni_od_ostatniego_zamowienia",
    "nps_ostatni",
]
ZIARNO = 42
PARAMETRY = {"random_state": ZIARNO, "verbose": -1}  # poza tym domyślne LightGBM, jak w v0_agencja


class ModelBezPrzeciekow(ChurnModel):
    wersja = "v2_bez_przeciekow"
    cechy = CECHY_WEJSCIOWE

    def __init__(self, booster: lgb.Booster | None = None, kodowanie_miasta: KodowanieCelu | None = None):
        self.booster = booster
        self.kodowanie_miasta = kodowanie_miasta

    def _przygotuj(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X[self.cechy].copy()
        for c in self.cechy:
            # duckdb oddaje tekst jako string, a liczby z brakami jako Int64; LightGBM chce category i float
            X[c] = X[c].astype(object).astype("category") if c in KATEGORYCZNE else X[c].astype("float64")
        return X

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "ModelBezPrzeciekow":
        biura = X["id_biura"] if "id_biura" in X else pd.Series(X.index, index=X.index)
        self.kodowanie_miasta = KodowanieCelu()
        Xp = self._przygotuj(X)
        Xp["miasto_te"] = self.kodowanie_miasta.fit_transform(X["miasto"], y, grupy=biura)
        self.booster = lgb.LGBMClassifier(**PARAMETRY).fit(Xp, y).booster_
        return self

    def predict_proba(self, X: pd.DataFrame) -> pd.Series:
        Xp = self._przygotuj(X)
        Xp["miasto_te"] = self.kodowanie_miasta.transform(X["miasto"])
        # Booster pamięta kategorie z uczenia (pandas_categorical) i mapuje na nie nowe dane.
        return pd.Series(self.booster.predict(Xp), index=X.index, name="p_odejdzie_90d")

    def save(self, katalog: Path) -> None:
        katalog.mkdir(parents=True, exist_ok=True)
        self.booster.save_model(katalog / "model.txt")
        meta = {
            "wersja": self.wersja,
            "cechy": self.cechy,
            "kategoryczne": KATEGORYCZNE,
            "kodowanie_miasta": self.kodowanie_miasta.do_slownika(),
        }
        (katalog / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")

    @classmethod
    def load(cls, katalog: Path) -> "ModelBezPrzeciekow":
        meta = json.loads((katalog / "meta.json").read_text())
        return cls(lgb.Booster(model_file=katalog / "model.txt"), KodowanieCelu.ze_slownika(meta["kodowanie_miasta"]))
