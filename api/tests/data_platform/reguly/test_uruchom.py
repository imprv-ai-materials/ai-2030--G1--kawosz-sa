"""Runner i raport: wszystkie naruszenia naraz, błąd jednej reguły nie przerywa reszty, kod wyjścia i raport."""

import sys
from datetime import date

import duckdb
import pytest

from api.data_platform.reguly import ecom, erp, pos, raport, uruchom
from api.data_platform.reguly.regula import Poziom

WSZYSTKIE = pos.REGULY + erp.REGULY + ecom.REGULY
# sześć kolejnych paragonów bez metody płatności (z pozycjami, więc łamią tylko POS-07)
SZESC_BEZ_METODY = """
    INSERT INTO pos_paragony (lokal, nr_paragonu, data_czas, kanal, kwota_brutto, metoda_platnosci, storno, plik)
    SELECT 1, 2609300002 + i, TIMESTAMP '2026-09-30 09:00:00' + INTERVAL (i) MINUTE, 'sala', 14.00, NULL, 0,
           'pos_paragony_1_2026-09-30.csv'
    FROM range(1, 7) t(i);
    INSERT INTO pos_pozycje SELECT 1, 2609300002 + i, 'P0101', 1, 14.0, 8 FROM range(1, 7) t(i);
"""


def test_regula_zbiera_wszystkie_naruszenia_naraz(baza, sprawdz):
    """Zła cena i stawka na jednej pozycji, zerowa ilość na drugiej — reguła raportuje wszystko, nie pierwszy błąd."""
    baza.execute("""UPDATE pos_pozycje SET cena_brutto = 15.0, vat = 23 WHERE nr_paragonu = 2609300001;
           UPDATE pos_pozycje SET ilosc = 0 WHERE nr_paragonu = 2609300002""")
    wynik = sprawdz(pos.POS_06)
    assert set(wynik.naruszenia) == {"cena = cena z cennika", "stawka VAT = stawka z cennika", "ilosc: not_equal_to(0)"}
    assert wynik.bledne == 2


def test_wszystkie_reguly_dzialaja_mimo_wielu_naruszen(baza, sprawdz):
    """Jednocześnie zepsute POS, ERP i e-commerce: każda z tych reguł zgłasza swoje naruszenie."""
    baza.execute("""UPDATE pos_paragony SET metoda_platnosci = NULL WHERE nr_paragonu = 2609300001;
           UPDATE erp_kartoteka SET kategoria = NULL WHERE indeks = '80.01.0001';
           UPDATE ecom_zamowienia SET email = NULL WHERE id = 1000001""")
    naruszone = {r.id for r in WSZYSTKIE if not sprawdz(r).ok}
    assert naruszone == {"POS-07", "ERP-06", "ECOM-06"}


def test_blad_jednej_reguly_nie_przerywa_pozostalych(baza, sprawdz):
    baza.execute("DROP TABLE lokale")
    wyniki = {r.id: sprawdz(r) for r in pos.REGULY}
    assert {i for i, w in wyniki.items() if w.blad} == {"POS-05", "POS-10"}
    assert all(w.ok for i, w in wyniki.items() if i not in {"POS-05", "POS-10"})
    assert wyniki["POS-10"].blokuje  # reguły blokującej, której nie da się sprawdzić, nie uznajemy za spełnioną


def test_przyklady_po_jednym_z_kazdego_rodzaju_naruszenia(baza, sprawdz):
    baza.execute(SZESC_BEZ_METODY + "UPDATE pos_paragony SET metoda_platnosci = 'czek' WHERE nr_paragonu = 2609300001;")
    wynik = sprawdz(pos.POS_07)
    assert wynik.bledne == 7
    przyklady = wynik.przyklady(5)
    assert len(przyklady) == 5
    assert set(przyklady["naruszenie"]) == {
        "metoda_platnosci: brak wartości",
        f"metoda_platnosci: isin({pos.METODY_PLATNOSCI})",
    }


def test_raport_markdown(baza, sprawdz):
    baza.execute(SZESC_BEZ_METODY + "UPDATE pos_paragony SET kwota_brutto = 15.00 WHERE nr_paragonu = 2609300001;")
    tekst = raport.markdown([sprawdz(r) for r in WSZYSTKIE], date(2026, 9, 1), date(2026, 9, 30), "…")

    assert "**Wsad zablokowany: tak.** Reguły blokujące z naruszeniami: POS-04." in tekst
    assert "| POS-04 | **tak** | Zespół danych | 1 |" in tekst
    assert "| POS-07 | nie (ostrzega) | Operacje lokali (POS) | 6 |" in tekst
    sekcja_pos_07 = tekst.split("### POS-07")[1].split("###")[0]
    assert "Przykłady (5 z 6):" in sekcja_pos_07
    assert sekcja_pos_07.count("| metoda_platnosci: brak wartości |") == 5


@pytest.mark.parametrize(
    "psucie, kod, podsumowanie",
    [
        ("SELECT 1", 0, "**Wsad zablokowany: nie.**"),
        (
            "UPDATE pos_paragony SET kwota_brutto = 15.00 WHERE nr_paragonu = 2609300001",
            1,
            "**Wsad zablokowany: tak.** Reguły blokujące z naruszeniami: POS-04.",
        ),
    ],
    ids=["czyste dane", "regula blokujaca"],
)
def test_runner_kod_wyjscia_i_raport(plik_bazy, tmp_path, monkeypatch, psucie, kod, podsumowanie):
    con = duckdb.connect(str(plik_bazy))
    con.execute(psucie)
    con.close()
    plik_raportu = tmp_path / "naruszenia.md"
    argv = ["uruchom", "--dzien", "2026-09-30", "--baza", str(plik_bazy), "--raport", str(plik_raportu)]
    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(SystemExit) as wyjscie:
        uruchom.main()

    assert wyjscie.value.code == kod
    tekst = plik_raportu.read_text()
    assert podsumowanie in tekst
    assert str(plik_bazy) not in tekst  # ścieżka do bazy nie trafia do raportu


def test_poziomy_regul():
    """Każda reguła ma poziom, właściciela, jednostkę i unikalny identyfikator."""
    assert len({r.id for r in WSZYSTKIE}) == len(WSZYSTKIE) == 39
    assert {r.poziom for r in WSZYSTKIE} == set(Poziom)
    assert all(r.wlasciciel and r.jednostka for r in WSZYSTKIE)
