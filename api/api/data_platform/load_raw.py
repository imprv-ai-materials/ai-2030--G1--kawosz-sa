"""Ładuje surowe pliki z data/ do kawosz.duckdb — jedna tabela na plik, nazwa tabeli = nazwa pliku.

data/ jest tylko do odczytu, więc paragony z data/pos/pos_paragony.zip rozpakowujemy do
_staging/pos/ (poza data/, w .gitignore).

Uruchomienie: PYTHONPATH=api poetry run python -m api.data_platform.load_raw
"""

import shutil
import zipfile

from api.adapters.duckdb_conn import PROJECT_ROOT, connect

DATA_DIR = PROJECT_ROOT / "data"
STAGING_DIR = PROJECT_ROOT / "_staging"
PARAGONY_ZIP = DATA_DIR / "pos" / "pos_paragony.zip"
PARAGONY_DIR = STAGING_DIR / "pos"

# Generator danych — zakazany (patrz CLAUDE.md).
EXCLUDED_DIRS = {"kawosz_gen"}

# Format dostawcy POS: CP1250, separator ';', przecinek dziesiętny, kwoty brutto.
# Od 2026-06-01 pliki mają dodatkową kolumnę `kanal` (po data_czas) — łączymy po nazwach,
# więc dla starszych plików kanal = NULL.
PARAGONY_TYPES = {
    "lokal": "INTEGER",
    "nr_paragonu": "BIGINT",
    "data_czas": "TIMESTAMP",
    "kanal": "VARCHAR",
    "kwota_brutto": "DECIMAL(12,2)",
    "metoda_platnosci": "VARCHAR",
    "storno": "INTEGER",
}


def extract_paragony() -> str:
    """Rozpakowuje dzienne pliki paragonów i zwraca glob do nich."""
    shutil.rmtree(PARAGONY_DIR, ignore_errors=True)
    PARAGONY_DIR.mkdir(parents=True)
    with zipfile.ZipFile(PARAGONY_ZIP) as zf:
        zf.extractall(PARAGONY_DIR)
    return str(PARAGONY_DIR / "paragony" / "*.csv")


def parquet_files():
    for path in sorted(DATA_DIR.rglob("*.parquet")):
        if EXCLUDED_DIRS.isdisjoint(path.relative_to(DATA_DIR).parts):
            yield path


def main() -> None:
    con = connect(read_only=False)
    try:
        for path in parquet_files():
            con.execute(f"CREATE OR REPLACE TABLE {path.stem} AS SELECT * FROM read_parquet(?)", [str(path)])
            print(f"{path.stem}: {con.table(path.stem).count('*').fetchone()[0]} wierszy")

        con.execute(
            """
            CREATE OR REPLACE TABLE pos_paragony AS
            SELECT * EXCLUDE (filename), parse_filename(filename) AS plik
            FROM read_csv(?, encoding = 'CP1250', delim = ';', decimal_separator = ',',
                          header = true, types = ?, union_by_name = true, filename = true)
            """,
            [extract_paragony(), PARAGONY_TYPES],
        )
        print(f"pos_paragony: {con.table('pos_paragony').count('*').fetchone()[0]} wierszy")
    finally:
        con.close()


if __name__ == "__main__":
    main()
