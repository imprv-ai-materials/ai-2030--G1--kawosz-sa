"""Połączenie z lokalną bazą analityczną kawosz.duckdb (katalog główny repozytorium)."""

from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = PROJECT_ROOT / "kawosz.duckdb"


def connect(read_only: bool = True, db_path: Path = DB_PATH) -> duckdb.DuckDBPyConnection:
    """Otwiera połączenie z bazą. Domyślnie tylko do odczytu — zapis tylko przy ładowaniu danych."""
    return duckdb.connect(str(db_path), read_only=read_only)
