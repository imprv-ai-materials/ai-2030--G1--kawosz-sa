"""Krzywa wartości progu: rachunek trafionych i zbędnych wizyt, top n, wybór najlepszego progu, bootstrap,
aktywny model."""

import numpy as np
import pandas as pd
import pytest

from api.contexts_boundaries.retention_bc.prog.krzywa_wartosci import (
    aktywny_model,
    krzywa_wartosci,
    najlepszy,
    plan_w_scenariuszu,
    prog_czy_budzet,
    top_n,
    wynik_wizyt,
    zyski_bootstrap,
    zalozenia,
)

# s × V − C = 0,5 × 10 000 − 1 000 = 4 000 zł za trafioną wizytę, 1 000 zł za zbędną
S, V, C = 0.5, 10_000, 1_000


@pytest.fixture
def biura() -> tuple[pd.Series, pd.Series]:
    """Pięć biur: odeszły te z p 0,9 i 0,4."""
    p = pd.Series([0.9, 0.6, 0.4, 0.2, 0.1], index=list("abcde"))
    y = pd.Series([1, 0, 1, 0, 0], index=list("abcde"))
    return p, y


def test_trafiona_daje_s_razy_V_minus_C_a_zbedna_kosztuje_C(biura):
    p, y = biura
    w = wynik_wizyt(p, y, S, V, C)
    assert (w["wizyty"], w["trafione"], w["zbedne"]) == (5, 2, 3)
    assert w["zysk"] == 2 * 4_000 - 3 * 1_000
    assert w["zysk_oczekiwany"] == pytest.approx((0.9 + 0.6 + 0.4 + 0.2 + 0.1) * 5_000 - 5 * 1_000)


def test_krzywa_jedzie_do_biur_z_p_co_najmniej_rownym_progowi(biura):
    p, y = biura
    k = krzywa_wartosci(p, y, [0.1, 0.4, 0.5, 0.95], S, V, C).set_index("prog")
    assert k["wizyty"].tolist() == [5, 3, 2, 0]
    assert k.loc[0.4, "zysk"] == 2 * 4_000 - 1 * 1_000
    assert k.loc[0.5, "zysk"] == 4_000 - 1_000
    assert k.loc[0.95, "zysk"] == 0


def test_najlepszy_prog_przy_remisie_wybiera_wyzszy():
    k = pd.DataFrame({"prog": [0.1, 0.2, 0.3], "wizyty": [9, 5, 1], "trafione": [2, 2, 0], "zbedne": [7, 3, 1],
                      "zysk": [10.0, 10.0, -1.0], "zysk_oczekiwany": [0.0, 0.0, 0.0]})
    assert najlepszy(k)["prog"] == 0.2


def test_top_n_bierze_n_biur_z_najwyzszym_p(biura):
    p, y = biura
    top = top_n(p, y, 3, S, V, C)
    assert (top["wizyty"], top["trafione"], top["prog_p"]) == (3, 2, 0.4)
    assert top["zysk"] == 2 * 4_000 - 1_000


def test_budzet_doklada_wizyty_ponizej_progu(biura):
    p, y = biura
    w = prog_czy_budzet(p, y, 0.5, 4, S, V, C)  # próg: a, b; budżet: a, b, c, d
    assert (w["wizyty_prog"], w["dodatkowe_wizyty"], w["dodatkowe_trafione"]) == (2, 2, 1)
    assert w["zysk_prog"] == 4_000 - 1_000
    assert w["dodatkowe_zysk"] == 4_000 - 1_000
    assert w["dodatkowe_zysk_oczekiwany"] == pytest.approx((0.4 + 0.2) * 5_000 - 2 * 1_000)


def test_budzet_mniejszy_niz_liczba_biur_nad_progiem_przycina_wizyty(biura):
    p, y = biura
    w = prog_czy_budzet(p, y, 0.1, 2, S, V, C)
    assert (w["wizyty_prog"], w["dodatkowe_wizyty"], w["dodatkowe_p"]) == (2, 0, None)


def test_plan_w_scenariuszu_usrednia_snapszoty_i_dopasowuje_prog():
    # dwa snapszoty po dwa biura; C / (s × V) = 1 000 / 5 000 = 0,2
    dane = pd.DataFrame({"t0": ["2026-01-01"] * 2 + ["2026-02-01"] * 2, "odejdzie_90d": [1, 0, 0, 0]})
    p = pd.Series([0.5, 0.1, 0.3, 0.1], index=dane.index)
    z = {"C": C, "budzet_wizyt": 60}
    w = plan_w_scenariuszu(dane, p, 0.05, z, S, V)
    assert w["prog_oplacalnosci"] == pytest.approx(0.2)
    assert (w["wizyty"], w["zysk"]) == (2, (4_000 - 1_000 - 2 * 1_000) / 2)  # próg 0,05: wszystkie biura
    assert (w["wizyty_dopasowany"], w["zysk_dopasowany"]) == (1, (4_000 - 1_000) / 2)  # próg 0,2: biura 0,5 i 0,3


class StaleLosowanie:
    """Zamiast generatora: każde losowanie daje te same pozycje biur."""

    def __init__(self, pozycje: list[int]):
        self.pozycje = np.array(pozycje)

    def integers(self, low, high, size):
        return self.pozycje


def test_bootstrap_liczy_biuro_tyle_razy_ile_je_wylosowano(biura):
    p, y = biura
    # a dwa razy, b ani razu, c, d, e po razie
    zyski, top = zyski_bootstrap(p, y, [0.3, 0.5, 0.95], S, V, C, 2, StaleLosowanie([0, 0, 2, 3, 4]))
    assert zyski.shape == (1000, 3)
    assert zyski[0].tolist() == [2 * 4_000 + 4_000, 2 * 4_000, 0]
    assert top[0] == 2 * 4_000  # dwie wizyty to dwa wylosowania biura a


def test_bootstrap_top_wszystkich_rowna_sie_progowi_ponizej_min_p(biura):
    p, y = biura
    zyski, top = zyski_bootstrap(p, y, [0.01], S, V, C, len(p), np.random.default_rng(0))
    assert np.array_equal(zyski[:, 0], top)


def test_zalozenia_i_aktywny_model_z_plikow_projektu():
    z = zalozenia()
    assert z["s"] * z["V"] > z["C"] > 0
    model = aktywny_model()
    assert hasattr(model, "predict_proba")
