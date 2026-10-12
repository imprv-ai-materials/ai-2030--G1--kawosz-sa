"""Kodowanie kategorii średnią etykiety (target encoding) uczone wyłącznie na zbiorze uczącym.

Agencja policzyła miasto_te na wszystkich wierszach, także testowych (docs/przecieki.md, sekcja 6.5). Tutaj:
- wiersze uczące dostają wartość policzoną bez swojego foldu, a foldy dzielą po biurach, bo to samo biuro jest w
  kilku snapszotach i jego etykiety się powtarzają;
- nowe dane dostają średnią z całego zbioru uczącego, a kategoria spoza uczenia średnią ogólną.
"""

import pandas as pd
from sklearn.model_selection import GroupKFold

FOLDY = 5


class KodowanieCelu:
    def __init__(self, srednie: dict | None = None, srednia_ogolna: float | None = None):
        self.srednie = srednie or {}
        self.srednia_ogolna = srednia_ogolna

    def fit_transform(self, kategoria: pd.Series, y: pd.Series, grupy: pd.Series) -> pd.Series:
        """Uczy się na (kategoria, y) i zwraca kodowanie wierszy uczących poza ich foldem."""
        kategoria, y, grupy = kategoria.astype(object), y.to_numpy(), grupy.to_numpy()
        wynik = pd.Series(float("nan"), index=kategoria.index)
        for uczace, oceniane in GroupKFold(n_splits=FOLDY).split(kategoria, y, grupy):
            srednie = pd.Series(y[uczace]).groupby(kategoria.iloc[uczace].to_numpy()).mean()
            wynik.iloc[oceniane] = (
                kategoria.iloc[oceniane].map(srednie).astype(float).fillna(y[uczace].mean()).to_numpy()
            )
        self.srednie = pd.Series(y).groupby(kategoria.to_numpy()).mean().to_dict()
        self.srednia_ogolna = float(y.mean())
        return wynik

    def transform(self, kategoria: pd.Series) -> pd.Series:
        return kategoria.astype(object).map(self.srednie).astype(float).fillna(self.srednia_ogolna)

    def do_slownika(self) -> dict:
        return {"srednie": {str(k): float(v) for k, v in self.srednie.items()}, "srednia_ogolna": self.srednia_ogolna}

    @classmethod
    def ze_slownika(cls, d: dict) -> "KodowanieCelu":
        return cls(d["srednie"], d["srednia_ogolna"])
