"""Uruchamia reguły jakości na kawosz.duckdb i zwraca kod 1, jeśli nie przeszła reguła blokująca.

Co noc (po load_raw), dla dnia eksportu:
    PYTHONPATH=api poetry run python -m api.data_platform.reguly.uruchom --dzien 2026-09-30

Przegląd okresu (np. całego września) i wybranych źródeł:
    PYTHONPATH=api poetry run python -m api.data_platform.reguly.uruchom \
        --od 2026-09-01 --dzien 2026-09-30 --zrodlo pos erp
"""

import argparse
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pandera.pandas as pa

from api.adapters.duckdb_conn import DB_PATH, connect
from api.data_platform.reguly import ecom, erp, pos
from api.data_platform.reguly.regula import Poziom, Regula

ZRODLA = {"pos": pos.REGULY, "erp": erp.REGULY, "ecom": ecom.REGULY}
PRZYKLADY = 3


@dataclass
class Wynik:
    regula: Regula
    wiersze: int
    bledne: int = 0
    naruszenia: dict[str, int] = field(default_factory=dict)  # naruszenie -> liczba wierszy
    przyklady: pd.DataFrame | None = None

    @property
    def ok(self) -> bool:
        return not self.naruszenia


def sprawdz(regula: Regula, con: duckdb.DuckDBPyConnection, od: date, dzien: date) -> Wynik:
    ramka = regula.ramka(con, od, dzien)
    if ramka.empty:  # nic do sprawdzenia, np. dzień bez korekt; brak całego dnia łapią reguły świeżości
        return Wynik(regula, 0)
    try:
        regula.schemat.validate(ramka, lazy=True)
        return Wynik(regula, len(ramka))
    except pa.errors.SchemaErrors as e:
        fc = e.failure_cases
        # Błąd schematu (brak kolumny, zły typ) nie ma indeksu wiersza — dotyczy całej ramki.
        cala_ramka = fc["index"].isna()
        naruszenia = {
            check: len(ramka) if grupa["index"].isna().any() else grupa["index"].nunique()
            for check, grupa in fc.assign(check=fc["check"].astype(str)).groupby("check")
        }
        indeksy = fc.loc[~cala_ramka, "index"].dropna().unique()
        return Wynik(
            regula,
            len(ramka),
            bledne=len(ramka) if cala_ramka.any() else len(indeksy),
            naruszenia=naruszenia,
            przyklady=ramka.loc[indeksy[:PRZYKLADY]] if len(indeksy) else None,
        )


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
        for naruszenie, n in w.naruszenia.items():
            print(f"  - {naruszenie}: {n}")
        if w.przyklady is not None:
            print(textwrap.indent(w.przyklady.to_string(max_colwidth=40), "    "))


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
    args = parser.parse_args()
    od = args.od or args.dzien

    reguly = [r for z in args.zrodlo for r in ZRODLA[z] if not args.regula or r.id in args.regula]
    con = connect(read_only=True, db_path=args.baza)
    try:
        wyniki = [sprawdz(r, con, od, args.dzien) for r in reguly]
    finally:
        con.close()

    print(f"Reguły jakości, zakres {od} – {args.dzien}\n")
    wypisz(wyniki)
    blokujace = [w.regula.id for w in wyniki if not w.ok and w.regula.poziom == Poziom.BLOKUJE]
    print(f"\nBlokujące z błędem: {', '.join(blokujace) or 'brak'}")
    sys.exit(1 if blokujace else 0)


if __name__ == "__main__":
    main()
