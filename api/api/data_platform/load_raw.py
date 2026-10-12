"""Ładuje surowe pliki z data/ do kawosz.duckdb — jedna tabela na plik, nazwa tabeli = nazwa pliku.

data/ jest tylko do odczytu, więc paragony z data/pos/pos_paragony.zip rozpakowujemy do
_staging/pos/ (poza data/, w .gitignore).

Format plików z kasy i typy kolumn pochodzą z kontraktu kontrakty/pos_paragony.yaml. Oprócz paragonów
loader zapisuje rejestr dostarczonych plików `pos_pliki` (nagłówek, liczba wierszy, czas dostawy),
bo po złączeniu plików w jedną tabelę nie widać już, które kolumny miał który plik.

Uruchomienie: PYTHONPATH=api poetry run python -m api.data_platform.load_raw
"""

import re
import shutil
import zipfile
from datetime import date
from pathlib import Path

from api.adapters.duckdb_conn import PROJECT_ROOT, connect
from api.data_platform.kontrakty.kontrakt import wczytaj

DATA_DIR = PROJECT_ROOT / "data"
STAGING_DIR = PROJECT_ROOT / "_staging"
PARAGONY_ZIP = DATA_DIR / "pos" / "pos_paragony.zip"
PARAGONY_DIR = STAGING_DIR / "pos"

# Generator danych — zakazany (patrz CLAUDE.md).
EXCLUDED_DIRS = {"kawosz_gen"}

KONTRAKT_POS = wczytaj("pos_paragony")


def wzorzec_pliku(plik: str) -> re.Pattern:
    """Lokal i dzień z nazwy pliku wg kontraktu. Dopisek po dniu (np. „ (1)”) nie przeszkadza: nazwę sprawdza POS-03."""
    do_dnia = re.escape(plik.split("{dzien}")[0]).replace(re.escape("{lokal}"), r"(?P<lokal>\d+)")
    return re.compile(do_dnia + r"(?P<dzien>\d{4}-\d{2}-\d{2})")


def rejestr_plikow(katalog: Path) -> list[tuple]:
    """Jeden wiersz na plik z kasy: nazwa, lokal i dzień z nazwy, kolumny z nagłówka, liczba wierszy, czas dostawy.

    Archiwum ZIP nie ma czasu dostawy (wszystkie pliki mają w nim datę spakowania 30.09.2026 23:59), więc
    czas_dostawy = NULL i POS-13 nie ma czego sprawdzić. W nocnym potoku trafia tu czas, w którym plik
    pojawił się w katalogu dostaw.
    """
    dostawa = KONTRAKT_POS.dostawa
    wzorzec = wzorzec_pliku(dostawa.plik)
    rejestr = []
    for sciezka in sorted(katalog.glob("*.csv")):
        with sciezka.open(encoding=dostawa.kodowanie, errors="replace", newline="") as plik:
            naglowek = plik.readline().rstrip("\r\n")
            wiersze = sum(1 for _ in plik)
        nazwa = wzorzec.match(sciezka.name)
        rejestr.append(
            (
                sciezka.name,
                int(nazwa["lokal"]) if nazwa else None,
                date.fromisoformat(nazwa["dzien"]) if nazwa else None,
                naglowek.split(dostawa.separator) if naglowek else [],
                wiersze,
                None,
            )
        )
    return rejestr


def typy_paragonow(kolumny_w_plikach: set[str]) -> dict[str, str]:
    """Typy z kontraktu dla kolumn, które są w plikach (DuckDB odrzuca typ dla kolumny, której nie ma).

    Kolumnę spoza kontraktu (od 2026-06-01: `kanal`) DuckDB wczyta z typem, który sam rozpozna. Pliki
    łączymy po nazwach kolumn, więc w starszych plikach ma ona NULL. Zmianę układu kolumn zgłasza POS-12.
    """
    return {k.nazwa: k.typ for k in KONTRAKT_POS.kolumny if k.nazwa in kolumny_w_plikach}


def extract_paragony() -> Path:
    """Rozpakowuje dzienne pliki paragonów i zwraca katalog z nimi."""
    shutil.rmtree(PARAGONY_DIR, ignore_errors=True)
    PARAGONY_DIR.mkdir(parents=True)
    with zipfile.ZipFile(PARAGONY_ZIP) as zf:
        zf.extractall(PARAGONY_DIR)
    return PARAGONY_DIR / "paragony"


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

        katalog = extract_paragony()
        rejestr = rejestr_plikow(katalog)
        con.execute(
            """
            CREATE OR REPLACE TABLE pos_pliki (
                plik VARCHAR, lokal INTEGER, dzien DATE, kolumny VARCHAR[], wiersze INTEGER, czas_dostawy TIMESTAMP)
            """
        )
        con.executemany("INSERT INTO pos_pliki VALUES (?, ?, ?, ?, ?, ?)", rejestr)
        print(f"pos_pliki: {len(rejestr)} plików")

        dostawa = KONTRAKT_POS.dostawa
        con.execute(
            """
            CREATE OR REPLACE TABLE pos_paragony AS
            SELECT * EXCLUDE (filename), parse_filename(filename) AS plik
            FROM read_csv(?, encoding = ?, delim = ?, decimal_separator = ?,
                          header = ?, types = ?, union_by_name = true, filename = true)
            """,
            [
                str(katalog / "*.csv"),
                dostawa.kodowanie,
                dostawa.separator,
                dostawa.separator_dziesietny,
                dostawa.naglowek,
                typy_paragonow({kolumna for wiersz in rejestr for kolumna in wiersz[3]}),
            ],
        )
        print(f"pos_paragony: {con.table('pos_paragony').count('*').fetchone()[0]} wierszy")
    finally:
        con.close()


if __name__ == "__main__":
    main()
