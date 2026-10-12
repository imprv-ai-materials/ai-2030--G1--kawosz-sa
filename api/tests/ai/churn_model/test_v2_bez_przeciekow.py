"""v2_bez_przeciekow spełnia kontrakt ChurnModel na cechach z cechy_snapszotu.sql, z miasto_te liczonym w modelu."""

import numpy as np
import pandas as pd
import pytest

from api.ai.churn_model.base import ChurnModel
from api.ai.churn_model.versions.v2_bez_przeciekow import ModelBezPrzeciekow
from api.ai.churn_model.versions.v2_bez_przeciekow.model import CECHY_WEJSCIOWE, KATEGORYCZNE


@pytest.fixture
def dane() -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(0)
    n = 400
    X = pd.DataFrame({c: rng.normal(size=n) for c in CECHY_WEJSCIOWE if c not in KATEGORYCZNE})
    X["nps_ostatni"] = pd.array(rng.integers(0, 11, n), dtype="Int64")  # cechy z duckdb bywają nullable
    X.loc[::7, "nps_ostatni"] = pd.NA
    X["plan"] = pd.array(rng.choice(["S", "M", "L", "XL"], n), dtype="string")
    X["branza"] = pd.array(rng.choice(["Bank", "Gaming"], n), dtype="string")
    X["miasto"] = pd.array(rng.choice(["Poznań", "Kraków", "Gdańsk"], n), dtype="string")
    X["id_biura"] = np.arange(n) // 4  # 4 snapszoty na biuro
    X.index = X.index + 1000
    y = pd.Series((X["dni_do_rocznicy"] < -0.5).astype(int), index=X.index)
    return X, y


def test_spelnia_kontrakt(dane):
    X, y = dane
    model = ModelBezPrzeciekow().fit(X, y)

    p = model.predict_proba(X)

    assert isinstance(model, ChurnModel)
    assert p.index.equals(X.index)
    assert p.between(0, 1).all()
    assert "miasto_te" not in model.cechy  # kontrakt: cechy to kolumny z X; miasto_te liczy model
    assert "miasto_te" in model.booster.feature_name()


def test_zapis_i_odczyt_daja_te_same_predykcje(dane, tmp_path):
    X, y = dane
    model = ModelBezPrzeciekow().fit(X, y)
    model.save(tmp_path)

    wczytany = ModelBezPrzeciekow.load(tmp_path)

    pd.testing.assert_series_equal(wczytany.predict_proba(X), model.predict_proba(X))


def test_miasto_spoza_uczenia_nie_przerywa_predykcji(dane):
    X, y = dane
    model = ModelBezPrzeciekow().fit(X, y)
    nowe = X.iloc[:3].copy()
    nowe["miasto"] = "Szczecin"

    assert model.predict_proba(nowe).notna().all()
