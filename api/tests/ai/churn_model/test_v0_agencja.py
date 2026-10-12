"""v0_agencja spełnia kontrakt ChurnModel: predykcje z indeksem X, te same po zapisie i odczycie, nowe kategorie."""

import numpy as np
import pandas as pd
import pytest

from api.ai.churn_model.base import ChurnModel
from api.ai.churn_model.versions.v0_agencja import ModelAgencji
from api.ai.churn_model.versions.v0_agencja.model import CECHY, KATEGORYCZNE


@pytest.fixture
def dane() -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(0)
    n = 400
    X = pd.DataFrame({c: rng.normal(size=n) for c in CECHY if c not in KATEGORYCZNE})
    X["status_crm"] = rng.choice(["aktywny", "zakończony"], n)
    X["plan"] = rng.choice(["S", "M", "L", "XL"], n)
    X["branza"] = rng.choice(["Bank", "Gaming"], n)
    X["miasto"] = rng.choice(["Poznań", "Kraków"], n)
    X["id_biura"] = np.arange(n)  # kolumna spoza cech: model ma ją pominąć
    X.index = X.index + 1000
    y = pd.Series((X["dni_do_konca_umowy"] < -0.5).astype(int), index=X.index)
    return X, y


def test_spelnia_kontrakt(dane):
    X, y = dane
    model = ModelAgencji().fit(X, y)

    p = model.predict_proba(X)

    assert isinstance(model, ChurnModel)
    assert p.index.equals(X.index)
    assert p.between(0, 1).all()


def test_zapis_i_odczyt_daja_te_same_predykcje(dane, tmp_path):
    X, y = dane
    model = ModelAgencji().fit(X, y)
    model.save(tmp_path)

    wczytany = ModelAgencji.load(tmp_path)

    pd.testing.assert_series_equal(wczytany.predict_proba(X), model.predict_proba(X))
    assert (tmp_path / "meta.json").exists()


def test_kategorie_mapowane_jak_przy_uczeniu(dane):
    # Pojedynczy wiersz ma tylko jedną kategorię; bez mapowania na kategorie z uczenia kod kategorii byłby inny.
    X, y = dane
    model = ModelAgencji().fit(X, y)

    pojedyncze = pd.concat([model.predict_proba(X.iloc[[i]]) for i in range(20)])

    pd.testing.assert_series_equal(pojedyncze, model.predict_proba(X.iloc[:20]))
