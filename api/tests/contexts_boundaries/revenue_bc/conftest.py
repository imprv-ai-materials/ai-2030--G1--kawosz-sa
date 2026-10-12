"""Mała baza z przypadkami do ręcznego policzenia przychodu za wrzesień 2026, po jednym na każdą regułę.

Typy kolumn są takie jak w kawosz.duckdb. Te same przypadki i rachunki opisuje docs/przychod_netto.md, sekcja 3.
Czasy e-commerce są w UTC; we wrześniu Warszawa to UTC+2.
"""

import duckdb
import pytest

DANE = """
-- POS: paragon 183 zł (latte 14 zł z VAT 8% + kawa 169 zł z VAT 23%) i ten sam plik wczytany drugi raz
CREATE TABLE pos_paragony (lokal INTEGER, nr_paragonu BIGINT, data_czas TIMESTAMP, kwota_brutto DECIMAL(12,2),
                           metoda_platnosci VARCHAR, storno INTEGER, kanal VARCHAR, plik VARCHAR);
INSERT INTO pos_paragony VALUES
    (1, 2609300001, TIMESTAMP '2026-09-30 08:00:00', 183.00, 'karta', 0, 'sala', 'pos_paragony_1_2026-09-30.csv'),
    (1, 2609300001, TIMESTAMP '2026-09-30 08:00:00', 183.00, 'karta', 0, 'sala', 'pos_paragony_1_2026-09-30 (1).csv');
CREATE TABLE pos_pozycje (lokal BIGINT, nr_paragonu BIGINT, kod_produktu VARCHAR, ilosc BIGINT, cena_brutto DOUBLE,
                          vat BIGINT);
INSERT INTO pos_pozycje VALUES (1, 2609300001, 'P0101', 1, 14.0, 8), (1, 2609300001, 'P0201', 1, 169.0, 23);

CREATE TABLE ecom_zamowienia (id BIGINT, data_utc TIMESTAMP_NS, waluta VARCHAR, brutto DOUBLE, email VARCHAR,
                              notatka VARCHAR, zwrot BOOLEAN, metoda_platnosci VARCHAR);
INSERT INTO ecom_zamowienia VALUES
    -- zwykłe zamówienie z notatką klienta
    (1000001, '2026-09-10 10:00:00', 'PLN', 123.00, 'anna@example.com', 'Proszę o szybką wysyłkę', false, 'BLIK'),
    -- zwrot
    (1000002, '2026-09-11 10:00:00', 'PLN', 61.50, 'piotr@example.com', NULL, true, 'karta'),
    -- EUR w sobotę 5.09: kurs z piątku 4.09 (4,2208)
    (1000003, '2026-09-05 10:00:00', 'EUR', 20.00, 'jan@example.de', NULL, false, 'karta'),
    -- testowe: e-mail w domenie firmy i notatka testowa
    (1000004, '2026-09-12 10:00:00', 'PLN', 123.00, 'qa@kawosz.pl', NULL, false, 'BLIK'),
    (1000005, '2026-09-13 10:00:00', 'PLN', 246.00, 'ewa@example.com', 'zamówienie testowe QA', false, 'BLIK'),
    -- 31.08 22:30 UTC = 1.09 00:30 w Warszawie; 30.09 22:15 UTC = 1.10 00:15 w Warszawie
    (1000006, '2026-08-31 22:30:00', 'PLN', 123.00, 'ola@example.com', NULL, false, 'BLIK'),
    (1000007, '2026-09-30 22:15:00', 'PLN', 61.50, 'tomek@example.com', NULL, false, 'BLIK'),
    -- EUR w niedzielę 6.09 22:30 UTC = poniedziałek 7.09 00:30 w Warszawie: kurs z 4.09 albo z 7.09 (4,2039)
    (1000008, '2026-09-06 22:30:00', 'EUR', 10.00, 'hans@example.de', NULL, false, 'karta');

CREATE TABLE ecom_subskrypcje (id VARCHAR, plan VARCHAR, data_platnosci TIMESTAMP, kwota DOUBLE);
INSERT INTO ecom_subskrypcje VALUES
    ('SUB-1', 'miesięczny', TIMESTAMP '2026-09-01 22:30:00', 39.0),
    ('SUB-2', 'roczny', TIMESTAMP '2026-09-02 23:00:00', 399.0),   -- 1/12 we wrześniu 2026
    ('SUB-3', 'roczny', TIMESTAMP '2025-10-14 23:10:00', 399.0),   -- X.2025–IX.2026: 1/12 we wrześniu 2026
    ('SUB-4', 'roczny', TIMESTAMP '2025-09-30 22:40:00', 399.0),   -- UTC: IX.2025–VIII.2026; Warszawa: X.2025–IX.2026
    ('SUB-5', 'miesięczny', TIMESTAMP '2026-08-31 22:20:00', 39.0); -- UTC: sierpień; Warszawa: 1.09 00:20

CREATE TABLE karty_podarunkowe (kod VARCHAR, data_sprzedazy DATE, data_realizacji DATE, kwota BIGINT);
INSERT INTO karty_podarunkowe VALUES
    ('KP-1', DATE '2026-09-03', NULL, 100),               -- sprzedana we wrześniu, niezrealizowana
    ('KP-2', DATE '2026-08-20', DATE '2026-09-05', 200),  -- sprzedana w sierpniu, zrealizowana we wrześniu
    ('KP-3', DATE '2026-09-04', DATE '2026-09-20', 50),   -- sprzedana i zrealizowana we wrześniu
    ('KP-4', DATE '2026-09-10', DATE '2026-10-02', 150);  -- sprzedana we wrześniu, zrealizowana w październiku

CREATE TABLE erp_faktury (nr_faktury VARCHAR, id_kontrahenta BIGINT, data DATE, typ VARCHAR, waluta VARCHAR,
                          kwota_netto DOUBLE, vat DOUBLE);
INSERT INTO erp_faktury VALUES
    ('FV/2026/09/00001', 260001, DATE '2026-09-30', 'faktura', 'PLN', 1000.0, 230.0),  -- drugi rekord firmy 200001
    ('KOR/2026/09/0001', 200001, DATE '2026-09-15', 'korekta', 'PLN', -100.0, -23.0),
    ('FV/2026/08/00001', 200001, DATE '2026-08-31', 'faktura', 'PLN', 500.0, 115.0);
CREATE TABLE mapa_kontrahentow (id_stary BIGINT, id_nowy BIGINT, zrodlo VARCHAR, podstawa VARCHAR, do_decyzji BOOLEAN);
INSERT INTO mapa_kontrahentow VALUES
    (200001, 200001, 'erp_kontrahenci', NULL, false),
    (260001, 200001, 'erp_kontrahenci', 'ten sam NIP i kod pocztowy', false);

CREATE TABLE kursy_nbp (data DATE, eur_pln DOUBLE);
INSERT INTO kursy_nbp VALUES
    (DATE '2026-09-03', 4.2143), (DATE '2026-09-04', 4.2208), (DATE '2026-09-07', 4.2039);
"""


@pytest.fixture
def baza():
    con = duckdb.connect(":memory:")
    con.execute(DANE)
    yield con
    con.close()


@pytest.fixture
def plik_bazy(tmp_path):
    sciezka = tmp_path / "kawosz.duckdb"
    con = duckdb.connect(str(sciezka))
    con.execute(DANE)
    con.close()
    return sciezka
