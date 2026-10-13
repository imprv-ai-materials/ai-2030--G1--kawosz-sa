"""v4_skalibrowany: kontrakt ChurnModel, podział zbioru uczącego na bazowy i walidację, Platt bez zmiany kolejności."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from api.ai.churn_model.base import ChurnModel
from api.ai.churn_model.versions.v3_katalog.model import LICZBOWE
from api.ai.churn_model.versions.v3_katalog.trenuj import podzial_czasowy
from api.ai.churn_model.versions.v4_skalibrowany import ModelSkalibrowany
from api.ai.churn_model.versions.v4_skalibrowany.model import OKNO_ETYKIETY, podzial_kalibracji

CHURN_MODEL = Path(__file__).parents[3] / "api" / "ai" / "churn_model"


@pytest.fixture
def dane() -> tuple[pd.DataFrame, pd.Series]:
    """Zbiór uczący jak z cechy_treningowe: miesięczne t0 2024-04 – 2025-07, około 4% odejść."""
    rng = np.random.default_rng(0)
    t0 = pd.Series(pd.date_range("2024-04-01", "2025-07-01", freq="MS")).repeat(300).reset_index(drop=True)
    n = len(t0)
    X = pd.DataFrame({c: rng.normal(size=n) for c in LICZBOWE})
    X["nps_ostatni"] = pd.array(rng.integers(0, 11, n), dtype="Int64")
    X["plan"] = pd.array(rng.choice(["S", "M", "L"], n), dtype="string")
    X["branza"] = pd.array(rng.choice(["Bank", "Gaming"], n), dtype="string")
    X["miasto"] = pd.array(rng.choice(["Poznań", "Kraków"], n), dtype="string")
    X["am_id"] = rng.integers(1, 4, n)
    X["t0"] = t0
    ryzyko = 1 / (1 + np.exp(-(-3.5 - 1.5 * X["dni_do_rocznicy"])))
    y = pd.Series((rng.random(n) < ryzyko).astype(int), index=X.index)
    return X, y


def test_spelnia_kontrakt_i_kalibruje_metoda_platta(dane):
    X, y = dane
    model = ModelSkalibrowany().fit(X, y)

    p = model.predict_proba(X)

    assert isinstance(model, ChurnModel)
    assert model.kalibrowany.method == "sigmoid"
    assert model.bazowy.named_steps["lgbm"].class_weight == "balanced"
    assert p.index.equals(X.index)
    assert p.between(0, 1).all()


def test_walidacja_to_ostatnie_3_miesiace_a_bazowy_ma_etykiety_sprzed_walidacji(dane):
    X, _ = dane

    bazowy, walidacja = podzial_kalibracji(X["t0"])

    assert sorted(X.loc[walidacja, "t0"].unique()) == list(pd.to_datetime(["2025-05-01", "2025-06-01", "2025-07-01"]))
    assert (X.loc[bazowy, "t0"] + OKNO_ETYKIETY).max() <= X.loc[walidacja, "t0"].min()
    assert X.loc[bazowy, "t0"].max() == pd.Timestamp("2025-01-01")


def test_na_zbiorze_uczacym_v3_daje_okresy_z_kalibracja_md():
    t0 = pd.Series(pd.date_range("2024-04-01", "2026-06-01", freq="MS"))
    uczacy, _ = podzial_czasowy(pd.DataFrame({"t0": t0}))

    bazowy, walidacja = podzial_kalibracji(uczacy["t0"])

    assert (uczacy.loc[bazowy, "t0"].min(), uczacy.loc[bazowy, "t0"].max()) == (
        pd.Timestamp("2024-04-01"),
        pd.Timestamp("2025-01-01"),
    )
    assert (uczacy.loc[walidacja, "t0"].min(), uczacy.loc[walidacja, "t0"].max()) == (
        pd.Timestamp("2025-05-01"),
        pd.Timestamp("2025-07-01"),
    )


def test_kalibracja_nie_zmienia_kolejnosci(dane):
    X, y = dane
    model = ModelSkalibrowany().fit(X, y)

    przed, po = model.predict_proba_bazowy(X), model.predict_proba(X)

    pd.testing.assert_series_equal(przed.rank(), po.rank(), check_names=False)
    assert model.platt["a"] < 0  # p = 1 / (1 + exp(a × logit + b)) rośnie z wynikiem bazowym


def test_kalibracja_obniza_zawyzony_wynik_bazowego(dane):
    X, y = dane
    model = ModelSkalibrowany().fit(X, y)

    assert model.predict_proba(X).mean() < model.predict_proba_bazowy(X).mean()


def test_zapis_i_odczyt_daja_te_same_predykcje(dane, tmp_path):
    X, y = dane
    model = ModelSkalibrowany().fit(X, y)
    model.save(tmp_path)

    wczytany = ModelSkalibrowany.load(tmp_path)

    pd.testing.assert_series_equal(wczytany.predict_proba(X), model.predict_proba(X))
    assert wczytany.okresy == model.okresy


def test_bez_kolumny_t0_przerywa(dane):
    X, y = dane

    with pytest.raises(ValueError, match="t0"):
        ModelSkalibrowany().fit(X.drop(columns="t0"), y)


def test_aktywna_wersja_w_current_yaml_ma_zapisany_model():
    aktywna = yaml.safe_load((CHURN_MODEL / "current.yaml").read_text())["wersja"]
    folder = CHURN_MODEL / "versions" / aktywna

    assert aktywna == "v4_skalibrowany"
    assert (folder / "artefakty" / "model.joblib").exists()
    assert ModelSkalibrowany.load(folder / "artefakty").wersja == aktywna
