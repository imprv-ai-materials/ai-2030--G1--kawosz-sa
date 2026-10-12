"""Reguła opiekunów (punkt odniesienia): biuro jest zagrożone, jeśli umowa kończy się w ciągu 90 dni, a zaparzenia
z 30 dni są o ponad 30% niższe od średniej z 90 dni.

„Średnia z 90 dni” to średnia 30-dniowa suma z 90 dni, czyli zaparzenia_90d / 3. Reguła się nie uczy i zwraca 0 albo 1.
Cechy liczy cechy.sql.
"""

import json
from pathlib import Path

import pandas as pd

from api.ai.churn_model.base import ChurnModel

DNI_DO_KONCA = 90
SPADEK = 0.30


class RegulaOpiekunow(ChurnModel):
    wersja = "regula_opiekunow"
    cechy = ["dni_do_konca_okresu", "zaparzenia_30d_iot", "zaparzenia_90d_iot"]

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "RegulaOpiekunow":
        return self

    def predict_proba(self, X: pd.DataFrame) -> pd.Series:
        konczy_sie = X["dni_do_konca_okresu"] < DNI_DO_KONCA
        spadek = X["zaparzenia_30d_iot"] < (1 - SPADEK) * X["zaparzenia_90d_iot"] / 3
        return (konczy_sie & spadek).astype(float).rename("p_odejdzie_90d")

    def save(self, katalog: Path) -> None:
        katalog.mkdir(parents=True, exist_ok=True)
        meta = {"wersja": self.wersja, "cechy": self.cechy, "dni_do_konca": DNI_DO_KONCA, "spadek": SPADEK}
        (katalog / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")

    @classmethod
    def load(cls, katalog: Path) -> "RegulaOpiekunow":
        return cls()
