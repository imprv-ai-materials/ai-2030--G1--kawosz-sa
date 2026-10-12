"""Nocny potok danych: wsad z katalogu dostaw → reguły jakości → publikacja albo kwarantanna.

Wsad to dostawa jednego źródła (pos, erp, ecom) za jeden dzień D. Pliki leżą w katalogu dostaw:

    _dostawy/RRRR-MM-DD/pos/pos_paragony_{lokal}_{dzien}.csv   pliki z kas w formacie z kontraktu
    _dostawy/RRRR-MM-DD/pos/pos_pozycje.parquet                 i pozostałe tabele: plik = nazwa tabeli
    _dostawy/RRRR-MM-DD/erp/erp_faktury.parquet …
    _dostawy/RRRR-MM-DD/ecom/ecom_zamowienia.parquet …

Każdy krok to osobna funkcja, którą orkiestrator (inngest_app.py) uruchamia jako osobny krok Inngest:

1. `wczytaj`: pliki wsadu → schemat roboczy `wsad_RRRRMMDD` w kawosz.duckdb. Opublikowane tabele bez zmian.
2. `sprawdz`: reguły jakości źródła na „kandydacie”, czyli opublikowanych tabelach z podmienionymi wierszami
   wsadu (widoki tymczasowe o nazwach tabel, więc reguły działają bez zmian). Przy błędzie blokującym zapisuje
   raport naruszeń w docs/kwarantanna/. Wycenę wsadu (ile przychodu niesie) liczy orkiestrator na widokach
   z `widok_wsadu`, bo definicja przychodu należy do revenue_bc.
3. `odloz` (błąd blokujący): wiersze wsadu → tabela `kwarantanna`; opublikowane tabele bez zmian.
   `opublikuj` (brak błędu blokującego): wiersze wsadu → opublikowane tabele.
   Oba kroki zapisują status, wycenę i wynik każdej reguły w tabelach `wsady` i `naruszenia` (panel jakości).
4. `sprzataj`: usuwa schemat roboczy.

Każdy krok jest idempotentny, więc ponowienie po awarii albo drugi przebieg tej samej nocy daje te same liczby:
- wczytanie zastępuje tabele robocze, a nie dopisuje do nich;
- publikacja zastępuje wiersze po kluczu (np. plik z kasy po nazwie, fakturę po numerze), w jednej transakcji;
- kwarantanna i rejestr `wsady` zastępują zapis tego samego wsadu (źródło + dzień).

Zdublowany plik z kasy („… (1).csv”) to inny plik, więc nie nadpisuje oryginału, tylko trafia do wsadu obok
niego. Wtedy łapie go POS-02 i wsad idzie do kwarantanny, zamiast po cichu zniknąć.
"""

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb

from api.adapters.duckdb_conn import DB_PATH, PROJECT_ROOT, connect
from api.data_platform import load_raw
from api.data_platform.reguly import raport
from api.data_platform.reguly.uruchom import ZRODLA as REGULY


@dataclass(frozen=True)
class Tabela:
    nazwa: str
    # Klucz, po którym wiersz wsadu zastępuje opublikowane wiersze. Pusty: tabela przychodzi jako pełna migawka
    # (słownik), a jej brak w dostawie zostawia opublikowaną wersję.
    klucz: tuple[str, ...] = ()
    przychod: bool = False  # dokumenty, z których definicja liczy przychód (wycena wsadu)

    @property
    def migawka(self) -> bool:
        return not self.klucz


TABELE: dict[str, list[Tabela]] = {
    "pos": [
        Tabela("pos_paragony", ("plik",), przychod=True),
        Tabela("pos_pliki", ("plik",)),
        Tabela("pos_pozycje", ("lokal", "nr_paragonu"), przychod=True),
        Tabela("lokale"),
        Tabela("pos_produkty"),
    ],
    "erp": [
        Tabela("erp_faktury", ("nr_faktury",), przychod=True),
        Tabela("erp_pozycje", ("nr_faktury",)),
        Tabela("erp_platnosci", ("nr_faktury", "data_platnosci")),
        Tabela("erp_kartoteka"),
        Tabela("erp_kontrahenci"),
        Tabela("erp_kontrahenci_archiwum"),
    ],
    "ecom": [
        Tabela("ecom_zamowienia", ("id",), przychod=True),
        Tabela("ecom_pozycje", ("id_zamowienia",)),
        Tabela("ecom_subskrypcje", ("id", "data_platnosci"), przychod=True),
        # realizacja karty sprzedanej wcześniej zmienia istniejący wiersz
        Tabela("karty_podarunkowe", ("kod",), przychod=True),
        Tabela("kursy_nbp", ("data",)),
        Tabela("ecom_produkty"),
    ],
}
ZRODLA = list(TABELE)
POLECENIE = "nocny potok kawosz-noc (api/api/inngest_app.py), krok sprawdz-{zrodlo} dla dnia {dzien}"


