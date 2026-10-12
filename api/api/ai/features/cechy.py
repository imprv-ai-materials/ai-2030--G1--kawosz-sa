"""Cechy modelu churnu na dzień snapszotu, bez przecieków z przyszłości (definicje: cechy_snapszotu.sql)."""

from pathlib import Path

import duckdb
import pandas as pd

SQL = Path(__file__).parent / "cechy_snapszotu.sql"


def cechy_snapszotu(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """1 wiersz na wiersz tabeli snapshoty: klucze (id_biura, data_snapszotu) i cechy."""
    return con.sql(SQL.read_text()).df()
