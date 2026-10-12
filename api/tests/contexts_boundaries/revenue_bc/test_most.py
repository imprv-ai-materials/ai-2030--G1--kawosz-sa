"""Most uzgodnieniowy na przypadkach z conftest.py: suma BI, zmiana po każdej regule, przychód netto i reszta."""

import sys
from datetime import date

import duckdb
import pytest

from api.contexts_boundaries.revenue_bc.most import most as m
from api.contexts_boundaries.revenue_bc.przychod.definicja import KROKI

WRZESIEN = date(2026, 9, 1)
POS_NETTO = 14 / 1.08 + 169 / 1.23


def _sumy_po_krokach() -> list[float]:
    """Suma po każdym kroku, policzona ręcznie (reguły włączane po kolei na liniach BI, z duplikatem paragonu)."""
    s = [2649.00]  # 366 + 645 + 438 + 300 + 900
    s.append(s[-1] - 366 + 2 * POS_NETTO)  # 1. POS netto (dwa razy, bo BI ma zdublowany plik)
    s.append(s[-1] - 1383 + 1383 / 1.23)  # 2. zamówienia 645 + subskrypcje 438 + karty 300 przez 1,23
    s.append(s[-1] - 61.50 / 1.23)  # 3. zwrot
    s.append(s[-1])  # 4. mapa kontrahentów
    s.append(s[-1] - 399 / 1.23 + 2 * 399 / 1.23 / 12)  # 5. plan roczny: zamiast 399 dwie dwunaste
    s.append(s[-1] - 300 / 1.23 + 250 / 1.23)  # 6. karty: realizacje 200 + 50 zamiast sprzedaży 300
    s.append(s[-1] + 30 / 1.23 * (4.2208 - 1))  # 7. EUR: 20 + 10 EUR kursem z 4.09 zamiast 1:1
    s.append(s[-1] - 369 / 1.23)  # 8. testowe 123 + 246
    s.append(  # 9. czas polski: +123 (31.08), −61,50 (1.10), kurs z 7.09 dla 10 EUR, +39 (31.08), +1/12 planu
        s[-1] + 123 / 1.23 - 61.50 / 1.23 + 10 / 1.23 * (4.2039 - 4.2208) + 39 / 1.23 + 399 / 1.23 / 12
    )
    return s


def test_most_krok_po_kroku(baza):
    tabela = m.most(baza, WRZESIEN)
    sumy = _sumy_po_krokach()

    assert list(tabela.columns) == ["krok", "opis", "kwota_pln", "suma_po_kroku"]
    kroki = ["0. Surowa suma BI", *(k.kod for k in KROKI), "Przychód netto", "Niewyjaśniona reszta"]
    assert list(tabela["krok"]) == kroki
    assert list(tabela["suma_po_kroku"][:10]) == pytest.approx([round(s, 2) for s in sumy], abs=0.005)
    netto, reszta = tabela.iloc[-2], tabela.iloc[-1]
    assert netto["kwota_pln"] == pytest.approx(sumy[-1] - POS_NETTO, abs=0.005)
    # reszta: zdublowany plik POS, którego żadna reguła nie usuwa (± 1 gr z zaokrągleń sum)
    assert reszta["kwota_pln"] == pytest.approx(-POS_NETTO, abs=0.011)
    assert "−8,84% przychodu netto" in reszta["opis"]


def test_most_sumuje_sie_co_do_grosza(baza):
    tabela = m.most(baza, WRZESIEN)
    kroki, netto = tabela.iloc[:10], tabela.iloc[-2]["kwota_pln"]
    assert round(kroki["kwota_pln"].sum() + tabela.iloc[-1]["kwota_pln"], 2) == netto
    assert (kroki["suma_po_kroku"].diff().round(2).iloc[1:] == kroki["kwota_pln"].iloc[1:]).all()


def test_surowa_suma_bi_jak_w_trzy_przychody(baza):
    assert m.surowa_suma_bi(baza, WRZESIEN) == pytest.approx(2649.00)


def test_zapis_kolejnych_miesiecy(baza):
    m.zapisz(baza, WRZESIEN, m.most(baza, WRZESIEN))
    m.zapisz(baza, date(2026, 8, 1), m.most(baza, date(2026, 8, 1)))
    m.zapisz(baza, WRZESIEN, m.most(baza, WRZESIEN))  # ponowne uruchomienie zastępuje miesiąc, nie dopisuje

    assert baza.sql(f"SELECT miesiac, count(*) FROM {m.TABELA} GROUP BY 1 ORDER BY 1").fetchall() == [
        (date(2026, 8, 1), 12),
        (date(2026, 9, 1), 12),
    ]
    assert [c[0] for c in baza.sql(f"DESCRIBE {m.TABELA}").fetchall()] == [
        "miesiac",
        "krok",
        "opis",
        "kwota_pln",
        "suma_po_kroku",
    ]


def test_uruchomienie_z_linii_polecen(plik_bazy, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["most", "2026-09", "2026-08", "--baza", str(plik_bazy)])
    m.main()

    assert "| **0. Surowa suma BI** |" in capsys.readouterr().out
    con = duckdb.connect(str(plik_bazy), read_only=True)
    assert con.sql(f"SELECT count(DISTINCT miesiac) FROM {m.TABELA}").fetchone()[0] == 2
    con.close()