@dataclass(frozen=True)
class Ustawienia:
    baza: Path = DB_PATH
    dostawy: Path = PROJECT_ROOT / "_dostawy"
    raporty: Path = PROJECT_ROOT / "docs" / "kwarantanna"
    wykresy_psi: Path = PROJECT_ROOT / "docs" / "img" / "psi"

    @classmethod
    def z_env(cls) -> "Ustawienia":
        """KAWOSZ_BAZA, KAWOSZ_DOSTAWY, KAWOSZ_RAPORTY, KAWOSZ_WYKRESY_PSI nadpisują ścieżki (np. kopia bazy do
        próby)."""
        domyslne = cls()
        return cls(
            baza=Path(os.environ.get("KAWOSZ_BAZA", domyslne.baza)),
            dostawy=Path(os.environ.get("KAWOSZ_DOSTAWY", domyslne.dostawy)),
            raporty=Path(os.environ.get("KAWOSZ_RAPORTY", domyslne.raporty)),
            wykresy_psi=Path(os.environ.get("KAWOSZ_WYKRESY_PSI", domyslne.wykresy_psi)),
        )


def schemat_wsadu(dzien: date) -> str:
    return f"wsad_{dzien:%Y%m%d}"


def id_wsadu(zrodlo: str, dzien: date) -> str:
    return f"{zrodlo}/{dzien}"


def sciezka_raportu(ust: Ustawienia, zrodlo: str, dzien: date) -> Path:
    return ust.raporty / f"{zrodlo}_{dzien}.md"


def _wzgledna(sciezka: Path) -> str:
    """Ścieżka względem katalogu repozytorium (np. docs/kwarantanna/pos_2026-09-30.md), poza nim pełna."""
    return str(sciezka.relative_to(PROJECT_ROOT)) if sciezka.is_relative_to(PROJECT_ROOT) else str(sciezka)


def _tabele_wsadu(con: duckdb.DuckDBPyConnection, dzien: date, zrodla: list[str]) -> list[Tabela]:
    """Tabele źródeł, które są w schemacie roboczym (migawki tylko, jeśli przyszły w dostawie)."""
    obecne = {
        nazwa
        for (nazwa,) in con.execute(
            "SELECT table_name FROM duckdb_tables() WHERE schema_name = ?", [schemat_wsadu(dzien)]
        ).fetchall()
    }
    return [t for z in zrodla for t in TABELE[z] if t.nazwa in obecne]


