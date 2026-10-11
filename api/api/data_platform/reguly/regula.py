"""Wspólny kształt reguły jakości: zapytanie do kawosz.duckdb + schemat Pandery.

SQL przygotowuje ramkę (złączenia i agregaty liczy DuckDB), a Pandera sprawdza ją kolumna po kolumnie.
Poziom, właściciel, jednostka rekordu i numery wierszy z docs/skala_problemu.md są w `metadata`
schematu, więc schemat jest pełnym opisem reguły.

Zakres: SQL dostaje parametry $od i $dzien (daty w czasie Europe/Warsaw). Co noc od = dzien = dzień
eksportu; przy przeglądzie historii `od` jest wcześniej.
"""

import re
from collections import Counter, defaultdict
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


def meta(poziom: Poziom, wlasciciel: Wlasciciel, *skala: int, jednostka: str) -> dict:
    """Metadane reguły; `skala` to numery wierszy z docs/skala_problemu.md, które reguła łapie,
    a `jednostka` mówi, czym jest jeden wiersz sprawdzanej ramki (paragon, lokal × dzień, …)."""
    return {"poziom": poziom, "wlasciciel": wlasciciel, "skala": skala, "jednostka": jednostka}


def warunek(opis: str, test) -> pa.Check:
    """Test na całej ramce (wiele kolumn); `opis` trafia do raportu jako nazwa naruszenia."""
    return pa.Check(test, name=opis, error=opis)


# Wbudowane testy Pandery mają nazwy typu `isin([...])` — w raporcie dopisujemy do nich kolumnę.
_TEST_WBUDOWANY = re.compile(r"^[a-z_]+\(.*\)$", re.DOTALL)


def _etykieta(przypadek, schemat: pa.DataFrameSchema) -> str:
    """Czytelna nazwa naruszenia z wiersza `SchemaErrors.failure_cases`."""
    test, kolumna, wartosc = str(przypadek.check), przypadek.column, przypadek.failure_case
    if test == "column_in_dataframe":
        return f"brak kolumny {wartosc}"
    if test == "column_in_schema":
        return f"nieoczekiwana kolumna {wartosc}"
    if test.startswith("dtype("):
        return f"{kolumna}: typ {wartosc} zamiast {test[len('dtype('):-1]}"
    if test == "not_nullable":
        return f"{kolumna}: brak wartości"
    if test == "multiple_fields_uniqueness":
        return f"powtórzony klucz ({', '.join(schemat.unique)})"
    if test == "field_uniqueness":
        return f"{kolumna}: wartość powtórzona"
    if _TEST_WBUDOWANY.match(test) and isinstance(kolumna, str):
        return f"{kolumna}: {test}"
    return test


@dataclass
class Wynik:
    regula: "Regula"
    wiersze: int  # ile wierszy reguła sprawdziła
    naruszenia: dict[str, int]  # naruszenie -> liczba wierszy, które je łamią
    bledne_wiersze: pd.DataFrame | None = None  # wszystkie łamiące wiersze + kolumna `naruszenie`
    blad: str | None = None  # reguły nie dało się wykonać (np. błąd SQL)

    @property
    def ok(self) -> bool:
        return not self.naruszenia and self.blad is None

    @property
    def bledne(self) -> int:
        return 0 if self.bledne_wiersze is None else len(self.bledne_wiersze)

    @property
    def blokuje(self) -> bool:
        return not self.ok and self.regula.poziom == Poziom.BLOKUJE

    def przyklady(self, n: int) -> pd.DataFrame | None:
        """Do `n` łamiących wierszy, po kolei z każdego rodzaju naruszenia; kolejność nie zależy od SQL."""
        if self.bledne_wiersze is None:
            return None
        wiersze = self.bledne_wiersze.sort_values(list(self.bledne_wiersze.columns), na_position="last", kind="stable")
        rodzaje = [grupa.index.tolist() for _, grupa in wiersze.groupby("naruszenie", sort=True)]
        wybrane = [idx for runda in range(n) for idx in (r[runda] for r in rodzaje if runda < len(r))][:n]
        return wiersze.loc[wybrane]


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

    @property
    def jednostka(self) -> str:
        return self.schemat.metadata["jednostka"]

    def ramka(self, con: duckdb.DuckDBPyConnection, od: date, dzien: date) -> pd.DataFrame:
        parametry = {nazwa: wartosc for nazwa, wartosc in {"od": od, "dzien": dzien}.items() if f"${nazwa}" in self.sql}
        wynik = con.sql(self.sql, params=parametry)
        ramka = wynik.df()
        # Pusta lub cała pusta kolumna VARCHAR przychodzi z DuckDB jako object — ujednolicamy do str,
        # żeby reguły typów nie blokowały dnia bez danych (np. 25.12 w POS).
        tekstowe = [kolumna for kolumna, typ in zip(wynik.columns, wynik.types) if str(typ) == "VARCHAR"]
        return ramka.astype({kolumna: "str" for kolumna in tekstowe})

    def sprawdz(self, con: duckdb.DuckDBPyConnection, od: date, dzien: date) -> Wynik:
        """Sprawdza wszystkie wiersze z zakresu i zbiera wszystkie naruszenia naraz (lazy=True)."""
        try:
            ramka = self.ramka(con, od, dzien)
        except duckdb.Error as e:
            return Wynik(self, 0, {}, blad=f"{type(e).__name__}: {e}")
        if ramka.empty:  # nic do sprawdzenia, np. dzień bez korekt; brak całego dnia łapią reguły świeżości
            return Wynik(self, 0, {})
        try:
            self.schemat.validate(ramka, lazy=True)
            return Wynik(self, len(ramka), {})
        except pa.errors.SchemaErrors as e:
            return self._wynik_z_bledow(ramka, e.failure_cases)

    def _wynik_z_bledow(self, ramka: pd.DataFrame, przypadki: pd.DataFrame) -> Wynik:
        cala_ramka: set[str] = set()  # naruszenia bez wiersza (brak kolumny, zły typ) dotyczą wszystkich wierszy
        per_wiersz: dict[int, set[str]] = defaultdict(set)
        for przypadek in przypadki.itertuples(index=False):
            etykieta = _etykieta(przypadek, self.schemat)
            if pd.isna(przypadek.index):
                cala_ramka.add(etykieta)
            else:
                per_wiersz[int(przypadek.index)].add(etykieta)
        indeksy = list(ramka.index) if cala_ramka else sorted(per_wiersz)
        etykiety = [cala_ramka | per_wiersz.get(idx, set()) for idx in indeksy]
        bledne = ramka.loc[indeksy].assign(naruszenie=["; ".join(sorted(e)) for e in etykiety])
        return Wynik(self, len(ramka), dict(Counter(e for zbior in etykiety for e in zbior)), bledne)
