"""Kodowanie średnią etykiety: uczy się tylko na zbiorze uczącym, a wiersz uczący nie widzi etykiety swojego biura."""

import pandas as pd
import pytest

from api.ai.features.kodowanie_celu import KodowanieCelu


@pytest.fixture
def uczacy() -> tuple[pd.Series, pd.Series, pd.Series]:
    # Miasto X: jedno biuro (7) w 3 snapszotach, zawsze odchodzi. Miasto Y: 10 biur po 2 wiersze, nikt nie odchodzi.
    miasto = pd.Series(["X"] * 3 + ["Y"] * 20)
    biuro = pd.Series([7] * 3 + [b for b in range(10) for _ in range(2)])
    y = pd.Series([1] * 3 + [0] * 20)
    return miasto, y, biuro


def test_wiersz_uczacy_nie_widzi_etykiety_swojego_biura(uczacy):
    miasto, y, biuro = uczacy

    te = KodowanieCelu().fit_transform(miasto, y, grupy=biuro)

    # Bez foldów po biurach X dostałoby 1,0, czyli własną etykietę. Poza foldem biura 7 jedynek nie ma.
    assert te[:3].tolist() == [0.0, 0.0, 0.0]
    assert te.index.equals(miasto.index)


def test_nowe_dane_kodowane_srednia_z_calego_zbioru_uczacego(uczacy):
    miasto, y, biuro = uczacy
    kodowanie = KodowanieCelu()
    kodowanie.fit_transform(miasto, y, grupy=biuro)

    te = kodowanie.transform(pd.Series(["Y", "X", "Z"], index=[5, 6, 7]))

    assert te.tolist() == pytest.approx([0.0, 1.0, 3 / 23])  # Z: miasta nie było w uczeniu → średnia ogólna
    assert te.index.tolist() == [5, 6, 7]


def test_odtworzone_ze_slownika_koduje_tak_samo(uczacy):
    miasto, y, biuro = uczacy
    kodowanie = KodowanieCelu()
    kodowanie.fit_transform(miasto, y, grupy=biuro)

    odtworzone = KodowanieCelu.ze_slownika(kodowanie.do_slownika())

    pd.testing.assert_series_equal(odtworzone.transform(miasto), kodowanie.transform(miasto))
