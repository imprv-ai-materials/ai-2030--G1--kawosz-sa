"""Aktywny model churnu: wersja z current.yaml, wczytana przez kontrakt ChurnModel (base.py).

Kod, który potrzebuje prognoz (kalkulator wizyt, poniedziałkowa lista opiekunów), bierze model stąd, a nie
importuje konkretnej wersji: zmiana `wersja` w current.yaml przełącza wszystkie miejsca naraz.
"""

import importlib
from pathlib import Path

import yaml

from api.ai.churn_model.base import ChurnModel

KATALOG = Path(__file__).parent


def wersja() -> str:
    """Nazwa folderu aktywnej wersji w versions/ (current.yaml)."""
    return yaml.safe_load((KATALOG / "current.yaml").read_text())["wersja"]


def wczytaj() -> ChurnModel:
    """Model aktywnej wersji z versions/<wersja>/artefakty. Pakiet wersji eksportuje klasę modelu w __all__."""
    w = wersja()
    pakiet = importlib.import_module(f"api.ai.churn_model.versions.{w}")
    klasa = getattr(pakiet, pakiet.__all__[0])
    assert issubclass(klasa, ChurnModel), f"{klasa.__name__} z versions/{w} nie implementuje ChurnModel"
    model = klasa.load(KATALOG / "versions" / w / "artefakty")
    assert model.wersja == w, f"current.yaml wskazuje {w}, a artefakt to {model.wersja}"
    return model
