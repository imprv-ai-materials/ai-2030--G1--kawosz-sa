"""Scalanie kontrahentów: ujednolicenie nazw, klasy par, mapa stary → nowy ID i niezmienna suma faktur."""

import duckdb
import pandas as pd
import pytest

from api.data_platform import mapa_kontrahentow as mk

KONTRAHENCI = """
CREATE TABLE erp_kontrahenci (
    id_kontrahenta BIGINT, nazwa VARCHAR, nip VARCHAR, adres VARCHAR, kod_pocztowy VARCHAR, id_biura_crm VARCHAR);
INSERT INTO erp_kontrahenci VALUES
    -- pewna: NIP w innym formacie, ta sama nazwa po ujednoliceniu i ten sam kod
    (200001, 'Instytut Garbary Sp. z o.o.', '123-456-32-18', 'ul. Garbary 1', '60-001', '10001'),
    (260001, 'INSTYTUT GARBARY SP Z OO', '1234563218', 'ul. Garbary 1', '60-001', NULL),
    -- pewna: ten sam NIP i kod, nazwa bez słowa „Biuro”
    (200002, 'Biuro Łazarz Sp. j.', '526-025-02-74', 'ul. Długa 2', '60-002', '10002'),
    (260002, 'ŁAZARZ SP J', '5260250274', 'ul. Długa 2', '60-002', NULL),
    -- wątpliwa: ta sama nazwa i kod, NIP bez jednej cyfry
    (200003, 'Kancelaria Aleja Sp. z o.o.', '739-031-90-19', 'ul. Kasprzaka 3', '62-793', '10003'),
    (260003, 'KANCELARIA ALEJA SP Z OO', '739039019', 'ul. Kasprzaka 3', '62-793', NULL),
    -- odrzucona: ta sama nazwa, inny NIP i kod (dwie różne firmy)
    (200004, 'ODRA SP. Z O.O.', '3712144122', 'ul. Marszałkowska 4', '81-516', '10004'),
    (200005, 'Odra spółka z o.o.', '547-004-83-72', 'ul. Śląska 5', '60-863', '10005');
CREATE TABLE erp_kontrahenci_archiwum AS SELECT * FROM erp_kontrahenci LIMIT 0;
INSERT INTO erp_kontrahenci_archiwum VALUES (200006, 'Gamma Sp. j.', '7740001454', 'ul. Stara 6', '60-006', '10006');

CREATE TABLE erp_faktury (
    nr_faktury VARCHAR, id_kontrahenta BIGINT, data DATE, typ VARCHAR, waluta VARCHAR, kwota_netto DOUBLE, vat DOUBLE);
INSERT INTO erp_faktury VALUES
    ('FV/2026/08/00001', 200001, DATE '2026-08-31', 'faktura', 'PLN', 100.0, 23.0),
    ('FV/2026/09/00001', 260001, DATE '2026-09-30', 'faktura', 'PLN', 200.0, 46.0),
    ('FV/2026/09/00002', 200002, DATE '2026-09-30', 'faktura', 'PLN', 300.0, 69.0),
    ('KOR/2026/09/0001', 260002, DATE '2026-09-30', 'korekta', 'PLN', -10.0, -2.3),
    ('FV/2026/09/00003', 260003, DATE '2026-09-30', 'faktura', 'PLN', 400.0, 92.0),
    ('FV/2026/09/00004', 200006, DATE '2026-09-15', 'faktura', 'PLN', 500.0, 115.0);
"""


@pytest.fixture
def baza():
    con = duckdb.connect(":memory:")
    con.execute(KONTRAHENCI)
    con.execute(mk.MAKRA)
    yield con
    con.close()


@pytest.mark.parametrize(
    "a, b",
    [
        ("Instytut Garbary Sp. z o.o.", "INSTYTUT GARBARY SP Z OO"),
        ("Walczak spółka z o.o.", "WALCZAK SP. Z O.O."),
        ("Agencja Jeżyce Spółka Akcyjna", "AGENCJA JEZYCE S.A."),
        ("Wektor Consulting spółka z o.o. Sp. k.", "WEKTOR CONSULTING SP Z OO SPK"),
        ("Łazarz Sp. j.", "LAZARZ SP J"),
        ("Agencja Browar s.c.", "AGENCJA  BROWAR S.C."),
    ],
)
def test_nazwy_tej_samej_firmy_po_ujednoliceniu_sa_rowne(baza, a, b):
    assert baza.execute("SELECT nazwa_ujednolicona(?) = nazwa_ujednolicona(?)", [a, b]).fetchone()[0]


@pytest.mark.parametrize("a, b", [("Omega S.A.", "Omega Sp. z o.o."), ("Kopernik Sp. k.", "Kopernik Sp. j.")])
def test_inna_forma_prawna_to_inna_nazwa(baza, a, b):
    assert not baza.execute("SELECT nazwa_ujednolicona(?) = nazwa_ujednolicona(?)", [a, b]).fetchone()[0]


def test_klasy_par(baza):
    p = mk.pary(baza)
    assert dict(zip(zip(p["id_a"], p["id_b"]), p["klasa"])) == {
        (200001, 260001): "pewna",
        (200002, 260002): "pewna",
        (200003, 260003): "wątpliwa",
        (200004, 200005): "odrzucona",
    }


def test_mapa_scala_pewne_a_watpliwe_zostawia_do_decyzji(baza):
    mapa, _ = mk.zbuduj_mape(baza, decyzje={})
    m = mapa.set_index("id_stary")

    assert sorted(m.index) == [200001, 200002, 200003, 200004, 200005, 200006, 260001, 260002, 260003]
    assert m.loc[260001, "id_nowy"] == 200001 and m.loc[260002, "id_nowy"] == 200002
    assert m.loc[260001, "podstawa"] == "ten sam NIP i kod pocztowy"
    assert m.loc[200001, "id_nowy"] == 200001 and pd.isna(m.loc[200001, "podstawa"])
    assert m.loc[260003, "id_nowy"] == 260003
    assert set(m.index[m["do_decyzji"]]) == {200003, 260003}
    assert m.loc[200005, "id_nowy"] == 200005
    assert m.loc[200006, "zrodlo"] == "erp_kontrahenci_archiwum"


@pytest.mark.parametrize("scal, id_nowy", [(True, 200003), (False, 260003)])
def test_decyzja_rozstrzyga_pare_watpliwa(baza, scal, id_nowy):
    mapa, _ = mk.zbuduj_mape(baza, decyzje={(200003, 260003): scal})
    m = mapa.set_index("id_stary")

    assert m.loc[260003, "id_nowy"] == id_nowy
    assert m.loc[260003, "podstawa"] == "decyzja" if scal else pd.isna(m.loc[260003, "podstawa"])
    assert not m["do_decyzji"].any()


def test_grupy_sa_przechodnie_i_wskazuja_najmniejszy_id():
    assert mk.grupy([1, 2, 3, 4], [(2, 3), (1, 3)]) == {1: 1, 2: 1, 3: 1, 4: 4}


def test_suma_faktur_po_scaleniu_jest_taka_sama(baza):
    mapa, _ = mk.zbuduj_mape(baza, decyzje={})
    mk.zapisz(baza, mapa)
    wrzesien = baza.sql(mk.SUMY_MIESIECZNE).df().set_index("miesiac").loc["2026-09-01"]

    assert wrzesien["netto_przed"] == wrzesien["netto_po"] == 1390.0
    # faktura na 200002 i korekta na 260002 to po scaleniu jeden kontrahent
    assert (wrzesien["kontrahenci_przed"], wrzesien["kontrahenci_po"]) == (5, 4)
