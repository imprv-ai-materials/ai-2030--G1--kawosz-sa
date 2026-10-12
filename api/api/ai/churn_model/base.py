"""Kontrakt modelu churnu: P(odejdzie_90d = 1) dla wiersza biuro × snapszot.

Każda wersja w versions/<wersja>/ implementuje ChurnModel. Reszta kodu zależy od tego kontraktu, a nie od wersji.
Zmienna celu i populacja: docs/target.md (tabela snapshoty).
"""

from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd


class ChurnModel(ABC):
    """Model churnu: P(odejdzie_90d = 1) dla wiersza biuro × snapszot."""

    wersja: str
    cechy: list[str]  # kolumny wejściowe, których model używa z X

    @abstractmethod
    def fit(self, X: pd.DataFrame, y: pd.Series) -> "ChurnModel":
        """Uczy model na X[cechy] i etykiecie y (0/1). Zwraca self."""

    @abstractmethod
    def predict_proba(self, X: pd.DataFrame) -> pd.Series:
        """P(odejście w 90 dni), indeks = X.index."""

    @abstractmethod
    def save(self, katalog: Path) -> None:
        """Zapisuje model do katalogu (model.txt + meta.json)."""

    @classmethod
    @abstractmethod
    def load(cls, katalog: Path) -> "ChurnModel":
        """Wczytuje model zapisany przez save()."""
