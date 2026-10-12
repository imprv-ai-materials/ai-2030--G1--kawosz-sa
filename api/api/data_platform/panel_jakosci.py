"""Dane panelu jakości dla finansów (ui/): wsady z ostatnich dni, wynik każdej reguły, wycena i most przychodu.

Czyta tabele, które zapisuje nocny potok (noc.py: wsady, naruszenia; revenue_bc: most_przychodu), a opisy reguł
i to, co zrobić przy naruszeniu, bierze z kontraktów. Niczego nie liczy od nowa, więc panel pokazuje dokładnie
to, co postanowiła noc.

    GET /api/jakosc?dni=30
"""

from datetime import date, timedelta
from pathlib import Path

import duckdb

from api.adapters.duckdb_conn import PROJECT_ROOT, connect
from api.data_platform.kontrakty.kontrakt import wczytaj
from api.data_platform.noc import ZRODLA
from api.data_platform.reguly.uruchom import ZRODLA as REGULY

KONTRAKTY = {"pos": "pos_paragony", "erp": "erp_faktury", "ecom": "ecom_zamowienia"}
NAZWY_ZRODEL = {
    "pos": "Kasy w lokalach (POS)",
    "erp": "Faktury B2B (ERP)",
    "ecom": "Sklep internetowy",
}
OPISY_ZRODEL = {
    "pos": "Paragony z 24 kawiarni: jeden plik z każdej kasy za każdy dzień.",
    "erp": "Faktury i korekty dla klientów biznesowych, płatności, kartoteka towarów i kontrahentów.",
    "ecom": "Zamówienia, subskrypcje „Kawosz co miesiąc”, karty podarunkowe i kurs euro.",
}


class BrakDanych(Exception):
    """Nocny potok jeszcze nie zapisał wyników (brak tabeli wsady)."""


def _reguly() -> list[dict]:
    wynik = []
    for zrodlo in ZRODLA:
        kontrakt = wczytaj(KONTRAKTY[zrodlo])
        for r in REGULY[zrodlo]:
            wynik.append(
                {
                    "id": r.id,
                    "zrodlo": zrodlo,
                    "opis": r.opis,
                    "poziom": str(r.poziom),
                    "wlasciciel": str(r.wlasciciel),
                    "jednostka": r.jednostka,
                    "co_zrobic": " ".join(kontrakt.reguly[r.id].co_zrobic.split()),
                }
            )
    return wynik


def _wiersze(con: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> list[dict]:
    wynik = con.execute(sql, params or [])
    kolumny = [k[0] for k in wynik.description]
    return [dict(zip(kolumny, w)) for w in wynik.fetchall()]


def dane(baza: Path, dni: int = 30) -> dict:
    """Wszystko, czego potrzebuje panel, za `dni` ostatnich dni z wynikiem nocy (licząc od ostatniego wsadu)."""
    baza = baza.resolve()
    con = connect(read_only=True, db_path=baza)
    try:
        tabele = {t for (t,) in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
        if not {"wsady", "naruszenia"} <= tabele:
            raise BrakDanych("Nocny potok jeszcze nie działał na tej bazie: brak tabel wsady i naruszenia.")
        ostatni: date | None = con.execute("SELECT max(dzien) FROM wsady").fetchone()[0]
        if ostatni is None:
            raise BrakDanych("Nocny potok nie zapisał jeszcze żadnego wsadu.")
        od = ostatni - timedelta(days=dni - 1)
        wsady = _wiersze(
            con,
            """SELECT dzien, zrodlo, status, reguly AS blokujace, przychod_netto::DOUBLE AS przychod_netto,
                      zawyzenie::DOUBLE AS zawyzenie, wycena_uwaga, raport, wiersze, zapisano
               FROM wsady WHERE dzien BETWEEN ? AND ? ORDER BY dzien, zrodlo""",
            [od, ostatni],
        )
        naruszenia = _wiersze(
            con,
            """SELECT dzien, zrodlo, regula, sprawdzone, bledne, blad
               FROM naruszenia WHERE dzien BETWEEN ? AND ? ORDER BY dzien, regula""",
            [od, ostatni],
        )
        most = (
            _wiersze(
                con,
                """SELECT miesiac, krok, opis, kwota_pln::DOUBLE AS kwota_pln,
                          suma_po_kroku::DOUBLE AS suma_po_kroku
                   FROM most_przychodu ORDER BY miesiac, rowid""",
            )
            if "most_przychodu" in tabele
            else []
        )
    finally:
        con.close()
    return {
        "baza": str(baza.relative_to(PROJECT_ROOT)) if baza.is_relative_to(PROJECT_ROOT) else baza.name,
        "od": od,
        "do": ostatni,
        "dni": dni,
        "zrodla": [{"id": z, "nazwa": NAZWY_ZRODEL[z], "opis": OPISY_ZRODEL[z]} for z in ZRODLA],
        "reguly": _reguly(),
        "wsady": wsady,
        "naruszenia": naruszenia,
        "most": most,
    }
