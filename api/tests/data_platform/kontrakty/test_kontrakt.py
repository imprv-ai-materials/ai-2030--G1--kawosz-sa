"""Kontrakty: pliki YAML są poprawne, reguły biorą z nich opis i poziom, a błąd w kontrakcie zatrzymuje wczytanie."""

import copy

import pytest
import yaml
from pydantic import ValidationError

from api.data_platform import load_raw
from api.data_platform.kontrakty.kontrakt import KATALOG, Kontrakt, wczytaj
from api.data_platform.reguly import ecom, erp, pos

MODULY = {"pos_paragony": pos, "ecom_zamowienia": ecom, "erp_faktury": erp}


@pytest.mark.parametrize("nazwa", MODULY)
def test_reguly_wynikaja_z_kontraktu(nazwa):
    """Każda reguła źródła jest w kontrakcie i odwrotnie; opis, poziom, właściciel i skala pochodzą z kontraktu."""
    kontrakt, modul = wczytaj(nazwa), MODULY[nazwa]
    assert set(kontrakt.reguly) == {r.id for r in modul.REGULY}
    for regula in modul.REGULY:
        z_kontraktu = kontrakt.reguly[regula.id]
        assert regula.opis == kontrakt.opis_reguly(regula.id)
        assert (regula.poziom, regula.wlasciciel, regula.skala, regula.jednostka) == (
            z_kontraktu.poziom,
            z_kontraktu.wlasciciel,
            tuple(z_kontraktu.skala),
            z_kontraktu.jednostka,
        )


def test_progi_i_slowniki_z_kontraktu():
    assert pos.CENA_RECZNA_MAX == 500 and "500 zł" in pos.POS_06.opis
    assert pos.METODY_PLATNOSCI == wczytaj("pos_paragony").kolumna("metoda_platnosci").dozwolone
    assert erp.STAWKI_VAT_INDEKSOW == {"20.01.0001": 5}
    assert ecom.PLANY == {"miesięczny": 39.0, "roczny": 399.0}


def test_kolumna_kontraktu_w_pandera():
    kontrakt = wczytaj("pos_paragony")
    storno = kontrakt.kolumna("storno").pandera()
    assert str(storno.dtype) == "int32" and not storno.nullable
    assert [c.name for c in storno.checks] == ["isin"]
    # opcjonalna: dopuszcza braki, może jej nie być, a typ fizyczny konwertujemy
    stornowany = kontrakt.kolumna("nr_paragonu_stornowanego").pandera()
    assert str(stornowany.dtype) == "Int64" and stornowany.nullable and not stornowany.required and stornowany.coerce
    assert [c.name for c in stornowany.checks] == ["in_range"]


def _surowy(nazwa: str) -> dict:
    with (KATALOG / f"{nazwa}.yaml").open(encoding="utf-8") as plik:
        return yaml.safe_load(plik)


def _bez_kodowania(k):
    del k["dostawa"]["kodowanie"]


def _opcjonalna_w_srodku(k):
    k["kolumny"].insert(0, {**k["kolumny"].pop(), "nazwa": "nowa"})


PSUCIA = [
    pytest.param(lambda k: k["kolumny"][0].update(typ="TEXT"), "nieznany typ TEXT", id="nieznany typ"),
    pytest.param(lambda k: k["kolumny"][0].update(dozwolne=[1]), "dozwolne", id="literowka w kluczu"),
    pytest.param(lambda k: k.update(wlasciciel="Dział IT"), "wlasciciel", id="wlasciciel spoza listy"),
    pytest.param(lambda k: k.update(wersja="1.1.0"), "ostatni wpis w historii", id="wersja bez wpisu w historii"),
    pytest.param(lambda k: k.update(wersja="1.1"), "GŁÓWNA.PODRZĘDNA.POPRAWKA", id="wersja bez poprawki"),
    pytest.param(_bez_kodowania, "dostawa CSV wymaga", id="CSV bez kodowania"),
    pytest.param(_opcjonalna_w_srodku, "na końcu listy", id="kolumna opcjonalna przed wymagana"),
    pytest.param(lambda k: k["reguly"]["POS-07"].update(kolumny=["metoda"]), "kolumny spoza kontraktu", id="regula"),
    pytest.param(lambda k: k["reguly"]["POS-06"]["parametry"].pop("max_sztuk"), "max_sztuk", id="opis bez parametru"),
]


@pytest.mark.parametrize("psucie, komunikat", PSUCIA)
def test_bledny_kontrakt_nie_wczyta_sie(psucie, komunikat):
    kontrakt = copy.deepcopy(_surowy("pos_paragony"))
    Kontrakt.model_validate(kontrakt)  # bez zmian jest poprawny
    psucie(kontrakt)
    with pytest.raises(ValidationError, match=komunikat):
        Kontrakt.model_validate(kontrakt)


@pytest.mark.parametrize(
    "plik, lokal, dzien",
    [
        ("pos_paragony_17_2026-09-11.csv", 17, "2026-09-11"),
        ("pos_paragony_17_2026-09-11 (1).csv", 17, "2026-09-11"),  # kopię rozpoznajemy, nazwę zgłasza POS-03
    ],
)
def test_lokal_i_dzien_z_nazwy_pliku(plik, lokal, dzien):
    nazwa = load_raw.wzorzec_pliku(wczytaj("pos_paragony").dostawa.plik).match(plik)
    assert (int(nazwa["lokal"]), nazwa["dzien"]) == (lokal, dzien)


def test_rejestr_plikow_czyta_naglowek_wg_kontraktu(tmp_path):
    (tmp_path / "pos_paragony_3_2026-06-01.csv").write_bytes(
        "lokal;nr_paragonu;data_czas;kanal;kwota_brutto;metoda_platnosci;storno\r\n"
        "3;2606010001;2026-06-01 07:12:01;sala;34,00;gotówka;0\r\n".encode("cp1250")
    )
    [(plik, lokal, dzien, kolumny, wiersze, czas_dostawy)] = load_raw.rejestr_plikow(tmp_path)
    assert (plik, lokal, str(dzien), wiersze) == ("pos_paragony_3_2026-06-01.csv", 3, "2026-06-01", 1)
    assert czas_dostawy is None  # archiwum nie wie, kiedy plik dotarł
    assert kolumny == ["lokal", "nr_paragonu", "data_czas", "kanal", "kwota_brutto", "metoda_platnosci", "storno"]


def test_typy_tylko_dla_kolumn_kontraktu_obecnych_w_plikach():
    """Typ dla kolumny, której nie ma w żadnym pliku, DuckDB odrzuca; kolumnę spoza kontraktu rozpoznaje sam."""
    assert load_raw.typy_paragonow({"lokal", "kanal", "kwota_brutto"}) == {
        "lokal": "INTEGER",
        "kwota_brutto": "DECIMAL(12,2)",
    }
