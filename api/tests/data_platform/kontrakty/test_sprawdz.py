"""Sprawdzenie kontraktu co miesiąc: komunikat mówi, który kontrakt, która kolumna, od którego dnia i co zrobić."""

import sys
from datetime import date

import duckdb
import pytest

from api.data_platform.kontrakty import sprawdz
from api.data_platform.kontrakty.kontrakt import wczytaj

KONTRAKT = wczytaj("pos_paragony")
DZIEN = date(2026, 9, 30)
NAGLOWEK = KONTRAKT.wymagane
Z_KANALEM = NAGLOWEK[:3] + ["kanal"] + NAGLOWEK[3:]  # układ plików z kas od 1.06.2026


def _jedyny(miesiac, regula):
    [komunikat] = [k for k in miesiac.komunikaty if k.regula.id == regula]
    return komunikat


def test_czyste_dane_sa_zgodne_z_kontraktem(baza):
    [miesiac] = sprawdz.sprawdz(baza, KONTRAKT, DZIEN, DZIEN)
    assert miesiac.wynik == "zgodny" and not miesiac.komunikaty


def test_nowa_kolumna_lamie_kontrakt_i_komunikat_mowi_co_zrobic(baza):
    baza.execute(f"UPDATE pos_pliki SET kolumny = {Z_KANALEM}")
    [miesiac] = sprawdz.sprawdz(baza, KONTRAKT, DZIEN, DZIEN)

    assert miesiac.zlamany and miesiac.wynik == "kontrakt złamany"
    komunikat = _jedyny(miesiac, "POS-12")
    assert (komunikat.kolumny, komunikat.od, komunikat.pliki, komunikat.lokale) == (["kanal"], DZIEN, 1, (1,))
    assert komunikat.naruszenie == "kolumna spoza kontraktu (w pliku po kolumnie `data_czas`)"
    tekst = komunikat.tekst()
    assert "**POS-12 · blokuje · kolumna `kanal`**" in tekst
    assert "Złamany kontrakt „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0)" in tekst
    assert "- Od dnia: **2026-09-30**" in tekst
    assert f"- Co zrobić: {KONTRAKT.reguly['POS-12'].co_zrobic}" in tekst
    assert "- Odpowiada: Operacje lokali (POS)" in tekst


def test_od_dnia_to_pierwszy_dzien_w_sprawdzanym_okresie(baza):
    """Złamanie z sierpnia trwa we wrześniu: wrześniowy komunikat podaje dzień, od którego trwa."""
    baza.execute(f"""UPDATE pos_pliki SET kolumny = {Z_KANALEM};
        INSERT INTO pos_pliki VALUES ('pos_paragony_1_2026-08-31.csv', 1, DATE '2026-08-31', {Z_KANALEM}, 0, NULL)""")
    sierpien, wrzesien = sprawdz.sprawdz(baza, KONTRAKT, date(2026, 8, 31), DZIEN)

    assert (sierpien.od, wrzesien.od) == (date(2026, 8, 31), date(2026, 9, 1))
    komunikat = _jedyny(wrzesien, "POS-12")
    assert (komunikat.pierwszy_dzien, komunikat.od) == (date(2026, 8, 31), DZIEN)
    od_dnia = "- Od dnia: **2026-08-31** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-09-30"
    assert od_dnia in komunikat.tekst()


@pytest.mark.parametrize(
    "psucie, regula, kolumny, naruszenie",
    [
        (
            "UPDATE pos_paragony SET storno = 2 WHERE nr_paragonu = 2609300001",
            "POS-01",
            ["storno"],
            "wartość spoza listy [0, 1]",
        ),
        (
            "UPDATE pos_paragony SET metoda_platnosci = NULL WHERE nr_paragonu = 2609300001",
            "POS-07",
            ["metoda_platnosci"],
            "brak wartości",
        ),
        (
            f"UPDATE pos_pliki SET kolumny = {[k for k in NAGLOWEK if k != 'storno']}",
            "POS-12",
            ["storno"],
            "brak kolumny z kontraktu",
        ),
        (
            "UPDATE pos_paragony SET plik = 'pos_paragony_1_2026-09-30 (1).csv' WHERE nr_paragonu = 2609300002",
            "POS-03",
            ["plik"],
            "plik = pos_paragony_{lokal}_{dzień}.csv",
        ),
    ],
    ids=["slownik", "brak wartosci", "brak kolumny w pliku", "nazwa pliku"],
)
def test_komunikat_wskazuje_kolumne_prostym_jezykiem(baza, psucie, regula, kolumny, naruszenie):
    baza.execute(psucie)
    [miesiac] = sprawdz.sprawdz(baza, KONTRAKT, DZIEN, DZIEN)
    komunikat = _jedyny(miesiac, regula)
    assert (komunikat.kolumny, komunikat.naruszenie) == (kolumny, naruszenie)


def test_regula_ktorej_nie_da_sie_sprawdzic_lamie_kontrakt(baza):
    baza.execute("DROP TABLE pos_pliki")
    [miesiac] = sprawdz.sprawdz(baza, KONTRAKT, DZIEN, DZIEN)
    assert miesiac.zlamany
    assert _jedyny(miesiac, "POS-12").naruszenie.startswith("reguły nie udało się wykonać")


def test_miesiace():
    assert sprawdz.miesiace(date(2026, 1, 15), date(2026, 3, 2)) == [
        (date(2026, 1, 15), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 28)),
        (date(2026, 3, 1), date(2026, 3, 2)),
    ]


def test_raport_markdown(baza):
    baza.execute(f"UPDATE pos_pliki SET kolumny = {Z_KANALEM}, czas_dostawy = NULL")
    tekst = sprawdz.markdown(KONTRAKT, sprawdz.sprawdz(baza, KONTRAKT, DZIEN, DZIEN), "…")

    assert "- **Kontrakt złamany w 1 z 1 miesięcy:** wrzesień 2026." in tekst
    assert "- **Pierwsze złamanie:** 2026-09-30, POS-12, kolumna `kanal`: kolumna spoza kontraktu" in tekst
    assert "| wrzesień 2026 | **kontrakt złamany** | POS-12 | — |" in tekst
    assert "| POS-12 | blokuje | plik × kolumna | **1** |" in tekst
    # plik bez czasu dostawy: POS-13 nie miał czego sprawdzić, a raport mówi dlaczego
    assert "| POS-13 | ostrzega | plik | — |" in tekst
    assert f"- **POS-13** ({KONTRAKT.opis_reguly('POS-13')})" in tekst and KONTRAKT.reguly["POS-13"].bez_danych in tekst


@pytest.mark.parametrize(
    "psucie, kod", [("SELECT 1", 0), (f"UPDATE pos_pliki SET kolumny = {Z_KANALEM}", 1)], ids=["zgodny", "zlamany"]
)
def test_kod_wyjscia_i_raport(plik_bazy, tmp_path, monkeypatch, psucie, kod):
    con = duckdb.connect(str(plik_bazy))
    con.execute(psucie)
    con.close()
    raport = tmp_path / "kontrakt.md"
    argv = ["sprawdz", "pos_paragony", "--od", "2026-09-30", "--do", "2026-09-30", "--baza", str(plik_bazy)]
    monkeypatch.setattr(sys, "argv", argv + ["--raport", str(raport)])

    with pytest.raises(SystemExit) as wyjscie:
        sprawdz.main()

    assert wyjscie.value.code == kod
    tekst = raport.read_text()
    assert "sprawdz pos_paragony --od 2026-09-30 --do 2026-09-30 --raport" in tekst
    assert str(plik_bazy) not in tekst
