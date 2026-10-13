"""Powody ryzyka: opis cechy prostym językiem i wybór cech, które najbardziej podnoszą p biura (przez kontrakt
modelu: tylko predict_proba i lista cech)."""

import math

import pandas as pd
import pytest

from api.contexts_boundaries.retention_bc.radar.powody import opis, powody


@pytest.mark.parametrize(
    "cecha, wartosc, tekst",
    [
        ("trend_zaparzen", 0.55, "zaparzenia −45% w ostatnim miesiącu"),
        ("trend_zaparzen", 1.3, "zaparzenia +30% w ostatnim miesiącu"),
        ("trend_zaparzen", math.nan, "brak zaparzeń w poprzednim miesiącu"),
        ("awarie_60d", 1, "1 awaria w 60 dni"),
        ("awarie_60d", 3, "3 awarie w 60 dni"),
        ("awarie_60d", 5, "5 awarii w 60 dni"),
        ("bledy_60d", 22, "22 błędy ekspresu w 60 dni"),
        ("zaparzenia_30d", 1250, "1 250 zaparzeń w 30 dni"),
        ("zaparzenia_30d", 0, "brak zaparzeń w ostatnich 30 dniach"),
        ("dni_od_ostatniego_zamowienia", 47, "47 dni od ostatniego zamówienia kawy"),
        ("dni_od_ostatniego_zamowienia", math.nan, "brak zamówień kawy"),
        ("sr_opoznienie_platnosci", 12.4, "płaci średnio 12 dni po terminie"),
        ("sr_opoznienie_platnosci", -3, "płaci średnio 3 dni przed terminem"),
        ("kontakty_am_90d", 0, "brak kontaktu z opiekunem od 90 dni"),
        ("kontakty_am_90d", 2, "2 kontakty z opiekunem w 90 dni"),
        ("nps_ostatni", 4, "NPS 4/10"),
        ("nps_ostatni", math.nan, "brak odpowiedzi w ankiecie NPS"),
        ("dni_do_rocznicy", 21, "odnowienie umowy za 21 dni"),
        ("staz_mies", 7.6, "klient od 8 mies."),
        ("cena_mies", 3227.24, "abonament 3 227 zł/mies."),
        ("plan", "S", "pakiet S"),
        ("branza", "Coworking", "branża: Coworking"),
        ("nowa_cecha", 1.5, "nowa_cecha: 1.5"),
    ],
)
def test_opis_cechy_prostym_jezykiem(cecha, wartosc, tekst):
    assert opis(cecha, wartosc) == tekst


def test_przy_zaparzeniach_opis_podaje_typowe_biuro():
    assert opis("zaparzenia_30d", 31, typowa=1240.5) == "31 zaparzeń w 30 dni (typowo 1 240)"


class ModelLiniowy:
    """p rośnie z awariami, spadkiem zaparzeń, niskim NPS i u opiekuna 2; liczba pracowników nie ma wpływu."""

    wersja = "testowa"
    cechy = ["awarie_60d", "trend_zaparzen", "nps_ostatni", "am_id", "liczba_pracownikow"]

    def predict_proba(self, X: pd.DataFrame) -> pd.Series:
        return (
            0.05
            + 0.05 * X["awarie_60d"]
            + 0.2 * (1 - X["trend_zaparzen"]).clip(lower=0)
            + 0.05 * (8 - X["nps_ostatni"].fillna(8)).clip(lower=0) / 4
            + 0.1 * (X["am_id"] == 2)
        )


@pytest.fixture
def populacja() -> pd.DataFrame:
    """Typowe biuro: 0 awarii, zaparzenia bez zmian, NPS 8, opiekun 1, 50 pracowników."""
    return pd.DataFrame({
        "awarie_60d": [0, 0, 0, 1, 2],
        "trend_zaparzen": [1.0, 1.0, 0.9, 1.1, 1.0],
        "nps_ostatni": [8, 8, 9, 7, 8],
        "am_id": [1, 1, 1, 2, 3],
        "liczba_pracownikow": [50, 50, 40, 60, 50],
    })


def test_powody_to_cechy_najbardziej_podnoszace_p_od_najwiekszego_wplywu(populacja):
    biura = pd.DataFrame({
        "awarie_60d": [3, 0],
        "trend_zaparzen": [0.55, 1.2],
        "nps_ostatni": [4, 9],
        "am_id": [2, 2],
        "liczba_pracownikow": [200, 50],
    })
    wynik = powody(ModelLiniowy(), biura, populacja)
    # wpływ: awarie 3 × 0,05 = 0,15; spadek zaparzeń 0,45 × 0,2 = 0,09; NPS 4 zamiast 8: 0,05; opiekun pominięty
    assert wynik[0] == ["3 awarie w 60 dni", "zaparzenia −45% w ostatnim miesiącu", "NPS 4/10"]
    assert wynik[1] == []  # nic nie podnosi ryzyka ponad typowe biuro (opiekuna nie liczymy)


def test_powod_musi_podnosic_p_o_co_najmniej_pol_punktu_procentowego(populacja):
    biura = pd.DataFrame({
        "awarie_60d": [1],
        "trend_zaparzen": [0.99],  # wpływ 0,002: za mały, żeby był powodem
        "nps_ostatni": [8],
        "am_id": [1],
        "liczba_pracownikow": [50],
    })
    assert powody(ModelLiniowy(), biura, populacja) == [["1 awaria w 60 dni"]]
