"""Tabela cechy_treningowe w kawosz.duckdb: cechy z sql/<rodzina>.sql na każdą datę t0 i etykieta ze snapshoty.

Każdy plik sql/<rodzina>.sql przyjmuje parametr $t0 i zwraca 1 wiersz na biuro z populacji w t0 (umowa trwa, brak
wypowiedzenia przed t0): id_biura, t0 i cechy rodziny, liczone tylko z rekordów, które do t0 dotarły (opóźnienia
źródeł: docs/opoznienia_danych.md). Opisy cech: katalog.yaml.
Na produkcji te same pliki liczą cechy na dzisiejsze t0 (policz_cechy), tylko bez etykiety.

    PYTHONPATH=api poetry run python -m api.ai.features.build                         # wszystkie daty snapshoty
    PYTHONPATH=api poetry run python -m api.ai.features.build 2026-05-01 2026-06-01
"""

import sys
from datetime import date
from pathlib import Path

import duckdb

from api.adapters.duckdb_conn import connect

KATALOG_SQL = Path(__file__).parent / "sql"
RODZINY = ["umowa", "uzycie", "zamowienia", "platnosci", "serwis", "relacja", "firmografia"]
KLUCZ = ["id_biura", "t0"]
TABELA = "cechy_treningowe"


def _policz_rodzine(con: duckdb.DuckDBPyConnection, rodzina: str, daty_t0: list[date]) -> str:
    """Wyniki sql/<rodzina>.sql dla wszystkich dat w tabeli tymczasowej; zwraca jej nazwę."""
    tabela = f"_rodzina_{rodzina}"
    sql = (KATALOG_SQL / f"{rodzina}.sql").read_text().strip().rstrip(";")
    con.execute(f"CREATE OR REPLACE TEMP TABLE {tabela} AS\n{sql}", {"t0": daty_t0[0]})
    for t0 in daty_t0[1:]:
        con.execute(f"INSERT INTO {tabela}\n{sql}", {"t0": t0})
    return tabela


def _sprawdz_rodziny(con: duckdb.DuckDBPyConnection, tabele: list[str]) -> None:
    """Rodziny muszą mieć 1 wiersz na (id_biura, t0), tę samą populację i różne nazwy cech, inaczej złączenie kłamie."""
    widziane: dict[str, str] = {}
    for tabela in tabele:
        for kolumna in con.sql(f"SELECT * FROM {tabela} LIMIT 0").columns:
            if kolumna in KLUCZ:
                continue
            if kolumna in widziane:
                raise ValueError(f"cecha {kolumna} jest w {widziane[kolumna]} i w {tabela}")
            widziane[kolumna] = tabela
        wiersze, klucze = con.sql(f"SELECT count(*), count(DISTINCT (id_biura, t0)) FROM {tabela}").fetchone()
        if wiersze != klucze:
            raise ValueError(f"{tabela}: {wiersze - klucze} powtórzonych wierszy (id_biura, t0)")
    wzor = tabele[0]
    for tabela in tabele[1:]:
        (rozne,) = con.sql(f"""
            SELECT count(*) FROM (
                (SELECT id_biura, t0 FROM {wzor} EXCEPT SELECT id_biura, t0 FROM {tabela})
                UNION ALL
                (SELECT id_biura, t0 FROM {tabela} EXCEPT SELECT id_biura, t0 FROM {wzor})
            )
        """).fetchone()
        if rozne:
            raise ValueError(f"{tabela} i {wzor} mają różne populacje biur ({rozne} kluczy w jednej, a nie w drugiej)")


def _zapytanie_cech(con: duckdb.DuckDBPyConnection, daty_t0: list[date]) -> str:
    if not daty_t0:
        raise ValueError("pusta lista dat t0")
    tabele = [_policz_rodzine(con, rodzina, list(daty_t0)) for rodzina in RODZINY]
    _sprawdz_rodziny(con, tabele)
    zlaczenia = "\n".join(f"JOIN {tabela} USING (id_biura, t0)" for tabela in tabele[1:])
    return f"SELECT * FROM {tabele[0]}\n{zlaczenia}"


def policz_cechy(con: duckdb.DuckDBPyConnection, daty_t0: list[date]) -> duckdb.DuckDBPyRelation:
    """Wszystkie rodziny dla każdej daty t0, złączone po (id_biura, t0): 1 wiersz na biuro z populacji × t0."""
    return con.sql(_zapytanie_cech(con, daty_t0))


def zbuduj_cechy_treningowe(daty_t0: list[date], con: duckdb.DuckDBPyConnection | None = None) -> int:
    """Liczy cechy na każdą datę t0, dokleja odejdzie_90d ze snapshoty i zapisuje tabelę cechy_treningowe.

    Populacja w sql/ i w snapshoty jest ta sama, więc każdy wiersz cech musi mieć etykietę, a każdy wiersz snapshoty
    z tych dat musi mieć cechy. Inaczej (np. t0 spoza dat snapshoty) przerywa, zanim nadpisze tabelę. Bez `con`
    zapisuje do kawosz.duckdb. Zwraca liczbę wierszy.
    """
    wlasne = con is None
    con = connect(read_only=False) if wlasne else con
    try:
        con.execute(f"CREATE OR REPLACE TEMP TABLE _cechy AS\n{_zapytanie_cech(con, daty_t0)}")
        con.execute(
            "CREATE OR REPLACE TEMP TABLE _daty AS SELECT CAST(unnest($daty) AS DATE) AS t0", {"daty": list(daty_t0)}
        )
        (bez_etykiety,) = con.sql("""
            SELECT count(*) FROM _cechy c
            WHERE NOT EXISTS (SELECT 1 FROM snapshoty s WHERE s.id_biura = c.id_biura AND s.data_snapszotu = c.t0)
        """).fetchone()
        (bez_cech,) = con.sql("""
            SELECT count(*) FROM snapshoty s
            WHERE s.data_snapszotu IN (SELECT t0 FROM _daty)
              AND NOT EXISTS (SELECT 1 FROM _cechy c WHERE c.id_biura = s.id_biura AND c.t0 = s.data_snapszotu)
        """).fetchone()
        if bez_etykiety or bez_cech:
            raise ValueError(
                f"populacja cech i snapshoty się różni: {bez_etykiety} wierszy cech bez etykiety, "
                f"{bez_cech} wierszy snapshoty bez cech"
            )
        con.execute(f"""
            CREATE OR REPLACE TABLE {TABELA} AS
            SELECT c.*, s.odejdzie_90d
            FROM _cechy c
            JOIN snapshoty s ON s.id_biura = c.id_biura AND s.data_snapszotu = c.t0
            ORDER BY c.t0, c.id_biura
        """)
        con.execute("DROP TABLE _cechy; DROP TABLE _daty")
        (wiersze,) = con.sql(f"SELECT count(*) FROM {TABELA}").fetchone()
        return wiersze
    finally:
        if wlasne:
            con.close()


def daty_snapszotow(con: duckdb.DuckDBPyConnection) -> list[date]:
    return [d for (d,) in con.sql("SELECT DISTINCT data_snapszotu FROM snapshoty ORDER BY 1").fetchall()]


def main(argv: list[str]) -> None:
    if argv:
        daty = [date.fromisoformat(a) for a in argv]
    else:
        con = connect(read_only=True)
        try:
            daty = daty_snapszotow(con)
        finally:
            con.close()
    wiersze = zbuduj_cechy_treningowe(daty)
    print(f"{TABELA}: {wiersze} wierszy, {len(daty)} dat t0 ({daty[0]} … {daty[-1]})")


if __name__ == "__main__":
    main(sys.argv[1:])
