"""v0_agencja: odtworzenie modelu agencji. LightGBM z domyślnymi parametrami na gotowej tabeli agencja_features.

Cechy bierzemy bez zmian, łącznie z tymi, które przeciekają z przyszłości (evals/v0_agencja.md). Ta wersja jest punktem odniesienia, a nie modelem do użycia.
"""

import json
from pathlib import Path

import lightgbm as lgb
import pandas as pd

from api.ai.churn_model.base import ChurnModel

KATEGORYCZNE = ["status_crm", "plan", "branza", "miasto"]
CECHY = [
    "status_crm",
    "plan",
    "liczba_pracownikow",
    "branza",
    "miasto",
    "miasto_te",
    "am_id",
    "staz_mies",
    "dni_do_konca_umowy",
    "cena_mies",
    "zaparzenia_30d",
    "trend_zaparzen",
    "bledy_60d",
    "awarie_60d",
    "zgloszenia_odbior_ekspresu",
    "rabat_retencyjny_max",
    "kontakty_am_90d",
    "sr_opoznienie_platnosci",
    "dni_od_ostatniego_zamowienia",
    "nps_ostatni",
]
ZIARNO = 42


class ModelAgencji(ChurnModel):
    wersja = "v0_agencja"
    cechy = CECHY

    def __init__(self, booster: lgb.Booster | None = None):
        self.booster = booster

    def _przygotuj(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X[self.cechy].copy()
        for c in KATEGORYCZNE:
            X[c] = X[c].astype("category")
        return X

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "ModelAgencji":
        klasyfikator = lgb.LGBMClassifier(random_state=ZIARNO, verbose=-1)
        self.booster = klasyfikator.fit(self._przygotuj(X), y).booster_
        return self

    def predict_proba(self, X: pd.DataFrame) -> pd.Series:
        # Booster pamięta kategorie z uczenia (pandas_categorical) i mapuje na nie nowe dane.
        return pd.Series(self.booster.predict(self._przygotuj(X)), index=X.index, name="p_odejdzie_90d")

    def save(self, katalog: Path) -> None:
        katalog.mkdir(parents=True, exist_ok=True)
        self.booster.save_model(katalog / "model.txt")
        meta = {"wersja": self.wersja, "cechy": self.cechy, "kategoryczne": KATEGORYCZNE}
        (katalog / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")

    @classmethod
    def load(cls, katalog: Path) -> "ModelAgencji":
        return cls(lgb.Booster(model_file=katalog / "model.txt"))
