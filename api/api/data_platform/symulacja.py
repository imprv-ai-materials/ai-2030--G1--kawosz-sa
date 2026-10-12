"""Symulacja nocnego potoku na zakresie dni: jak wyglądałyby dane, gdyby noc działała od dnia `od`.

Prawdziwego potoku jeszcze nie było, więc panel jakości (ui/) nie ma historii. Symulacja ją buduje:
1. kopiuje kawosz.duckdb do katalogu symulacji (kawosz.duckdb zostaje bez zmian);
2. w kopii cofa dane do stanu przed `od`: usuwa to, co przyniosłyby dostawy z dni od – do (paragony, faktury,
   zamówienia, …), a kartom zrealizowanym w tych dniach zdejmuje realizację;
3. buduje dostawy z archiwum w data/ (dostawa_z_archiwum.py) i uruchamia noc po nocy ten sam przebieg co Inngest.

Do raportów trafiają więc tylko wsady, które przeszły reguły, jak w prawdziwym potoku.

    PYTHONPATH=api poetry run python -m api.data_platform.symulacja --od 2026-09-01 --do 2026-09-30
    KAWOSZ_BAZA=_symulacja/kawosz.duckdb …                    # panel jakości na danych z symulacji
"""

import argparse
import shutil
from datetime import date, timedelta
from pathlib import Path

import duckdb

from api.adapters.duckdb_conn import DB_PATH, PROJECT_ROOT
from api.data_platform import dostawa_z_archiwum, noc

KATALOG = PROJECT_ROOT / "_symulacja"
DZIEN_PL = dostawa_z_archiwum.DZIEN_PL
DZIEN_PARAGONU = dostawa_z_archiwum.DZIEN_PARAGONU

# Stan przed nocą `od`: bez dokumentów z dni $od – $do (te same wycinki co w dostawach) i bez mostu tych miesięcy.
COFNIJ = f"""
    DELETE FROM pos_paragony WHERE plik IN (SELECT plik FROM pos_pliki WHERE dzien BETWEEN $od AND $do);
    DELETE FROM pos_pliki WHERE dzien BETWEEN $od AND $do;
    DELETE FROM pos_pozycje WHERE {DZIEN_PARAGONU} BETWEEN $od AND $do;
    DELETE FROM erp_pozycje WHERE nr_faktury IN (SELECT nr_faktury FROM erp_faktury WHERE data BETWEEN $od AND $do);
    DELETE FROM erp_faktury WHERE data BETWEEN $od AND $do;
    DELETE FROM erp_platnosci WHERE data_platnosci BETWEEN $od AND $do;
    DELETE FROM ecom_pozycje WHERE id_zamowienia IN (
        SELECT id FROM ecom_zamowienia WHERE {DZIEN_PL.format("data_utc::TIMESTAMP")} BETWEEN $od AND $do);
    DELETE FROM ecom_zamowienia WHERE {DZIEN_PL.format("data_utc::TIMESTAMP")} BETWEEN $od AND $do;
    DELETE FROM ecom_subskrypcje WHERE {DZIEN_PL.format("data_platnosci")} BETWEEN $od AND $do;
    UPDATE karty_podarunkowe SET data_realizacji = NULL
        WHERE data_realizacji BETWEEN $od AND $do AND data_sprzedazy < $od;
    DELETE FROM karty_podarunkowe WHERE data_sprzedazy BETWEEN $od AND $do;
    DELETE FROM kursy_nbp WHERE data BETWEEN $od AND $do;
    DELETE FROM most_przychodu WHERE miesiac BETWEEN date_trunc('month', $od::DATE) AND $do;
    DROP TABLE IF EXISTS kwarantanna; DROP TABLE IF EXISTS wsady; DROP TABLE IF EXISTS naruszenia;
"""


def przygotuj(od: date, do: date, katalog: Path = KATALOG, zrodlo: Path = DB_PATH) -> noc.Ustawienia:
    """Kopia bazy cofnięta do stanu przed `od` i dostawy dni od – do. Zastępuje poprzednią symulację."""
    shutil.rmtree(katalog, ignore_errors=True)
    katalog.mkdir(parents=True)
    ust = noc.Ustawienia(baza=katalog / "kawosz.duckdb", dostawy=katalog / "dostawy", raporty=katalog / "kwarantanna")
    shutil.copy(zrodlo, ust.baza)
    con = duckdb.connect(str(ust.baza))
    try:
        sql = COFNIJ.replace("$od", f"DATE '{od}'").replace("$do", f"DATE '{do}'")
        con.execute(sql)
    finally:
        con.close()
    for dzien in dni(od, do):
        dostawa_z_archiwum.zbuduj(dzien, ust.dostawy)
    return ust


def dni(od: date, do: date) -> list[date]:
    return [od + timedelta(days=i) for i in range((do - od).days + 1)]


def main() -> None:
    from api.inngest_app import przebieg  # orkiestrator zależy od data_platform, nie odwrotnie

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--od", type=date.fromisoformat, default=date(2026, 9, 1))
    parser.add_argument("--do", type=date.fromisoformat, default=date(2026, 9, 30))
    parser.add_argument("--katalog", type=Path, default=KATALOG)
    args = parser.parse_args()

    ust = przygotuj(args.od, args.do, args.katalog)
    for dzien in dni(args.od, args.do):
        wynik = przebieg(dzien, ust)
        statusy = ", ".join(f"{z}: {w['status']}" for z, w in wynik["wsady"].items())
        print(f"{dzien}  {statusy}  | przychód netto {wynik['most']['miesiac']}: {wynik['most']['przychod_netto']:,.2f} zł")
    print(f"\nBaza symulacji: {ust.baza}")


if __name__ == "__main__":
    main()
