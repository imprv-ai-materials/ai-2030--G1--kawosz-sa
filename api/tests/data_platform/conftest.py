"""Mała baza DuckDB w pamięci z czystymi danymi, które przechodzą wszystkie reguły jakości.

Każdy test psuje w niej jedną rzecz (SQL) i sprawdza, że właściwa reguła to łapie. Tabele mają te
same kolumny i typy co w kawosz.duckdb; pos_paragony bierze kolumny i typy wprost z kontraktu.
"""

import os
from datetime import date

import duckdb
import pytest

from api.data_platform.kontrakty.kontrakt import wczytaj

# Klient Inngest (api/inngest_app.py) powstaje przy imporcie: w testach w trybie deweloperskim, bez klucza podpisu.
os.environ.setdefault("INNGEST_DEV", "1")

DZIEN = date(2026, 9, 30)  # środa, ostatni dzień roboczy września: dzień eksportu w testach

# Jak w kawosz.duckdb: kolumny wymagane z kontraktu, `kanal`, którą kasy przysyłają od 1.06.2026 spoza
# kontraktu (loader łączy pliki po nazwach), i `plik` z nazwą pliku.
_POS_PARAGONY = "CREATE TABLE pos_paragony ({}, kanal VARCHAR, plik VARCHAR);".format(
    ", ".join(f"{k.nazwa} {k.typ}" for k in wczytaj("pos_paragony").kolumny if k.wymagana)
)
_NAGLOWEK = wczytaj("pos_paragony").wymagane

