"""Uruchamia reguły jakości na kawosz.duckdb i zwraca kod 1, jeśli nie przeszła reguła blokująca.

Co noc (po load_raw), dla dnia eksportu:
    PYTHONPATH=api poetry run python -m api.data_platform.reguly.uruchom --dzien 2026-09-30

Przegląd okresu (np. całego września) i wybranych źródeł:
    PYTHONPATH=api poetry run python -m api.data_platform.reguly.uruchom \
        --od 2026-09-01 --dzien 2026-09-30 --zrodlo pos erp

Raport naruszeń w Markdown:
    PYTHONPATH=api poetry run python -m api.data_platform.reguly.uruchom \
        --od 2026-09-01 --dzien 2026-09-30 --raport docs/naruszenia_2026-09.md

Każda reguła sprawdza wszystkie wiersze i zbiera wszystkie naruszenia naraz; błąd jednej reguły
nie przerywa pozostałych.
"""

import argparse
import sys
import textwrap
from datetime import date, timedelta
from pathlib import Path

from api.adapters.duckdb_conn import DB_PATH, connect
from api.data_platform.reguly import ecom, erp, pos, raport
from api.data_platform.reguly.regula import Wynik

ZRODLA = {"pos": pos.REGULY, "erp": erp.REGULY, "ecom": ecom.REGULY}
PRZYKLADY = 3


def wypisz(wyniki: list[Wynik]) -> None:
    print(f"{'reguła':<8} {'poziom':<9} {'wynik':<5} {'sprawdzone':>10} {'błędne':>8}  skala   właściciel")
    for w in wyniki:
        r = w.regula
        skala = ",".join(f"#{n}" for n in r.skala) or "—"
        print(
            f"{r.id:<8} {r.poziom:<9} {'OK' if w.ok else 'BŁĄD':<5} {w.wiersze:>10} {w.bledne:>8}"
            f"  {skala:<7} {r.wlasciciel}"
        )
    for w in (w for w in wyniki if not w.ok):
        print(f"\n{w.regula.id} [{w.regula.poziom}] {w.regula.opis}")
        if w.blad:
            print(f"  - nie udało się wykonać: {w.blad}")
            continue
        for naruszenie, n in w.naruszenia.items():
            print(f"  - {naruszenie}: {n}")
        print(textwrap.indent(w.przyklady(PRZYKLADY).to_string(max_colwidth=40), "    "))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dzien",
        type=date.fromisoformat,
        default=date.today() - timedelta(days=1),
        help="dzień eksportu (domyślnie wczoraj)",
    )
    parser.add_argument("--od", type=date.fromisoformat, help="początek zakresu (domyślnie = --dzien)")
    parser.add_argument("--zrodlo", nargs="+", choices=ZRODLA, default=list(ZRODLA))
    parser.add_argument("--regula", nargs="+", help="tylko wybrane reguły, np. POS-02 ERP-06")
    parser.add_argument("--baza", type=Path, default=DB_PATH, help="plik DuckDB (domyślnie kawosz.duckdb)")
    parser.add_argument("--raport", type=Path, help="zapisz raport naruszeń w Markdown do tego pliku")
    args = parser.parse_args()
    od = args.od or args.dzien

    reguly = [r for z in args.zrodlo for r in ZRODLA[z] if not args.regula or r.id in args.regula]
    con = connect(read_only=True, db_path=args.baza)
    try:
        wyniki = [r.sprawdz(con, od, args.dzien) for r in reguly]
    finally:
        con.close()

    print(f"Reguły jakości, zakres {od} – {args.dzien}\n")
    wypisz(wyniki)
    if args.raport:
        argumenty = sys.argv[1:]
        if "--baza" in argumenty:  # ścieżka do kopii bazy nie należy do raportu
            del argumenty[argumenty.index("--baza") : argumenty.index("--baza") + 2]
        polecenie = "PYTHONPATH=api poetry run python -m api.data_platform.reguly.uruchom " + " ".join(argumenty)
        args.raport.write_text(raport.markdown(wyniki, od, args.dzien, polecenie))
        print(f"\nRaport: {args.raport}")
    blokujace = [w.regula.id for w in wyniki if w.blokuje]
    print(f"\nBlokujące z błędem: {', '.join(blokujace) or 'brak'}")
    sys.exit(1 if blokujace else 0)


if __name__ == "__main__":
    main()
