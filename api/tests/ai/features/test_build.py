"""Cechy z sql/<rodzina>.sql na dzień t0 i tabele cechy_treningowe i cechy_aktualne: populacja, opóźnienia dostaw,
etykieta."""

from datetime import date, datetime, time, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pytest
import yaml

from api.ai.features import build
from api.ai.features.build import KLUCZ, RODZINY, policz_cechy, zbuduj_cechy_aktualne, zbuduj_cechy_treningowe

FEATURES = Path(build.__file__).parent
T0 = date(2025, 4, 1)
T1 = date(2025, 5, 1)
# CRM, helpdesk i ERP dostarczają D+1 (docs/opoznienia_danych.md): w T0 znane są zdarzenia do T0 − 2,
# telemetria dociera z data_dostarczenia = data + 2, więc ostatni znany dzień pomiaru to T0 − 3.


def dni(n: int) -> date:
    return T0 - timedelta(days=n)


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE crm_biura (
            id_biura BIGINT, miasto VARCHAR, branza VARCHAR, liczba_pracownikow BIGINT, am_id BIGINT,
            plan VARCHAR, cena_mies DOUBLE, data_startu DATE, data_konca_umowy DATE, status VARCHAR
        );
        INSERT INTO crm_biura VALUES
            (1, 'Poznań', 'IT', 50, 3, 'S', 999, DATE '2022-06-10', DATE '2026-06-09', 'aktywny'),
            -- wypowiedzenie przed T0
            (2, 'Kraków', 'Bank', 20, 4, 'M', 500, DATE '2021-01-01', DATE '2025-04-30', 'zakończony'),
            -- brak odnowienia: umowa skończyła się przed T0
            (3, 'Gdańsk', 'IT', 10, 3, 'L', 700, DATE '2020-03-01', DATE '2025-02-28', 'zakończony'),
            -- start po T0
            (4, 'Łódź', 'Prawo', 30, 5, 'M', 800, DATE '2025-06-01', DATE '2026-05-31', 'aktywny'),
            -- wypowiedzenie w dniu T0: w T0 jeszcze nieznane, w T1 już tak
            (5, 'Poznań', 'Bank', 80, 4, 'XL', 2000, DATE '2023-09-01', DATE '2025-05-31', 'zakończony');
        CREATE TABLE crm_umowy_historia (id_biura BIGINT, data_zdarzenia DATE, typ VARCHAR, plan VARCHAR, cena DOUBLE);
        INSERT INTO crm_umowy_historia VALUES
            (1, DATE '2022-06-10', 'start', 'M', 1500),
            (1, DATE '2025-01-10', 'downgrade', 'S', 999),
            (2, DATE '2021-01-01', 'start', 'M', 500),
            (2, DATE '2025-03-15', 'wypowiedzenie', 'M', 500),
            (3, DATE '2020-03-01', 'start', 'L', 700),
            (4, DATE '2025-06-01', 'start', 'M', 800),
            (5, DATE '2023-09-01', 'start', 'XL', 2000),
            (5, DATE '2024-09-01', 'odnowienie', 'XL', 2100),
            (5, DATE '2025-04-01', 'wypowiedzenie', 'XL', 2100);
        CREATE TABLE iot_ekspresy (id_ekspresu VARCHAR, id_biura BIGINT);
        INSERT INTO iot_ekspresy VALUES ('A', 1), ('E', 5);
        CREATE TABLE iot_telemetria (
            id_ekspresu VARCHAR, data DATE, zaparzenia BIGINT, bledy BIGINT, data_dostarczenia DATE
        );
        CREATE TABLE helpdesk_zgloszenia (id VARCHAR, id_biura BIGINT, utworzono TIMESTAMP, kategoria VARCHAR);
        CREATE TABLE crm_kontakty_am (id_biura BIGINT, data DATE, rabat_retencyjny_pct BIGINT);
        CREATE TABLE ankiety_nps (id_biura BIGINT, data_wysylki DATE, data_odpowiedzi DATE, wynik BIGINT);
        CREATE TABLE erp_kontrahenci (id_kontrahenta BIGINT, id_biura_crm VARCHAR);
        CREATE TABLE erp_kontrahenci_archiwum (id_kontrahenta BIGINT, id_biura_crm VARCHAR);
        INSERT INTO erp_kontrahenci VALUES (100, '1'), (500, '5');
        CREATE TABLE mapa_kontrahentow (id_stary BIGINT, id_nowy BIGINT);
        INSERT INTO mapa_kontrahentow VALUES (100, 100), (500, 500);
        CREATE TABLE erp_faktury (nr_faktury VARCHAR, id_kontrahenta BIGINT, data DATE, typ VARCHAR);
        CREATE TABLE erp_pozycje (nr_faktury VARCHAR, indeks VARCHAR);
        CREATE TABLE erp_platnosci (nr_faktury VARCHAR, data_platnosci DATE);
    """)
    con.execute((FEATURES / "snapshoty.sql").read_text())
    _historia_przed_t0(con)
    return con


def _telemetria(con, ekspres: str, dzien: date, zaparzenia: int, bledy: int = 0):
    con.execute(
        "INSERT INTO iot_telemetria VALUES (?, ?, ?, ?, ?)",
        [ekspres, dzien, zaparzenia, bledy, dzien + timedelta(days=2)],
    )


def _faktura(con, nr: str, kontrahent: int, dzien: date, indeksy: list[str], zaplata=None):
    con.execute("INSERT INTO erp_faktury VALUES (?, ?, ?, 'faktura')", [nr, kontrahent, dzien])
    for indeks in indeksy:
        con.execute("INSERT INTO erp_pozycje VALUES (?, ?)", [nr, indeks])
    if zaplata:
        con.execute("INSERT INTO erp_platnosci VALUES (?, ?)", [nr, zaplata])


def _historia_przed_t0(con):
    for n in range(3, 66):
        _telemetria(con, "A", dni(n), 10 + n % 7, bledy=n % 2)
        _telemetria(con, "E", dni(n), 5, bledy=1)
    con.execute(
        "INSERT INTO helpdesk_zgloszenia VALUES ('z1', 1, ?, 'awaria'), ('z2', 5, ?, 'awaria')", [dni(10), dni(40)]
    )
    con.execute("INSERT INTO crm_kontakty_am VALUES (1, ?, 0), (5, ?, 0)", [dni(5), dni(80)])
    con.execute("INSERT INTO ankiety_nps VALUES (1, ?, ?, 8), (5, ?, ?, 4)", [dni(30), dni(20), dni(50), dni(45)])
    _faktura(con, "F1", 100, dni(15), ["10.01.0001"], zaplata=dni(3))
    _faktura(con, "F5", 500, dni(70), ["10.01.0001", "80.01.0002"], zaplata=dni(50))


def _rekordy_nieznane_w_t0(con):
    """Rekordy, które w T0 jeszcze nie dotarły: z dnia T0 − 1 (dostawa D+1 przychodzi w T0) i późniejsze."""
    con.execute(
        "INSERT INTO crm_umowy_historia VALUES (1, ?, 'downgrade', 'XS', 1), (5, ?, 'downgrade', 'S', 2)", [dni(1), T0]
    )
    # dzień pomiaru w oknie, ale dostarczony z opóźnieniem w T0
    con.execute("INSERT INTO iot_telemetria VALUES ('A', ?, 9999, 9999, ?)", [dni(5), T0])
    _telemetria(con, "A", dni(2), 9999, bledy=9999)  # dostarczony w T0
    _telemetria(con, "A", T0, 9999, bledy=9999)
    con.execute(
        "INSERT INTO helpdesk_zgloszenia VALUES"
        " ('z8', 1, ?, 'awaria'), ('z9', 1, ?, 'awaria'), ('z10', 5, ?, 'awaria')",
        [datetime.combine(dni(1), time(23, 59)), T0, T0 + timedelta(days=3)],
    )
    con.execute("INSERT INTO crm_kontakty_am VALUES (1, ?, 0), (1, ?, 20), (5, ?, 10)", [dni(1), T0, T0])
    con.execute("INSERT INTO ankiety_nps VALUES (1, ?, ?, 0), (5, ?, ?, 10)", [dni(10), dni(1), dni(9), T0])
    con.execute("INSERT INTO erp_platnosci VALUES ('F5', ?)", [dni(1)])  # druga płatność starszej faktury
    _faktura(con, "F9", 100, dni(1), ["10.01.0001"], zaplata=dni(1))
    _faktura(con, "F10", 500, T0, ["10.01.0001"], zaplata=T0)


def _df(rel: duckdb.DuckDBPyRelation) -> pd.DataFrame:
    return rel.df().sort_values(KLUCZ).reset_index(drop=True)


def _katalog() -> dict:
    return yaml.safe_load((FEATURES / "katalog.yaml").read_text())


@pytest.mark.parametrize("rodzina", RODZINY)
def test_rodzina_daje_wiersz_na_biuro_z_aktywna_umowa_w_t0(con, rodzina):
    sql = (FEATURES / "sql" / f"{rodzina}.sql").read_text()
    df = con.execute(sql, {"t0": T0}).df()

    # 2: wypowiedzenie przed T0, 3: umowa skończona przed T0, 4: start po T0;
    # 5: wypowiedzenie z dnia T0 jeszcze nieznane
    assert sorted(df["id_biura"]) == [1, 5]
    assert set(pd.to_datetime(df["t0"]).dt.date) == {T0}


def test_rekordy_ktore_w_t0_nie_dotarly_nie_zmieniaja_cech(con):
    przed = _df(policz_cechy(con, [T0]))
    _rekordy_nieznane_w_t0(con)
    po = _df(policz_cechy(con, [T0]))

    pd.testing.assert_frame_equal(po, przed)
    w = przed.set_index("id_biura").loc[1]
    assert (w["plan"], w["awarie_60d"], w["kontakty_am_90d"], w["nps_ostatni"]) == ("S", 1, 1, 8)
    assert (w["dni_od_ostatniego_zamowienia"], w["sr_opoznienie_platnosci"]) == (15, -2)


def test_rekordy_z_ostatniego_znanego_dnia_licza_sie(con):
    con.execute("INSERT INTO crm_umowy_historia VALUES (1, ?, 'downgrade', 'XS', 1)", [dni(2)])
    con.execute(
        "INSERT INTO helpdesk_zgloszenia VALUES ('z8', 1, ?, 'awaria')", [datetime.combine(dni(2), time(23, 59))]
    )
    con.execute("INSERT INTO crm_kontakty_am VALUES (1, ?, 0)", [dni(2)])
    con.execute("INSERT INTO ankiety_nps VALUES (1, ?, ?, 0)", [dni(10), dni(2)])
    _faktura(con, "F8", 100, dni(2), ["10.01.0001"], zaplata=dni(2))

    w = _df(policz_cechy(con, [T0])).set_index("id_biura").loc[1]

    assert (w["plan"], w["cena_mies"], w["awarie_60d"], w["kontakty_am_90d"], w["nps_ostatni"]) == ("XS", 1, 2, 2, 0)
    assert w["dni_od_ostatniego_zamowienia"] == 2
    assert w["sr_opoznienie_platnosci"] == pytest.approx((-2 + -14) / 2)  # F1 zapłacona po 12 dniach, F8 po 0


def test_nps_liczy_sie_od_dnia_odpowiedzi_nie_wysylki(con):
    # wysłana dawno, ale odpowiedź przyszła wczoraj: jeszcze nieznana; wysłana bez odpowiedzi: nic nie zmienia
    con.execute("INSERT INTO ankiety_nps VALUES (1, ?, ?, 0), (1, ?, NULL, NULL)", [dni(60), dni(1), dni(5)])

    assert _df(policz_cechy(con, [T0])).set_index("id_biura").loc[1, "nps_ostatni"] == 8


def test_dwa_zdarzenia_umowy_jednego_dnia_wygrywa_downgrade(con):
    con.execute(
        "INSERT INTO crm_umowy_historia VALUES (1, ?, 'odnowienie', 'L', 3000), (1, ?, 'downgrade', 'M', 1200)",
        [dni(3), dni(3)],
    )

    w = _df(policz_cechy(con, [T0])).set_index("id_biura").loc[1]

    assert (w["plan"], w["cena_mies"]) == ("M", 1200)


def test_cechy_treningowe_maja_etykiete_ze_snapshoty(con):
    wiersze = zbuduj_cechy_treningowe([T0, T1], con)

    df = con.sql("SELECT * FROM cechy_treningowe").df()
    snap = con.sql(
        "SELECT id_biura, data_snapszotu AS t0, odejdzie_90d FROM snapshoty WHERE data_snapszotu IN (?, ?)",
        params=[T0, T1],
    ).df()
    assert wiersze == len(df) == len(snap) == 3  # T0: biura 1 i 5, T1: biuro 1
    assert _df_z(df[["id_biura", "t0", "odejdzie_90d"]]).equals(_df_z(snap))
    cechy = [c for rodzina in RODZINY for c in _katalog()[rodzina]]
    assert list(df.columns) == KLUCZ + cechy + ["odejdzie_90d"]


def _df_z(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(KLUCZ).reset_index(drop=True).astype({"odejdzie_90d": "int64"})


def test_t0_spoza_snapshoty_przerywa_i_nie_nadpisuje_tabeli(con):
    zbuduj_cechy_treningowe([T0], con)

    with pytest.raises(ValueError, match="bez etykiety"):
        zbuduj_cechy_treningowe([date(2025, 4, 15)], con)

    assert con.sql("SELECT count(*) FROM cechy_treningowe").fetchone() == (2,)


def test_cechy_aktualne_to_cechy_treningowe_z_tego_samego_t0_bez_etykiety(con):
    zbuduj_cechy_treningowe([T0, T1], con)

    wiersze = zbuduj_cechy_aktualne(T0, con)

    aktualne = _df(con.sql("SELECT * FROM cechy_aktualne"))
    treningowe = _df(con.sql("SELECT * EXCLUDE (odejdzie_90d) FROM cechy_treningowe WHERE t0 = ?", params=[T0]))
    assert wiersze == len(aktualne) == 2  # biura 1 i 5
    pd.testing.assert_frame_equal(aktualne, treningowe)


def test_cechy_aktualne_zastepuja_poprzedni_stan_i_nie_potrzebuja_snapszotu(con):
    zbuduj_cechy_aktualne(T0, con)

    dzis = date(2025, 5, 12)  # nie 1. dzień miesiąca, więc snapshoty nie ma etykiety na ten dzień
    zbuduj_cechy_aktualne(dzis, con)

    assert con.sql("SELECT id_biura, t0 FROM cechy_aktualne").fetchall() == [(1, dzis)]


def test_brak_biur_w_t0_przerywa_i_nie_nadpisuje_cech_aktualnych(con):
    zbuduj_cechy_aktualne(T0, con)

    with pytest.raises(ValueError, match="żadnego biura"):
        zbuduj_cechy_aktualne(date(2019, 1, 1), con)

    assert con.sql("SELECT count(*) FROM cechy_aktualne").fetchone() == (2,)


def test_katalog_opisuje_kazda_ceche_kazdej_rodziny(con):
    katalog = _katalog()

    assert set(katalog) - {"pominiete_cechy_agencji"} == set(RODZINY)
    for rodzina in RODZINY:
        sql = (FEATURES / "sql" / f"{rodzina}.sql").read_text()
        kolumny = con.execute(sql, {"t0": T0}).df().columns
        assert list(kolumny) == KLUCZ + list(katalog[rodzina]), rodzina
        assert all(isinstance(opis, str) and opis.strip() for opis in katalog[rodzina].values()), rodzina


def test_brak_cech_z_przeciekiem(con):
    kolumny = set(policz_cechy(con, [T0]).columns)

    assert kolumny.isdisjoint(_katalog()["pominiete_cechy_agencji"])