def _przygotuj_rejestry(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS kwarantanna (
            wsad VARCHAR, zrodlo VARCHAR, dzien DATE, tabela VARCHAR, wiersz JSON, reguly VARCHAR[], raport VARCHAR);
        CREATE TABLE IF NOT EXISTS wsady (
            wsad VARCHAR, zrodlo VARCHAR, dzien DATE, status VARCHAR, wiersze BIGINT, reguly VARCHAR[],
            raport VARCHAR, zapisano TIMESTAMP);
        -- wycena wsadu (dodana później, więc też dla tabeli założonej przez starszą wersję potoku)
        ALTER TABLE wsady ADD COLUMN IF NOT EXISTS przychod_netto DECIMAL(14,2);
        ALTER TABLE wsady ADD COLUMN IF NOT EXISTS zawyzenie DECIMAL(14,2);
        ALTER TABLE wsady ADD COLUMN IF NOT EXISTS wycena_uwaga VARCHAR;
        CREATE TABLE IF NOT EXISTS naruszenia (
            wsad VARCHAR, zrodlo VARCHAR, dzien DATE, regula VARCHAR, poziom VARCHAR, sprawdzone BIGINT,
            bledne BIGINT, blad VARCHAR);
        """
    )


def _zapisz_status(
    con, zrodlo: str, dzien: date, status: str, wiersze: int, sprawdzenie: dict, wycena: dict, raport_md
) -> None:
    """Status, wycena i wynik każdej reguły wsadu w miejsce poprzedniego zapisu tego wsadu."""
    wsad = id_wsadu(zrodlo, dzien)
    con.execute("DELETE FROM wsady WHERE wsad = ?", [wsad])
    con.execute(
        """INSERT INTO wsady BY NAME SELECT ? AS wsad, ? AS zrodlo, ? AS dzien, ? AS status, ? AS wiersze,
               ? AS reguly, ? AS raport, now()::TIMESTAMP AS zapisano, ? AS przychod_netto, ? AS zawyzenie,
               ? AS wycena_uwaga""",
        [
            wsad, zrodlo, dzien, status, wiersze, sprawdzenie["blokujace"], raport_md,
            wycena.get("przychod_netto"), wycena.get("zawyzenie"), wycena.get("uwaga"),
        ],
    )
    con.execute("DELETE FROM naruszenia WHERE wsad = ?", [wsad])
    if sprawdzenie["reguly"]:
        con.executemany(
            "INSERT INTO naruszenia VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                [wsad, zrodlo, dzien, r["id"], r["poziom"], r["sprawdzone"], r["bledne"], r["blad"]]
                for r in sprawdzenie["reguly"]
            ],
        )


# --- 1. Wczytanie ---


def wczytaj(ust: Ustawienia, zrodlo: str, dzien: date) -> dict[str, int]:
    """Pliki wsadu → tabele w schemacie roboczym. Zwraca liczbę wierszy na tabelę.

    Tabela faktów bez pliku w dostawie dostaje pusty wsad (z kolumnami opublikowanej tabeli): brak danych z dnia
    łapią reguły świeżości i kompletności (np. POS-10).
    """
    katalog = ust.dostawy / str(dzien) / zrodlo
    schemat = schemat_wsadu(dzien)
    con = connect(read_only=False, db_path=ust.baza)
    try:
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {schemat}")
        for t in TABELE[zrodlo]:
            con.execute(f"DROP TABLE IF EXISTS {schemat}.{t.nazwa}")
        if zrodlo == "pos":
            _wczytaj_pliki_z_kas(con, katalog, schemat)
        for t in TABELE[zrodlo]:
            if t.nazwa in ("pos_paragony", "pos_pliki"):
                continue
            plik = katalog / f"{t.nazwa}.parquet"
            if plik.exists():
                con.execute(f"CREATE TABLE {schemat}.{t.nazwa} AS SELECT * FROM read_parquet(?)", [str(plik)])
            elif not t.migawka:
                con.execute(f"CREATE TABLE {schemat}.{t.nazwa} AS SELECT * FROM main.{t.nazwa} LIMIT 0")
        return {
            t.nazwa: con.execute(f"SELECT count(*) FROM {schemat}.{t.nazwa}").fetchone()[0]
            for t in _tabele_wsadu(con, dzien, [zrodlo])
        }
    finally:
        con.close()


def _wczytaj_pliki_z_kas(con: duckdb.DuckDBPyConnection, katalog: Path, schemat: str) -> None:
    rejestr = load_raw.rejestr_plikow(katalog, z_czasem_dostawy=True) if katalog.is_dir() else []
    load_raw.zapisz_rejestr(con, f"{schemat}.pos_pliki", rejestr)
    if rejestr:
        load_raw.wczytaj_paragony(con, str(katalog / "*.csv"), f"{schemat}.pos_paragony", rejestr)
    else:
        con.execute(f"CREATE TABLE {schemat}.pos_paragony AS SELECT * FROM main.pos_paragony LIMIT 0")


# --- 2. Reguły jakości ---


def _kandydat(con: duckdb.DuckDBPyConnection, dzien: date, tylko_zrodlo: str | None = None) -> None:
    """Widoki tymczasowe o nazwach opublikowanych tabel: opublikowane wiersze z podmienionymi wierszami wsadu.

    Czyli to, co byłoby opublikowane po publikacji całej dostawy z tej nocy. Reguły czytają tabele bez schematu,
    więc trafiają na widoki. Do tabel sięgamy przez nazwę bazy, bo `main` wskazałby z powrotem na widok.

    `tylko_zrodlo`: tabele z dokumentami przychodu mają tylko wiersze wsadu tego źródła (pozostałe są puste),
    a słowniki i kursy jak u kandydata. Na takich widokach definicja przychodu liczy przychód samego wsadu.
    """
    baza, schemat = con.execute("SELECT current_database()").fetchone()[0], schemat_wsadu(dzien)
    w_wsadzie = {t.nazwa for t in _tabele_wsadu(con, dzien, ZRODLA)}
    for zrodlo, tabele in TABELE.items():
        for t in tabele:
            wsad, opublikowana = f'"{baza}".{schemat}.{t.nazwa}', f'"{baza}".main.{t.nazwa}'
            if tylko_zrodlo and t.przychod:
                wiersze_wsadu = zrodlo == tylko_zrodlo and t.nazwa in w_wsadzie
                sql = f"SELECT * FROM {wsad}" if wiersze_wsadu else f"SELECT * FROM {opublikowana} LIMIT 0"
            elif t.nazwa not in w_wsadzie:
                continue
            elif t.migawka:
                sql = f"SELECT * FROM {wsad}"
            else:
                klucz = ", ".join(t.klucz)
                sql = (
                    f"SELECT * FROM {opublikowana} ANTI JOIN {wsad} USING ({klucz})"
                    f" UNION ALL BY NAME SELECT * FROM {wsad}"
                )
            con.execute(f"CREATE OR REPLACE TEMP VIEW {t.nazwa} AS {sql}")


def widok_wsadu(con: duckdb.DuckDBPyConnection, zrodlo: str, dzien: date) -> None:
    """Widoki, w których z dokumentów przychodu jest tylko wsad `zrodlo` z dnia D (do wyceny wsadu)."""
    _kandydat(con, dzien, tylko_zrodlo=zrodlo)


def sprawdz(ust: Ustawienia, zrodlo: str, dzien: date) -> dict:
    """Reguły źródła dla dnia D na kandydacie. Przy błędzie blokującym zapisuje raport w docs/kwarantanna/."""
    con = connect(read_only=True, db_path=ust.baza)
    try:
        _kandydat(con, dzien)
        wyniki = [r.sprawdz(con, dzien, dzien) for r in REGULY[zrodlo]]
    finally:
        con.close()

    blokujace = [w.regula.id for w in wyniki if w.blokuje]
    ostrzegajace = [w.regula.id for w in wyniki if not w.ok and not w.blokuje]
    sciezka = None
    if blokujace:
        sciezka = sciezka_raportu(ust, zrodlo, dzien)
        sciezka.parent.mkdir(parents=True, exist_ok=True)
        tresc = raport.markdown(
            wyniki,
            dzien,
            dzien,
            POLECENIE.format(zrodlo=zrodlo, dzien=dzien),
            tytul=f"Kwarantanna: wsad {zrodlo} z {dzien}",
        )
        sciezka.write_text(tresc.replace("](reguly.md)", "](../reguly.md)"))
    return {
        "zrodlo": zrodlo,
        "dzien": str(dzien),
        "blokujace": blokujace,
        "ostrzegajace": ostrzegajace,
        "raport": _wzgledna(sciezka) if sciezka else None,
        "reguly": [
            {"id": w.regula.id, "poziom": str(w.regula.poziom), "sprawdzone": w.wiersze, "bledne": w.bledne,
             "blad": w.blad}
            for w in wyniki
        ],
    }


# --- 3. Kwarantanna albo publikacja ---


def odloz(ust: Ustawienia, zrodlo: str, dzien: date, sprawdzenie: dict, wycena: dict) -> dict[str, int]:
    """Wiersze wsadu → kwarantanna (jako JSON, jeden wiersz tabeli na wiersz), w miejsce poprzedniego zapisu wsadu.

    Opublikowane tabele zostają bez zmian, więc raporty nie widzą tego wsadu (i ewentualnie mają poprzednią,
    dobrą wersję tego dnia).
    """
    wsad, schemat, blokujace = id_wsadu(zrodlo, dzien), schemat_wsadu(dzien), sprawdzenie["blokujace"]
    raport_md = _wzgledna(sciezka_raportu(ust, zrodlo, dzien))
    con = connect(read_only=False, db_path=ust.baza)
    try:
        _przygotuj_rejestry(con)
        tabele = _tabele_wsadu(con, dzien, [zrodlo])
        con.execute("BEGIN")
        con.execute("DELETE FROM kwarantanna WHERE wsad = ?", [wsad])
        for t in tabele:
            con.execute(
                f"INSERT INTO kwarantanna SELECT ?, ?, ?, ?, to_json(w), ?, ? FROM {schemat}.{t.nazwa} w",
                [wsad, zrodlo, dzien, t.nazwa, blokujace, raport_md],
            )
        wiersze = dict(
            con.execute("SELECT tabela, count(*) FROM kwarantanna WHERE wsad = ? GROUP BY 1", [wsad]).fetchall()
        )
        _zapisz_status(con, zrodlo, dzien, "kwarantanna", sum(wiersze.values()), sprawdzenie, wycena, raport_md)
        con.execute("COMMIT")
        return {t.nazwa: wiersze.get(t.nazwa, 0) for t in tabele}
    finally:
        con.close()


def opublikuj(ust: Ustawienia, zrodlo: str, dzien: date, sprawdzenie: dict, wycena: dict) -> dict[str, int]:
    """Wiersze wsadu → opublikowane tabele, w jednej transakcji: najpierw usuwa wiersze o tych samych kluczach
    (migawka: całą tabelę), potem wstawia wsad. Zdejmuje wsad z kwarantanny, jeśli wcześniej tam trafił."""
    wsad, schemat = id_wsadu(zrodlo, dzien), schemat_wsadu(dzien)
    con = connect(read_only=False, db_path=ust.baza)
    try:
        _przygotuj_rejestry(con)
        tabele = _tabele_wsadu(con, dzien, [zrodlo])
        con.execute("BEGIN")
        wiersze = {}
        for t in tabele:
            _sprawdz_kolumny(con, schemat, t.nazwa)
            if t.migawka:
                con.execute(f"DELETE FROM main.{t.nazwa}")
            else:
                warunek = " AND ".join(f"w.{k} IS NOT DISTINCT FROM main.{t.nazwa}.{k}" for k in t.klucz)
                con.execute(
                    f"DELETE FROM main.{t.nazwa} WHERE EXISTS (SELECT 1 FROM {schemat}.{t.nazwa} w WHERE {warunek})"
                )
            con.execute(f"INSERT INTO main.{t.nazwa} BY NAME SELECT * FROM {schemat}.{t.nazwa}")
            wiersze[t.nazwa] = con.execute(f"SELECT count(*) FROM {schemat}.{t.nazwa}").fetchone()[0]
        con.execute("DELETE FROM kwarantanna WHERE wsad = ?", [wsad])
        _zapisz_status(con, zrodlo, dzien, "opublikowany", sum(wiersze.values()), sprawdzenie, wycena, None)
        con.execute("COMMIT")
    finally:
        con.close()
    # raport z wcześniejszej, złej dostawy tego dnia już nie obowiązuje
    sciezka_raportu(ust, zrodlo, dzien).unlink(missing_ok=True)
    return wiersze


def _sprawdz_kolumny(con: duckdb.DuckDBPyConnection, schemat: str, tabela: str) -> None:
    """Kolumna, której nie ma w opublikowanej tabeli, to zmiana źródła poza kontraktem: nie dopisujemy jej cicho."""
    kolumny = "SELECT column_name FROM duckdb_columns() WHERE schema_name = ? AND table_name = ?"
    nowe = {k for (k,) in con.execute(kolumny, [schemat, tabela]).fetchall()} - {
        k for (k,) in con.execute(kolumny, ["main", tabela]).fetchall()
    }
    if nowe:
        raise ValueError(f"{tabela}: kolumny spoza opublikowanej tabeli {sorted(nowe)}, wsadu nie publikujemy")


# --- 4. Sprzątanie ---


def sprzataj(ust: Ustawienia, dzien: date) -> None:
    con = connect(read_only=False, db_path=ust.baza)
    try:
        con.execute(f"DROP SCHEMA IF EXISTS {schemat_wsadu(dzien)} CASCADE")
    finally:
        con.close()
