"""Aktywny model: wersja z current.yaml, wczytana przez kontrakt ChurnModel."""

import yaml

from api.ai.churn_model import aktywny
from api.ai.churn_model.base import ChurnModel


def test_aktywny_model_to_wersja_z_current_yaml_przez_kontrakt():
    wersja = yaml.safe_load((aktywny.KATALOG / "current.yaml").read_text())["wersja"]
    model = aktywny.wczytaj()
    assert aktywny.wersja() == wersja == model.wersja
    assert isinstance(model, ChurnModel)
