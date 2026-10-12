"""Most uzgodnieniowy: od surowej sumy z dashboardu BI do przychodu netto według definicji, reguła po regule.

Pierwszy wiersz to suma, którą liczy dashboard BI: kwoty ze wszystkich źródeł tak, jak leżą w tabelach (natywne
daty, EUR jak PLN, bez poprawek; docs/trzy_przychody.md, sekcja 1). Potem włączamy po kolei reguły definicji
(przychod/definicja.py, KROKI) na tych samych liniach co BI i zapisujemy, o ile każda zmienia sumę. Na końcu jest
przychód netto według definicji (każdy dokument raz) i niewyjaśniona reszta, czyli różnica między nim a sumą po
ostatniej regule. Tej różnicy żadna reguła nie tłumaczy.

    PYTHONPATH=api poetry run python -m api.contexts_boundaries.revenue_bc.most.most 2026-09 2026-08

Każdy uruchomiony miesiąc trafia do tabeli most_przychodu w kawosz.duckdb. Poprzedni zapis tego miesiąca znika.
"""

import argparse
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from api.adapters.duckdb_conn import DB_PATH, connect
from api.contexts_boundaries.revenue_bc.przychod.definicja import KROKI, przychod_netto, suma

TABELA = "most_przychodu"
KOLUMNY = ["krok", "opis", "kwota_pln", "suma_po_kroku"]

# Dashboard BI (docs/trzy_przychody.md, 1.3): każde źródło po swojej natywnej kolumnie daty, bez żadnych poprawek.
SUMA_BI = """
    SELECT (SELECT coalesce(sum(kwota_brutto), 0) FROM pos_paragony WHERE data_czas >= $od AND data_czas < $do)
         + (SELECT coalesce(sum(brutto), 0) FROM ecom_zamowienia WHERE data_utc >= $od AND data_utc < $do)
         + (SELECT coalesce(sum(kwota), 0) FROM ecom_subskrypcje WHERE data_platnosci >= $od AND data_platnosci < $do)
         + (SELECT coalesce(sum(kwota), 0) FROM karty_podarunkowe WHERE data_sprzedazy >= $od AND data_sprzedazy < $do)
         + (SELECT coalesce(sum(kwota_netto), 0) FROM erp_faktury WHERE data >= $od AND data < $do)
"""
OPIS_BI = (
    "Surowa suma jak dashboard BI: POS, zamówienia i subskrypcje brutto, karty w dniu sprzedaży, ERP netto;"
    " natywne daty (e-commerce w UTC), EUR jak PLN, bez poprawek"
)
OPIS_NETTO = "Przychód netto według definicji (docs/przychod_netto.md): wszystkie reguły, każdy dokument raz"


def _miesiac(miesiac: date) -> dict[str, date]:
    od = miesiac.replace(day=1)
    return {"od": od, "do": (pd.Timestamp(od) + pd.DateOffset(months=1)).date()}


def surowa_suma_bi(con: duckdb.DuckDBPyConnection, miesiac: date) -> float:
    return float(con.sql(SUMA_BI, params=_miesiac(miesiac)).fetchone()[0])


def _procent(x: float) -> str:
    return f"{x:.2%}".replace(".", ",").replace("-", "−")


def most(con: duckdb.DuckDBPyConnection, miesiac: date) -> pd.DataFrame:
    """Most za miesiąc: krok, opis, kwota_pln (zmiana sumy), suma_po_kroku. Kwoty w zł, zaokrąglone do grosza."""
    bi = round(surowa_suma_bi(con, miesiac), 2)
    sumy = [
        round(suma(con, miesiac, KROKI[:k], bez_duplikatow=False)["kwota_pln"].sum(), 2) for k in range(len(KROKI) + 1)
    ]
    if abs(sumy[0] - bi) > 0.005:  # linie startowe definicji mają dawać dokładnie to, co liczy BI
        raise RuntimeError(f"Linie startowe dają {sumy[0]:.2f} zł, a suma BI {bi:.2f} zł za {miesiac:%Y-%m}")
    netto = round(przychod_netto(con, miesiac)["kwota_pln"].sum(), 2)
    reszta = round(netto - sumy[-1], 2)

    wiersze = [("0. Surowa suma BI", OPIS_BI, bi, bi)]
    # zmiana = różnica zaokrąglonych sum, żeby kolumny sumowały się co do grosza
    wiersze += [(k.kod, k.opis, round(sumy[i] - sumy[i - 1], 2), sumy[i]) for i, k in enumerate(KROKI, 1)]
    wiersze += [
        ("Przychód netto", OPIS_NETTO, netto, netto),
        (
            "Niewyjaśniona reszta",
            f"Przychód netto według definicji minus suma po ostatniej regule: {_procent(reszta / netto)}"
            " przychodu netto",
            reszta,
            netto,
        ),
    ]
    return pd.DataFrame(wiersze, columns=KOLUMNY)


def zapisz(con: duckdb.DuckDBPyConnection, miesiac: date, tabela: pd.DataFrame) -> None:
    """Zapisuje most miesiąca w most_przychodu (z kolumną miesiac) w miejsce poprzedniego zapisu tego miesiąca."""
    con.execute(
        f"""CREATE TABLE IF NOT EXISTS {TABELA} (
                miesiac DATE, krok VARCHAR, opis VARCHAR, kwota_pln DECIMAL(14,2), suma_po_kroku DECIMAL(14,2))"""
    )
    con.register("most_df", tabela.assign(miesiac=miesiac.replace(day=1)))
    try:
        con.execute("BEGIN")
        con.execute(f"DELETE FROM {TABELA} WHERE miesiac = ?", [miesiac.replace(day=1)])
        con.execute(f"INSERT INTO {TABELA} SELECT miesiac, {', '.join(KOLUMNY)} FROM most_df")
        con.execute("COMMIT")
    finally:
        con.unregister("most_df")


def _zl(x: float) -> str:
    return f"{x:,.2f}".replace(",", " ").replace(".", ",").replace("-", "−")


def markdown(tabela: pd.DataFrame) -> str:
    linie = ["| Krok | Opis | Kwota [zł] | Suma po kroku [zł] |", "|---|---|---:|---:|"]
    for w in tabela.itertuples(index=False):
        krok, suma_po = w.krok, _zl(w.suma_po_kroku)
        if krok in ("0. Surowa suma BI", "Przychód netto"):
            krok, suma_po = f"**{krok}**", f"**{suma_po}**"
        linie.append(f"| {krok} | {w.opis} | {_zl(w.kwota_pln)} | {suma_po} |")
    return "\n".join(linie)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("miesiace", nargs="+", type=lambda m: date.fromisoformat(f"{m}-01"), help="RRRR-MM")
    parser.add_argument("--baza", type=Path, default=DB_PATH, help="plik DuckDB (domyślnie kawosz.duckdb)")
    args = parser.parse_args()

    con = connect(read_only=False, db_path=args.baza)
    try:
        for miesiac in args.miesiace:
            tabela = most(con, miesiac)
            zapisz(con, miesiac, tabela)
            print(f"\n## Most przychodu: {miesiac:%Y-%m}\n\n{markdown(tabela)}")
    finally:
        con.close()
    print(f"\nZapisano w {args.baza.name}, tabela {TABELA}.")


if __name__ == "__main__":
    main()
