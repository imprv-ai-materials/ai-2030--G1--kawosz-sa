"""Wspólny kształt reguły jakości: zapytanie do kawosz.duckdb + schemat Pandery.

SQL przygotowuje ramkę (złączenia i agregaty liczy DuckDB), a Pandera sprawdza ją kolumna po kolumnie.
Poziom, właściciel i numery wierszy z docs/skala_problemu.md są w `metadata` schematu, więc schemat
jest pełnym opisem reguły.

Zakres: SQL dostaje parametry $od i $dzien (daty w czasie Europe/Warsaw). Co noc od = dzien = dzień
eksportu; przy przeglądzie historii `od` jest wcześniej.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

import duckdb
import pandas as pd
import pandera.pandas as pa


class Poziom(StrEnum):
    BLOKUJE = "blokuje"  # dane z tej nocy nie idą do raportów, dopóki właściciel nie poprawi źródła
    OSTRZEGA = "ostrzega"  # dane idą dalej, właściciel dostaje listę wierszy


class Wlasciciel(StrEnum):
    ZESPOL_DANYCH = "Zespół danych"
    OPERACJE_LOKALI = "Operacje lokali (POS)"
    ECOMMERCE = "E-commerce"
    FINANSE = "Finanse i księgowość"
    KARTOTEKA = "Dane podstawowe (kartoteka ERP)"
    SPRZEDAZ_B2B = "Sprzedaż B2B (kontrahenci)"


def meta(poziom: Poziom, wlasciciel: Wlasciciel, *skala: int) -> dict:
    """Metadane reguły; `skala` to numery wierszy z docs/skala_problemu.md, które reguła łapie."""
    return {"poziom": poziom, "wlasciciel": wlasciciel, "skala": skala}


def warunek(opis: str, test) -> pa.Check:
    """Test na całej ramce (wiele kolumn); `opis` trafia do raportu jako nazwa naruszenia."""
    return pa.Check(test, name=opis, error=opis)


@dataclass(frozen=True)
class Regula:
    sql: str
    schemat: pa.DataFrameSchema

    @property
    def id(self) -> str:
        return self.schemat.name

    @property
    def opis(self) -> str:
        return self.schemat.description

    @property
    def poziom(self) -> Poziom:
        return self.schemat.metadata["poziom"]

    @property
    def wlasciciel(self) -> Wlasciciel:
        return self.schemat.metadata["wlasciciel"]

    @property
    def skala(self) -> tuple[int, ...]:
        return self.schemat.metadata["skala"]

    def ramka(self, con: duckdb.DuckDBPyConnection, od: date, dzien: date) -> pd.DataFrame:
        parametry = {nazwa: wartosc for nazwa, wartosc in {"od": od, "dzien": dzien}.items() if f"${nazwa}" in self.sql}
        wynik = con.sql(self.sql, params=parametry)
        ramka = wynik.df()
        # Pusta lub cała pusta kolumna VARCHAR przychodzi z DuckDB jako object — ujednolicamy do str,
        # żeby reguły typów nie blokowały dnia bez danych (np. 25.12 w POS).
        tekstowe = [kolumna for kolumna, typ in zip(wynik.columns, wynik.types) if str(typ) == "VARCHAR"]
        return ramka.astype({kolumna: "str" for kolumna in tekstowe})
