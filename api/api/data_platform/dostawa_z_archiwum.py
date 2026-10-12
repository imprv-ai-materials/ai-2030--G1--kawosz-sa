"""Buduje dostawę jednego dnia w katalogu dostaw z archiwum w data/ (do prób nocnego potoku, data/ tylko czytamy).

Prawdziwych dostaw jeszcze nie ma, a archiwum w data/ to stan na 30.09.2026. Dostawa za dzień D zawiera to, co
systemy wysłałyby w nocy po D:
- POS: pliki z kas za D z pos_paragony.zip (z kopiami „ (1)”, jeśli kasa je wysłała) z czasem dostawy z archiwum,
  pozycje paragonów z D;
- ERP: dokumenty z D z pozycjami, płatności z D;
- e-commerce: zamówienia z D (dzień polski) z pozycjami, obciążenia subskrypcji z D, karty sprzedane albo
  zrealizowane w D, kurs NBP z D;
- słowniki (lokale, cenniki, kartoteka, kontrahenci) jako pełne migawki.

    PYTHONPATH=api poetry run python -m api.data_platform.dostawa_z_archiwum 2026-09-30
"""

import argparse
import os
import shutil
import zipfile
from datetime import date, datetime
from pathlib import Path

import duckdb

from api.data_platform.load_raw import DATA_DIR, PARAGONY_ZIP
from api.data_platform.noc import Ustawienia

DZIEN_PL = "timezone('Europe/Warsaw', {} AT TIME ZONE 'UTC')::DATE"
DZIEN_PARAGONU = "strptime((nr_paragonu // 10000)::VARCHAR, '%y%m%d')::DATE"

# plik dostawy → SQL wierszy z dnia $d; {nazwa} to plik parquet z data/
WYCINKI = {
    "pos": {
        "pos_pozycje": f"SELECT * FROM {{pos_pozycje}} WHERE {DZIEN_PARAGONU} = $d",
        "lokale": "SELECT * FROM {lokale}",
        "pos_produkty": "SELECT * FROM {pos_produkty}",
    },
    "erp": {
        "erp_faktury": "SELECT * FROM {erp_faktury} WHERE data = $d",
        "erp_pozycje": "SELECT * FROM {erp_pozycje} SEMI JOIN (SELECT nr_faktury FROM {erp_faktury} WHERE data = $d)"
        " USING (nr_faktury)",
        "erp_platnosci": "SELECT * FROM {erp_platnosci} WHERE data_platnosci = $d",
        "erp_kartoteka": "SELECT * FROM {erp_kartoteka}",
        "erp_kontrahenci": "SELECT * FROM {erp_kontrahenci}",
        "erp_kontrahenci_archiwum": "SELECT * FROM {erp_kontrahenci_archiwum}",
    },
    "ecom": {
        "ecom_zamowienia": f"SELECT * FROM {{ecom_zamowienia}} WHERE {DZIEN_PL.format('data_utc::TIMESTAMP')} = $d",
        "ecom_pozycje": "SELECT * FROM {ecom_pozycje} p SEMI JOIN (SELECT id FROM {ecom_zamowienia}"
        f" WHERE {DZIEN_PL.format('data_utc::TIMESTAMP')} = $d) z ON z.id = p.id_zamowienia",
        "ecom_subskrypcje": f"SELECT * FROM {{ecom_subskrypcje}} WHERE {DZIEN_PL.format('data_platnosci')} = $d",
        "karty_podarunkowe": "SELECT * FROM {karty_podarunkowe} WHERE data_sprzedazy = $d OR data_realizacji = $d",
        "kursy_nbp": "SELECT * FROM {kursy_nbp} WHERE data = $d",
        "ecom_produkty": "SELECT * FROM {ecom_produkty}",
    },
}


TABELE_Z_DATA = {
    nazwa: f"read_parquet('{next(DATA_DIR.rglob(f'{nazwa}.parquet'))}')"
    for nazwa in {nazwa for wycinki in WYCINKI.values() for nazwa in wycinki}
}


def zbuduj(dzien: date, dostawy: Path) -> Path:
    """Zastępuje katalog dostawy dnia D i zwraca go."""
    katalog = dostawy / str(dzien)
    shutil.rmtree(katalog, ignore_errors=True)
    (katalog / "pos").mkdir(parents=True)
    with zipfile.ZipFile(PARAGONY_ZIP) as zf:
        for info in zf.infolist():
            nazwa = Path(info.filename).name
            if nazwa.endswith(".csv") and f"_{dzien}" in nazwa:
                cel = katalog / "pos" / nazwa
                cel.write_bytes(zf.read(info))
                czas = datetime(*info.date_time).timestamp()  # czas dostawy = czas pliku w archiwum
                os.utime(cel, (czas, czas))

    con = duckdb.connect()
    try:
        for zrodlo, wycinki in WYCINKI.items():
            (katalog / zrodlo).mkdir(exist_ok=True)
            for plik, sql in wycinki.items():
                zapytanie = sql.format(**TABELE_Z_DATA).replace("$d", f"DATE '{dzien}'")
                con.execute(f"COPY ({zapytanie}) TO '{katalog / zrodlo / plik}.parquet' (FORMAT parquet)")
    finally:
        con.close()
    return katalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dzien", type=date.fromisoformat)
    args = parser.parse_args()
    katalog = zbuduj(args.dzien, Ustawienia.z_env().dostawy)
    for plik in sorted(katalog.rglob("*")):
        if plik.is_file():
            print(plik.relative_to(katalog))


if __name__ == "__main__":
    main()