CZYSTE_DANE = _POS_PARAGONY + f"""
-- POS: jeden lokal, dwa paragony z 30.09 po cenach z cennika
CREATE TABLE lokale (lokal BIGINT, nazwa VARCHAR, miasto VARCHAR, adres VARCHAR, data_otwarcia DATE);
INSERT INTO lokale VALUES (1, 'Kawosz Poznań – ul. Testowa 1', 'Poznań', 'ul. Testowa 1', DATE '2020-01-01');

CREATE TABLE pos_produkty (kod_produktu VARCHAR, nazwa VARCHAR, kategoria VARCHAR, cena_brutto DOUBLE, vat BIGINT);
INSERT INTO pos_produkty VALUES
    ('P0101', 'Latte', 'napoje', 14.0, 8),
    ('P0201', 'Espresso Blend 1 kg', 'detal', 169.0, 23),
    ('P0999', 'Kawa ziarnista na wagę', 'detal', 0.0, 23);

INSERT INTO pos_paragony (lokal, nr_paragonu, data_czas, kanal, kwota_brutto, metoda_platnosci, storno, plik) VALUES
    (1, 2609300001, TIMESTAMP '2026-09-30 08:00:00', 'sala', 14.00, 'karta', 0, 'pos_paragony_1_2026-09-30.csv'),
    (1, 2609300002, TIMESTAMP '2026-09-30 09:00:00', 'wynos', 169.00, 'BLIK', 0, 'pos_paragony_1_2026-09-30.csv');

-- rejestr plików z kasy (load_raw): nagłówek zgodny z kontraktem, plik dotarł 1.10 o 5:12
CREATE TABLE pos_pliki (
    plik VARCHAR, lokal INTEGER, dzien DATE, kolumny VARCHAR[], wiersze INTEGER, czas_dostawy TIMESTAMP);
INSERT INTO pos_pliki VALUES
    ('pos_paragony_1_2026-09-30.csv', 1, DATE '2026-09-30', {_NAGLOWEK}, 2, TIMESTAMP '2026-10-01 05:12:00');

CREATE TABLE pos_pozycje (
    lokal BIGINT, nr_paragonu BIGINT, kod_produktu VARCHAR, ilosc BIGINT, cena_brutto DOUBLE, vat BIGINT);
INSERT INTO pos_pozycje VALUES
    (1, 2609300001, 'P0101', 1, 14.0, 8),
    (1, 2609300002, 'P0201', 1, 169.0, 23);

-- ERP: dwie faktury z 30.09 (23% VAT), jedna już opłacona; kontrahenci z poprawnym NIP-em i ID z CRM
CREATE TABLE erp_kontrahenci (
    id_kontrahenta BIGINT, nazwa VARCHAR, nip VARCHAR, adres VARCHAR, kod_pocztowy VARCHAR, id_biura_crm VARCHAR);
INSERT INTO erp_kontrahenci VALUES
    (200001, 'Alfa Sp. z o.o.', '123-456-32-18', 'ul. Biurowa 1', '60-001', '10001'),
    (200002, 'Beta S.A.', '5260250274', 'ul. Biurowa 2', '60-002', '10002');
CREATE TABLE erp_kontrahenci_archiwum AS SELECT * FROM erp_kontrahenci LIMIT 0;
INSERT INTO erp_kontrahenci_archiwum VALUES (200003, 'Gamma Sp. j.', '7740001454', 'ul. Stara 3', '60-003', '10003');

CREATE TABLE erp_kartoteka (indeks VARCHAR, nazwa VARCHAR, kategoria VARCHAR);
INSERT INTO erp_kartoteka VALUES
    ('10.01.0001', 'KAWA ZIARN. CREMA 1KG', 'Kawa ziarnista'),
    ('20.01.0001', 'MLEKO UHT 3,2% 1L', 'Mleko i dodatki'),
    ('80.01.0001', 'ABONAMENT KAWOSZ DLA BIUR – PLAN S', 'Abonamenty');

CREATE TABLE erp_faktury (
    nr_faktury VARCHAR, id_kontrahenta BIGINT, data DATE, typ VARCHAR, waluta VARCHAR, kwota_netto DOUBLE, vat DOUBLE);
INSERT INTO erp_faktury VALUES
    ('FV/2026/09/00001', 200001, DATE '2026-09-30', 'faktura', 'PLN', 1000.0, 230.0),
    ('FV/2026/09/00002', 200002, DATE '2026-09-30', 'faktura', 'PLN', 500.0, 115.0);

CREATE TABLE erp_pozycje (nr_faktury VARCHAR, indeks VARCHAR, ilosc DOUBLE, cena DOUBLE);
INSERT INTO erp_pozycje VALUES
    ('FV/2026/09/00001', '80.01.0001', 1, 1000.0),
    ('FV/2026/09/00002', '10.01.0001', 10, 50.0);

CREATE TABLE erp_platnosci (nr_faktury VARCHAR, data_platnosci DATE, kwota DOUBLE, spor BOOLEAN);
INSERT INTO erp_platnosci VALUES ('FV/2026/09/00001', DATE '2026-09-30', 1230.0, false);

-- E-commerce: zamówienie w PLN i w EUR (czas w UTC: 08:00 i 20:30 UTC to 10:00 i 22:30 w Warszawie)
CREATE TABLE ecom_produkty (sku VARCHAR, nazwa VARCHAR, cena_brutto_pln DOUBLE);
INSERT INTO ecom_produkty VALUES
    ('KW-ETIOPIA-001', 'Etiopia Yirgacheffe – kawa ziarnista 250 g', 46.17),
    ('KW-KENIA-002', 'Kenia AA – kawa ziarnista 250 g', 52.66);

CREATE TABLE ecom_zamowienia (
    id BIGINT, data_utc TIMESTAMP_NS, waluta VARCHAR, brutto DOUBLE, email VARCHAR, notatka VARCHAR, zwrot BOOLEAN,
    metoda_platnosci VARCHAR);
INSERT INTO ecom_zamowienia VALUES
    (1000001, '2026-09-30 08:00:00'::TIMESTAMP_NS, 'PLN', 61.16, 'anna.nowak@example.com', NULL, false, 'BLIK'),
    (1000002, '2026-09-30 20:30:00'::TIMESTAMP_NS, 'EUR', 20.07, 'jan.kowalski@example.de', NULL, false, 'karta');

CREATE TABLE ecom_pozycje (id_zamowienia BIGINT, sku VARCHAR, ilosc BIGINT, cena_brutto DOUBLE);
INSERT INTO ecom_pozycje VALUES
    (1000001, 'KW-ETIOPIA-001', 1, 46.17), (1000001, 'DOSTAWA', 1, 14.99),
    (1000002, 'KW-KENIA-002', 1, 13.17), (1000002, 'DOSTAWA', 1, 6.90);

CREATE TABLE kursy_nbp (data DATE, eur_pln DOUBLE);
INSERT INTO kursy_nbp VALUES (DATE '2026-09-29', 4.27), (DATE '2026-09-30', 4.26);

-- nocny batch subskrypcji: 22:30 i 23:10 UTC 29.09 to 00:30 i 01:10 30.09 w Warszawie
CREATE TABLE ecom_subskrypcje (id VARCHAR, plan VARCHAR, data_platnosci TIMESTAMP, kwota DOUBLE);
INSERT INTO ecom_subskrypcje VALUES
    ('SUB-000001', 'miesięczny', TIMESTAMP '2026-09-29 22:30:00', 39.0),
    ('SUB-000002', 'roczny', TIMESTAMP '2026-09-29 23:10:00', 399.0);

CREATE TABLE karty_podarunkowe (kod VARCHAR, data_sprzedazy DATE, data_realizacji DATE, kwota BIGINT);
INSERT INTO karty_podarunkowe VALUES ('KP-AAAA-0001', DATE '2026-09-01', NULL, 100);
"""


@pytest.fixture
def baza():
    con = duckdb.connect(":memory:")
    con.execute(CZYSTE_DANE)
    yield con
    con.close()


@pytest.fixture
def plik_bazy(tmp_path):
    """Czyste dane w pliku DuckDB — dla testów runnera, który otwiera bazę z dysku."""
    sciezka = tmp_path / "kawosz.duckdb"
    con = duckdb.connect(str(sciezka))
    con.execute(CZYSTE_DANE)
    con.close()
    return sciezka


@pytest.fixture
def sprawdz(baza):
    """Uruchamia regułę na bazie testowej dla dnia eksportu DZIEN (jak w nocy)."""
    return lambda regula: regula.sprawdz(baza, DZIEN, DZIEN)
