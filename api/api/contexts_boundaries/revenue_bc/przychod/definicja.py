"""Definicja przychodu netto Kawosz S.A.: linie przychodu ze wszystkich źródeł i reguły, każda jako osobny krok.

Linia przychodu to jeden dokument źródłowy: paragon, zamówienie, obciążenie subskrypcji, karta podarunkowa, faktura
albo korekta ERP. Ma kwotę, walutę i czas ujęcia. Linie startowe są takie, jak sumuje je dashboard BI: kwoty i daty
leżą tak jak w tabelach (e-commerce w UTC, EUR liczone jak PLN). Każda reguła z KROKI to funkcja, która dostaje SQL
linii po poprzednim kroku i zwraca SQL linii po swoim. Przychód miesiąca to suma linii, których miesiąc ujęcia
wypada w tym miesiącu (`suma`).

Dwie rzeczy liczymy dopiero przy sumowaniu, żeby wynik po wszystkich krokach nie zależał od ich kolejności:
- kwotę w EUR przeliczamy kursem z dnia ujęcia linii (krok „EUR” tylko to włącza), bo krok „czas polski” może
  przesunąć ten dzień;
- miesiąc ujęcia to miesiąc `czas` przesunięty o `miesiecy_po` (rozłożenie planu rocznego), bo krok „czas polski”
  może przesunąć miesiąc płatności.

Przychód netto według definicji to suma linii po wszystkich krokach, w której każdy dokument występuje raz
(`przychod_netto`). Surowa suma BI liczy linie z duplikatami (zdublowane pliki z kas), tak jak leżą w tabelach.
Reguły i ręcznie policzone przykłady: docs/przychod_netto.md.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import duckdb
import pandas as pd

from api.data_platform.kontrakty.kontrakt import wczytaj

STREFA = "Europe/Warsaw"  # czas biznesowy firmy (data/README.md)
STAWKA_VAT_ECOM = 23  # sklep, subskrypcje i karty podarunkowe: VAT 23% (konwencja e-commerce, data/README.md)

POS, ZAMOWIENIA, SUBSKRYPCJE, KARTY, ERP = (
    "POS",
    "e-commerce: zamówienia",
    "e-commerce: subskrypcje",
    "karty podarunkowe",
    "ERP",
)
ZRODLA = [POS, ZAMOWIENIA, SUBSKRYPCJE, KARTY, ERP]

# Zamówienie testowe rozpoznajemy tak samo jak reguła jakości ECOM-05: notatka testowa albo e-mail w domenie firmy.
_ECOM_05 = wczytaj("ecom_zamowienia").parametry("ECOM-05")
NOTATKA_TESTOWA, DOMENA_WEWNETRZNA = _ECOM_05["notatka_testowa"], _ECOM_05["domena_wewnetrzna"]


def _tekst(wartosc: str) -> str:
    """Literał tekstowy SQL."""
    return "'" + wartosc.replace("'", "''") + "'"


JEST_TESTOWE = (
    f"(coalesce(regexp_matches(notatka, {_tekst('(?i)' + NOTATKA_TESTOWA)}), false)"
    f" OR coalesce(ends_with(lower(email), {_tekst(DOMENA_WEWNETRZNA.lower())}), false))"
)


def _linie_startowe(bez_duplikatow: bool) -> str:
    """Linie tak, jak sumuje je BI: kwota i data z tabeli, e-commerce w UTC, EUR bez przeliczenia.

    Okno jest szersze niż miesiąc ($od – $do) tam, gdzie kroki przesuwają czas ujęcia: e-commerce o dobę
    (czas polski), subskrypcje o rok (plan roczny), karty sprzedane wcześniej (dzień realizacji). Miesiąc wybiera
    dopiero `suma`. Przy `bez_duplikatow` paragon (lokal, nr_paragonu) liczy się raz: z pliku bez dopisku w nazwie.
    """
    jeden_paragon = (
        "QUALIFY row_number() OVER (PARTITION BY lokal, nr_paragonu ORDER BY length(plik), plik) = 1"
        if bez_duplikatow
        else ""
    )
    return f"""
        SELECT *, 0 AS miesiecy_po, false AS eur_po_kursie FROM (
            SELECT '{POS}' AS zrodlo, lokal::VARCHAR || '/' || nr_paragonu::VARCHAR AS dokument, data_czas AS czas,
                   false AS czas_utc, kwota_brutto::DOUBLE AS kwota, 'PLN' AS waluta, lokal, nr_paragonu
            FROM pos_paragony WHERE data_czas >= $od AND data_czas < $do
            {jeden_paragon}
            UNION ALL BY NAME
            SELECT '{ZAMOWIENIA}' AS zrodlo, id::VARCHAR AS dokument, data_utc::TIMESTAMP AS czas, true AS czas_utc,
                   brutto AS kwota, waluta, zwrot, email, notatka
            FROM ecom_zamowienia WHERE data_utc >= $od - INTERVAL 1 DAY AND data_utc < $do + INTERVAL 1 DAY
            UNION ALL BY NAME
            SELECT '{SUBSKRYPCJE}' AS zrodlo, id || ' ' || data_platnosci::VARCHAR AS dokument, data_platnosci AS czas,
                   true AS czas_utc, kwota, 'PLN' AS waluta, plan
            FROM ecom_subskrypcje
            WHERE data_platnosci >= $od - INTERVAL 12 MONTH - INTERVAL 1 DAY AND data_platnosci < $do + INTERVAL 1 DAY
            UNION ALL BY NAME
            SELECT '{KARTY}' AS zrodlo, kod AS dokument, data_sprzedazy::TIMESTAMP AS czas, false AS czas_utc,
                   kwota::DOUBLE AS kwota, 'PLN' AS waluta, data_realizacji
            FROM karty_podarunkowe
            WHERE data_sprzedazy >= $od AND data_sprzedazy < $do OR data_realizacji >= $od AND data_realizacji < $do
            UNION ALL BY NAME
            SELECT '{ERP}' AS zrodlo, nr_faktury AS dokument, data::TIMESTAMP AS czas, false AS czas_utc,
                   kwota_netto AS kwota, waluta, typ, id_kontrahenta
            FROM erp_faktury WHERE data >= $od AND data < $do
        )
    """


# --- Reguły: każda dostaje nazwę relacji z liniami po poprzednim kroku i zwraca SELECT linii po swoim. ---


def pos_netto(linie: str) -> str:
    """Paragon POS: netto = Σ ilosc × cena_brutto / (1 + vat/100) z jego pozycji (stawki 5/8/23% są w pozycjach)."""
    return f"""
        WITH netto AS (
            SELECT lokal, nr_paragonu, sum(ilosc * cena_brutto / (1 + vat / 100.0)) AS netto
            FROM pos_pozycje SEMI JOIN (SELECT lokal, nr_paragonu FROM {linie} WHERE zrodlo = '{POS}')
                 USING (lokal, nr_paragonu)
            GROUP BY ALL)
        SELECT l.* REPLACE (CASE WHEN l.zrodlo = '{POS}' THEN n.netto ELSE l.kwota END AS kwota)
        FROM {linie} l LEFT JOIN netto n USING (lokal, nr_paragonu)
    """


def vat_23(linie: str) -> str:
    """Zamówienia, subskrypcje i karty podarunkowe: netto = brutto / 1,23."""
    return f"""
        SELECT * REPLACE (CASE WHEN zrodlo IN ('{ZAMOWIENIA}', '{SUBSKRYPCJE}', '{KARTY}')
                               THEN kwota / {1 + STAWKA_VAT_ECOM / 100} ELSE kwota END AS kwota)
        FROM {linie}
    """


def korekty_i_zwroty(linie: str) -> str:
    """Korekty ERP mają ujemną kwotę i datę korekty, więc odejmują się od faktur same (są już w liniach startowych).

    Zwrot e-commerce trzeba odjąć. Tabela nie ma daty ani kwoty zwrotu (ECOM-07), więc zwrot jest pełny
    i ujęty w miesiącu zamówienia: zamówienie z `zwrot = true` nie daje przychodu.
    """
    return f"SELECT * FROM {linie} WHERE NOT (zrodlo = '{ZAMOWIENIA}' AND zwrot)"


def mapa_kontrahentow(linie: str) -> str:
    """Faktura ERP trafia na rekord główny kontrahenta z mapa_kontrahentow (stary → nowy ID). Suma się nie zmienia."""
    return f"""
        SELECT l.* REPLACE (coalesce(m.id_nowy, l.id_kontrahenta) AS id_kontrahenta)
        FROM {linie} l LEFT JOIN mapa_kontrahentow m ON m.id_stary = l.id_kontrahenta
    """


def roczne_na_12_miesiecy(linie: str) -> str:
    """Obciążenie planu rocznego: 1/12 kwoty w miesiącu płatności i w każdym z 11 następnych."""
    return f"""
        SELECT * FROM {linie} WHERE NOT (zrodlo = '{SUBSKRYPCJE}' AND plan = 'roczny')
        UNION ALL
        SELECT l.* REPLACE (l.kwota / 12 AS kwota, l.miesiecy_po + r.i AS miesiecy_po)
        FROM {linie} l, range(12) r(i) WHERE l.zrodlo = '{SUBSKRYPCJE}' AND l.plan = 'roczny'
    """


def karty_w_dniu_realizacji(linie: str) -> str:
    """Karta podarunkowa jest przychodem w dniu realizacji. Sprzedaż karty to przedpłata, a nie przychód."""
    return f"""
        SELECT * REPLACE (CASE WHEN zrodlo = '{KARTY}' THEN data_realizacji::TIMESTAMP ELSE czas END AS czas)
        FROM {linie} WHERE NOT (zrodlo = '{KARTY}' AND data_realizacji IS NULL)
    """


def eur_po_kursie(linie: str) -> str:
    """Kwotę w EUR przeliczamy kursem z kursy_nbp z dnia ujęcia, a bez notowania tego dnia ostatnim wcześniejszym.

    Samo przeliczenie robi `suma` (kursem z dnia, który obowiązuje po wszystkich krokach).
    """
    return f"SELECT * REPLACE (true AS eur_po_kursie) FROM {linie}"


def bez_testowych(linie: str) -> str:
    """Bez zamówień testowych: notatka testowa albo e-mail w domenie firmy (parametry z kontraktu, reguła ECOM-05)."""
    return f"SELECT * FROM {linie} WHERE NOT (zrodlo = '{ZAMOWIENIA}' AND {JEST_TESTOWE})"


def czas_polski(linie: str) -> str:
    """Doba według czasu polskiego: czas e-commerce (UTC) przeliczamy na Europe/Warsaw. POS, ERP i karty są lokalne."""
    return f"""
        SELECT * REPLACE (CASE WHEN czas_utc THEN timezone('{STREFA}', czas AT TIME ZONE 'UTC') ELSE czas END AS czas,
                          false AS czas_utc)
        FROM {linie}
    """


@dataclass(frozen=True)
class Krok:
    kod: str
    opis: str
    sql: Callable[[str], str]


KROKI = [
    Krok("1. POS netto", "POS netto według stawek VAT z pozycji paragonu", pos_netto),
    Krok("2. VAT 23%", "E-commerce, subskrypcje i karty podarunkowe netto: brutto / 1,23", vat_23),
    Krok(
        "3. Korekty i zwroty",
        "Korekty ERP odjęte (już są w BI z kwotą ujemną), zwroty e-commerce odjęte w całości w miesiącu zamówienia",
        korekty_i_zwroty,
    ),
    Krok(
        "4. Mapa kontrahentów",
        "Faktury ERP przepięte na główny rekord kontrahenta z mapa_kontrahentow",
        mapa_kontrahentow,
    ),
    Krok("5. Plan roczny", "Subskrypcje roczne rozłożone na 12 miesięcy po 1/12", roczne_na_12_miesiecy),
    Krok("6. Karty", "Karty podarunkowe w dniu realizacji, a nie sprzedaży", karty_w_dniu_realizacji),
    Krok(
        "7. EUR",
        "EUR po kursie z kursy_nbp z dnia sprzedaży (brak notowania: ostatni wcześniejszy kurs)",
        eur_po_kursie,
    ),
    Krok("8. Bez testowych", "Bez zamówień testowych: notatka testowa albo e-mail @kawosz.pl", bez_testowych),
    Krok("9. Czas polski", "Doba według czasu polskiego (Europe/Warsaw) zamiast UTC w e-commerce", czas_polski),
]


def linie_sql(kroki: list[Krok], bez_duplikatow: bool) -> str:
    """SQL linii po podanych krokach (po kolei); parametry $od i $do to granice miesiąca."""
    ctes = [f"l0 AS ({_linie_startowe(bez_duplikatow)})"]
    ctes += [f"l{i} AS ({krok.sql(f'l{i - 1}')})" for i, krok in enumerate(kroki, 1)]
    return "WITH " + ",\n".join(ctes) + f"\nSELECT * FROM l{len(kroki)}"


def _granice(miesiac: date) -> dict[str, date]:
    od = miesiac.replace(day=1)
    return {"od": od, "do": (pd.Timestamp(od) + pd.DateOffset(months=1)).date()}


def linie(con: duckdb.DuckDBPyConnection, miesiac: date, kroki: list[Krok] = KROKI, bez_duplikatow=True):
    """Linie ujęte w miesiącu po podanych krokach, z kwotą w PLN (do sprawdzeń i przykładów)."""
    return con.sql(_ujete(linie_sql(kroki, bez_duplikatow)), params=_granice(miesiac)).df()


def _ujete(sql_linii: str) -> str:
    """Linie z miesiącem ujęcia = $od i kwotą w PLN (EUR kursem z dnia ujęcia, jeśli krok EUR jest włączony)."""
    return f"""
        WITH linie AS ({sql_linii})
        SELECT l.*, k.data AS data_kursu, k.eur_pln,
               l.kwota * CASE WHEN l.waluta = 'EUR' AND l.eur_po_kursie THEN k.eur_pln ELSE 1 END AS kwota_pln
        FROM linie l ASOF LEFT JOIN kursy_nbp k ON l.czas::DATE >= k.data
        WHERE (date_trunc('month', l.czas) + to_months(l.miesiecy_po::INTEGER))::DATE = $od
    """


def suma(con: duckdb.DuckDBPyConnection, miesiac: date, kroki: list[Krok], bez_duplikatow: bool) -> pd.DataFrame:
    """Przychód miesiąca według źródeł po podanych krokach: zrodlo, linie, kwota_pln."""
    wynik = con.sql(
        f"""
        SELECT zrodlo, count(*) AS linie, sum(kwota_pln) AS kwota_pln,
               count(*) FILTER (WHERE kwota IS NULL) AS bez_kwoty,
               count(*) FILTER (WHERE waluta = 'EUR' AND eur_po_kursie AND eur_pln IS NULL) AS bez_kursu
        FROM ({_ujete(linie_sql(kroki, bez_duplikatow))}) GROUP BY 1
        """,
        params=_granice(miesiac),
    ).df()
    # Linii bez kwoty (np. paragonu bez pozycji) albo bez kursu nie pomijamy po cichu: to błąd danych.
    bledne = wynik[(wynik["bez_kwoty"] > 0) | (wynik["bez_kursu"] > 0)]
    if not bledne.empty:
        raise ValueError(f"Linie bez kwoty albo bez kursu EUR w {miesiac:%Y-%m}:\n{bledne.to_string(index=False)}")
    wynik = pd.DataFrame({"zrodlo": ZRODLA}).merge(wynik[["zrodlo", "linie", "kwota_pln"]], how="left")
    return wynik.fillna({"linie": 0, "kwota_pln": 0.0}).astype({"linie": int})


def przychod_netto(con: duckdb.DuckDBPyConnection, miesiac: date) -> pd.DataFrame:
    """Przychód netto według definicji: każdy dokument raz, wszystkie reguły z KROKI."""
    return suma(con, miesiac, KROKI, bez_duplikatow=True)
