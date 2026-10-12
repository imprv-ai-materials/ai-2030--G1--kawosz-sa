"""v3_katalog: kontrakt ChurnModel, jeden Pipeline i kodowanie/skalowanie uczone tylko na części uczącej foldu."""

import numpy as np
import pandas as pd
import pytest
import yaml
from sklearn.model_selection import cross_validate
from sklearn.pipeline import Pipeline

from api.ai.churn_model.base import ChurnModel
from api.ai.churn_model.versions.v3_katalog import ModelKatalog
from api.ai.churn_model.versions.v3_katalog.model import CECHY_WEJSCIOWE, KATEGORYCZNE, LICZBOWE, zbuduj_pipeline
from api.ai.churn_model.versions.v3_katalog.trenuj import OKNO_ETYKIETY, foldy_czasowe, podzial_czasowy
from api.ai.features.build import KATALOG_SQL, RODZINY


@pytest.fixture
def dane() -> tuple[pd.DataFrame, pd.Series]:
    """Wiersze jak z cechy_treningowe: miesięczne t0 2024-04 – 2026-04, typy z duckdb (string, Int64 z brakami)."""
    rng = np.random.default_rng(0)
    t0 = pd.Series(pd.date_range("2024-04-01", "2026-04-01", freq="MS")).repeat(40).reset_index(drop=True)
    n = len(t0)
    X = pd.DataFrame({c: rng.normal(size=n) for c in LICZBOWE})
    X["nps_ostatni"] = pd.array(rng.integers(0, 11, n), dtype="Int64")
    X.loc[::7, "nps_ostatni"] = pd.NA
    X["plan"] = pd.array(rng.choice(["S", "M", "L", "XL"], n), dtype="string")
    X.loc[::11, "plan"] = pd.NA
    X["branza"] = pd.array(rng.choice(["Bank", "Gaming"], n), dtype="string")
    X["miasto"] = pd.array(rng.choice(["Poznań", "Kraków", "Gdańsk"], n), dtype="string")
    X["am_id"] = rng.integers(1, 4, n)
    X["id_biura"] = np.arange(n) % 40
    X["t0"] = t0
    # miasto, które pojawia się dopiero w ostatnim kwartale: w foldach wcześniejszych go nie ma
    X.loc[X["t0"] >= "2025-04-01", "miasto"] = X["miasto"].where(rng.random(n) > 0.2, "Łódź")
    y = pd.Series(((X["dni_do_rocznicy"] < -0.5) | (X["miasto"] == "Łódź")).astype(int), index=X.index)
    return X, y


def test_spelnia_kontrakt(dane):
    X, y = dane
    model = ModelKatalog().fit(X, y)

    p = model.predict_proba(X)

    assert isinstance(model, ChurnModel)
    assert isinstance(model.pipeline, Pipeline)
    assert [nazwa for nazwa, _ in model.pipeline.steps] == ["kodowanie", "skalowanie", "lgbm"]
    assert model.pipeline.named_steps["lgbm"].class_weight == "balanced"
    assert p.index.equals(X.index)
    assert p.between(0, 1).all()


def test_cechy_to_katalog_w_kolejnosci_rodzin():
    katalog = yaml.safe_load((KATALOG_SQL.parent / "katalog.yaml").read_text())

    assert CECHY_WEJSCIOWE == [c for rodzina in RODZINY for c in katalog[rodzina]]
    assert set(KATEGORYCZNE) | set(LICZBOWE) == set(CECHY_WEJSCIOWE)


def test_zapis_i_odczyt_daja_te_same_predykcje(dane, tmp_path):
    X, y = dane
    model = ModelKatalog().fit(X, y)
    model.save(tmp_path)

    wczytany = ModelKatalog.load(tmp_path)

    pd.testing.assert_series_equal(wczytany.predict_proba(X), model.predict_proba(X))


def test_kategoria_spoza_uczenia_i_braki_nie_przerywaja_predykcji(dane):
    X, y = dane
    model = ModelKatalog().fit(X, y)
    nowe = X.iloc[:3].copy()
    nowe["miasto"] = "Szczecin"
    nowe["plan"] = pd.array([pd.NA] * 3, dtype="string")
    nowe["am_id"] = 99

    assert model.predict_proba(nowe).notna().all()


def test_foldy_ucza_sie_tylko_na_snapszotach_z_etykieta_przed_walidacja(dane):
    X, _ = dane
    uczacy, _ = podzial_czasowy(X)

    for uczace, walidacyjne in foldy_czasowe(uczacy["t0"]):
        t0 = uczacy["t0"].reset_index(drop=True)
        assert len(uczace) and len(walidacyjne)
        assert (t0.iloc[uczace] + OKNO_ETYKIETY).max() <= t0.iloc[walidacyjne].min()


def test_kodowanie_i_skalowanie_ucza_sie_tylko_na_czesci_uczacej_kazdego_foldu(dane):
    X, y = dane
    uczacy, _ = podzial_czasowy(X)
    Xu, yu = uczacy[CECHY_WEJSCIOWE].reset_index(drop=True), y.loc[uczacy.index].reset_index(drop=True)
    foldy = foldy_czasowe(uczacy["t0"])

    wynik = cross_validate(zbuduj_pipeline(), Xu, yu, cv=foldy, scoring="roc_auc", return_estimator=True)

    nowe_miasto_tylko_w_walidacji = 0
    for pipeline, (uczace, walidacyjne) in zip(wynik["estimator"], foldy):
        czesc = Xu.iloc[uczace]
        one_hot = pipeline.named_steps["kodowanie"].named_transformers_["kategorie"].named_steps["one_hot"]
        miasta = list(one_hot.categories_[KATEGORYCZNE.index("miasto")])
        assert miasta == sorted(czesc["miasto"].unique())
        nowe_miasto_tylko_w_walidacji += "Łódź" in set(Xu.iloc[walidacyjne]["miasto"]) and "Łódź" not in miasta
        skaler = pipeline.named_steps["skalowanie"]
        kolumny = list(skaler.feature_names_in_)
        for cecha in ["staz_mies", "nps_ostatni"]:
            assert skaler.mean_[kolumny.index(cecha)] == pytest.approx(czesc[cecha].astype(float).mean())
    assert nowe_miasto_tylko_w_walidacji == 1  # ostatni fold: Łódź jest w walidacji, a kodowanie jej nie zna


def test_podzial_czasowy_jak_w_v2(dane):
    X, _ = dane

    uczacy, testowy = podzial_czasowy(X)

    assert (uczacy["t0"].min(), uczacy["t0"].max()) == (pd.Timestamp("2024-04-01"), pd.Timestamp("2025-07-01"))
    assert (testowy["t0"].min(), testowy["t0"].max()) == (pd.Timestamp("2025-10-01"), pd.Timestamp("2026-04-01"))
