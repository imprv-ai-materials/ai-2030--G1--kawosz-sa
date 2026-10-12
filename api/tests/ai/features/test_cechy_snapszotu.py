"""Cechy na dzień snapszotu d: każda liczona wyłącznie z tego, co było znane przed początkiem dnia d."""

from datetime import date, timedelta

import duckdb
import pandas as pd
import pytest

from api.ai.features.cechy import cechy_snapszotu

D = date(2025, 4, 1)  # snapszot, na który sprawdzamy okna


def dni(n: int) -> date:
    return D - timedelta(days=n)


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE crm_biura (
            id_biura BIGINT, miasto VARCHAR, branza VARCHAR, liczba_pracownikow BIGINT, am_id BIGINT,
            plan VARCHAR, cena_mies DOUBLE, data_startu DATE, data_konca_umowy DATE, status VARCHAR
        );
        -- plan, cena, data końca i status ze stanu z dnia eksportu: nie mogą wpływać na cechy
        INSERT INTO crm_biura VALUES
            (1, 'Poznań', 'IT', 50, 3, 'S', 999, DATE '2020-04-01', DATE '2025-05-31', 'zakończony'),
            (2, 'Kraków', 'Bank', 20, 4, 'M', 500, DATE '2016-02-29', DATE '2027-02-27', 'aktywny'),
            (3, 'Gdańsk', 'IT', 10, 3, 'L', 700, DATE '2010-06-15', DATE '2026-06-14', 'aktywny');
        CREATE TABLE snapshoty (data_snapszotu DATE, id_biura BIGINT, odejdzie_90d INTEGER);
        INSERT INTO snapshoty VALUES
            (DATE '2025-04-01', 1, 1), (DATE '2025-02-01', 2, 0), (DATE '2025-04-01', 2, 0),
            (DATE '2025-04-01', 3, 0);
        CREATE TABLE crm_umowy_historia (id_biura BIGINT, data_zdarzenia DATE, typ VARCHAR, plan VARCHAR, cena DOUBLE);
        INSERT INTO crm_umowy_historia VALUES
            (1, DATE '2020-04-01', 'start', 'L', 3000),
            (1, DATE '2024-04-01', 'odnowienie', 'L', 3100),
            (1, DATE '2025-03-31', 'downgrade', 'M', 1800),
            (1, DATE '2025-04-01', 'downgrade', 'S', 999),
            (1, DATE '2025-04-20', 'wypowiedzenie', 'S', 999),
            (2, DATE '2016-02-29', 'start', 'M', 500),
            (3, DATE '2010-06-15', 'start', 'L', 700);
        CREATE TABLE iot_ekspresy (id_ekspresu VARCHAR, id_biura BIGINT);
        INSERT INTO iot_ekspresy VALUES ('A', 1), ('B', 1);
        CREATE TABLE iot_telemetria (
            id_ekspresu VARCHAR, data DATE, zaparzenia BIGINT, bledy BIGINT, data_dostarczenia DATE
        );
        CREATE TABLE helpdesk_zgloszenia (id VARCHAR, id_biura BIGINT, utworzono TIMESTAMP, kategoria VARCHAR);
        CREATE TABLE crm_kontakty_am (id_biura BIGINT, data DATE, rabat_retencyjny_pct BIGINT);
        CREATE TABLE ankiety_nps (id_biura BIGINT, data_wysylki DATE, data_odpowiedzi DATE, wynik BIGINT);
        CREATE TABLE erp_kontrahenci (id_kontrahenta BIGINT, id_biura_crm VARCHAR);
        CREATE TABLE erp_kontrahenci_archiwum (id_kontrahenta BIGINT, id_biura_crm VARCHAR);
        INSERT INTO erp_kontrahenci VALUES (100, '1'), (101, NULL);
        CREATE TABLE mapa_kontrahentow (id_stary BIGINT, id_nowy BIGINT);
        INSERT INTO mapa_kontrahentow VALUES (100, 100), (101, 100);  -- 101 to duplikat kontrahenta 100
        CREATE TABLE erp_faktury (nr_faktury VARCHAR, id_kontrahenta BIGINT, data DATE, typ VARCHAR);
        CREATE TABLE erp_pozycje (nr_faktury VARCHAR, indeks VARCHAR);
        CREATE TABLE erp_platnosci (nr_faktury VARCHAR, data_platnosci DATE);
    """)
    return con


def _cechy(con) -> pd.DataFrame:
    df = cechy_snapszotu(con)
    df["data_snapszotu"] = pd.to_datetime(df["data_snapszotu"]).dt.date
    return df.set_index(["id_biura", "data_snapszotu"])


def _telemetria(con, ekspres: str, dzien: date, zaparzenia: int, bledy: int = 0):
    con.execute(
        "INSERT INTO iot_telemetria VALUES (?, ?, ?, ?, ?)",
        [ekspres, dzien, zaparzenia, bledy, dzien + timedelta(days=2)],
    )


def _faktura(con, nr: str, kontrahent: int, dzien: date, indeksy: list[str], typ: str = "faktura", zaplata=None):
    con.execute("INSERT INTO erp_faktury VALUES (?, ?, ?, ?)", [nr, kontrahent, dzien, typ])
    for indeks in indeksy:
        con.execute("INSERT INTO erp_pozycje VALUES (?, ?)", [nr, indeks])
    if zaplata:
        con.execute("INSERT INTO erp_platnosci VALUES (?, ?)", [nr, zaplata])


def test_wiersz_na_kazdy_snapszot(con):
    assert len(_cechy(con)) == 4


def test_dni_do_rocznicy_z_daty_startu_a_nie_z_konca_umowy_z_eksportu(con):
    c = _cechy(con)

    assert c.loc[(1, D), "dni_do_rocznicy"] == 0  # rocznica 1.04 wypada w dniu snapszotu
    assert c.loc[(2, date(2025, 2, 1)), "dni_do_rocznicy"] == 27  # start 29.02: rocznica 2025-02-28
    assert c.loc[(3, D), "dni_do_rocznicy"] == 75  # 2025-06-15


def test_plan_i_cena_z_ostatniego_zdarzenia_przed_snapszotem(con):
    w = _cechy(con).loc[(1, D)]

    # downgrade z 2025-03-31 jest znany; downgrade z dnia snapszotu i stan z eksportu (S, 999) jeszcze nie
    assert (w["plan"], w["cena_mies"]) == ("M", 1800)


def test_cena_nieznana_gdy_ostatnie_zdarzenie_starsze_niz_rok(con):
    # Historia odnowień zaczyna się w 2024; cena ze startu w 2010 nie jest ceną z 2025.
    w = _cechy(con).loc[(3, D)]

    assert w["plan"] == "L"
    assert pd.isna(w["cena_mies"])


def test_atrybuty_biura_bez_historii_z_crm(con):
    w = _cechy(con).loc[(1, D)]

    assert (w["miasto"], w["branza"], w["liczba_pracownikow"], w["am_id"]) == ("Poznań", "IT", 50, 3)
    assert w["staz_mies"] == pytest.approx(1826 / 30.44)


def test_zaparzenia_i_bledy_tylko_z_dostarczonych_dni(con):
    _telemetria(con, "A", dni(2), 1000, bledy=1000)  # dostarczone w dniu snapszotu: jeszcze nieznane
    _telemetria(con, "A", dni(3), 1, bledy=1)  # ostatni znany dzień
    _telemetria(con, "B", dni(32), 10, bledy=10)  # początek okna 30 dni, drugi ekspres biura
    _telemetria(con, "A", dni(33), 100, bledy=100)  # koniec poprzednich 30 dni
    _telemetria(con, "A", dni(62), 1, bledy=1000)  # początek poprzednich 30 dni i okna błędów 60 dni
    _telemetria(con, "A", dni(63), 5000, bledy=5000)  # poza oknami

    w = _cechy(con).loc[(1, D)]

    assert w["zaparzenia_30d"] == 11
    assert w["trend_zaparzen"] == pytest.approx(11 / 101)
    assert w["bledy_60d"] == 1111


def test_biuro_bez_telemetrii_ma_zera_i_brak_trendu(con):
    w = _cechy(con).loc[(2, D)]

    assert (w["zaparzenia_30d"], w["bledy_60d"]) == (0, 0)
    assert pd.isna(w["trend_zaparzen"])


def test_awarie_i_kontakty_tylko_z_okna_przed_snapszotem(con):
    con.execute(
        "INSERT INTO helpdesk_zgloszenia VALUES (?, 1, ?, 'awaria'), (?, 1, ?, 'awaria'), (?, 1, ?, 'awaria'),"
        " (?, 1, ?, 'serwis')",
        ["z1", D, "z2", dni(60), "z3", dni(61), "z4", dni(1)],
    )
    con.execute(
        "INSERT INTO crm_kontakty_am VALUES (1, ?, 0), (1, ?, 0), (1, ?, 0), (1, ?, 10)", [D, dni(90), dni(91), dni(1)]
    )

    w = _cechy(con).loc[(1, D)]

    assert w["awarie_60d"] == 1  # z2; z1 jest z dnia snapszotu, z3 sprzed okna, z4 to nie awaria
    assert w["kontakty_am_90d"] == 2  # dni(90) i dni(1)


def test_nps_z_ostatniej_odpowiedzi_przed_snapszotem(con):
    con.execute(
        "INSERT INTO ankiety_nps VALUES (1, ?, ?, 9), (1, ?, ?, 3), (1, ?, NULL, NULL), (2, ?, ?, 7)",
        [dni(100), dni(95), dni(10), D, dni(5), dni(400), dni(399)],
    )

    c = _cechy(con)

    assert c.loc[(1, D), "nps_ostatni"] == 9  # odpowiedź z dnia snapszotu jeszcze nieznana
    assert c.loc[(2, D), "nps_ostatni"] == 7
    assert pd.isna(c.loc[(3, D), "nps_ostatni"])


def test_dni_od_ostatniego_zamowienia_kawy_przed_snapszotem(con):
    _faktura(con, "F1", 101, dni(40), ["10.01.0001", "80.01.0002"])  # kawa, kontrahent-duplikat
    _faktura(con, "F2", 100, dni(10), ["80.01.0002", "20.01.0001"])  # abonament i mleko, bez kawy
    _faktura(con, "F3", 100, D, ["10.01.0001"])  # z dnia snapszotu
    _faktura(con, "K1", 100, dni(5), ["10.01.0001"], typ="korekta")

    c = _cechy(con)

    assert c.loc[(1, D), "dni_od_ostatniego_zamowienia"] == 40
    assert pd.isna(c.loc[(3, D), "dni_od_ostatniego_zamowienia"])


def test_opoznienie_z_platnosci_z_ostatnich_90_dni_przed_snapszotem(con):
    _faktura(con, "F1", 100, dni(100), ["80.01.0002"], zaplata=dni(80))  # 20 dni: 6 po terminie
    _faktura(con, "F2", 100, dni(40), ["80.01.0002"], zaplata=dni(30))  # 10 dni: 4 przed terminem
    _faktura(con, "F3", 100, dni(20), ["80.01.0002"], zaplata=D)  # zapłacona w dniu snapszotu: nieznana
    _faktura(con, "F4", 100, dni(200), ["80.01.0002"], zaplata=dni(91))  # zapłata sprzed okna 90 dni

    c = _cechy(con)

    assert c.loc[(1, D), "sr_opoznienie_platnosci"] == pytest.approx(1.0)
    assert pd.isna(c.loc[(3, D), "sr_opoznienie_platnosci"])


def test_brak_cech_z_przeciekiem(con):
    kolumny = set(_cechy(con).columns)

    assert kolumny.isdisjoint(
        {"dni_do_konca_umowy", "status_crm", "zgloszenia_odbior_ekspresu", "rabat_retencyjny_max", "miasto_te"}
    )
