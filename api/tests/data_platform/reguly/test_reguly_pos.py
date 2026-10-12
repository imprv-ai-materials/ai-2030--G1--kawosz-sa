"""Reguły POS: na czystych danych przechodzą, a każdy zepsuty przykład łapie właściwa reguła."""

import pytest

from api.data_platform.reguly import pos

NAGLOWEK = pos.KONTRAKT.wymagane  # nagłówek pliku z kasy zgodny z kontraktem

NOWY_PARAGON = (
    "INSERT INTO pos_paragony (lokal, nr_paragonu, data_czas, kanal, kwota_brutto, metoda_platnosci, storno, plik)"
)
PLIK = "'pos_paragony_1_2026-09-30.csv'"

# (reguła, SQL psujący czyste dane, oczekiwane naruszenie, ile rekordów ma oznaczyć reguła)
PRZYKLADY = [
    pytest.param(
        pos.POS_01,
        "UPDATE pos_paragony SET storno = 2 WHERE nr_paragonu = 2609300001",
        "storno: isin([0, 1])",
        1,
        id="POS-01 storno spoza slownika",
    ),
    pytest.param(
        pos.POS_02,
        # ten sam plik z kasy wczytany drugi raz, jak pos_paragony_17_2026-09-11 (1).csv
        "INSERT INTO pos_paragony SELECT * REPLACE ('pos_paragony_1_2026-09-30 (1).csv' AS plik) FROM pos_paragony",
        "powtórzony klucz (lokal, nr_paragonu)",
        2,
        id="POS-02 plik wczytany dwa razy",
    ),
    pytest.param(
        pos.POS_03,
        # paragon dopisany poza kolejnością: numer 0003, a godzina wcześniejsza niż 0001 i 0002
        f"""{NOWY_PARAGON} VALUES (1, 2609300003, TIMESTAMP '2026-09-30 07:30:00', 'sala', 14.00, 'karta', 0, {PLIK});
            INSERT INTO pos_pozycje VALUES (1, 2609300003, 'P0101', 1, 14.0, 8)""",
        "numer paragonu rośnie z czasem",
        1,
        id="POS-03 numer poza kolejnoscia",
    ),
    pytest.param(
        pos.POS_04,
        "UPDATE pos_paragony SET kwota_brutto = 15.00 WHERE nr_paragonu = 2609300001",
        "Σ kwota_brutto = Σ ilosc × cena_brutto",
        1,
        id="POS-04 naglowek inny niz suma pozycji",
    ),
    pytest.param(
        pos.POS_05,
        f"{NOWY_PARAGON} VALUES (1, 2609300003, TIMESTAMP '2026-09-30 10:00:00', 'sala', 14.00, 'karta', 0, {PLIK})",
        "paragon bez pozycji",
        1,
        id="POS-05 paragon bez pozycji",
    ),
    pytest.param(
        pos.POS_06,
        # 1 szt. „kawy na wagę” (cena wpisywana ręcznie) za 48 000 zł
        f"""{NOWY_PARAGON}
            VALUES (1, 2609300003, TIMESTAMP '2026-09-30 10:00:00', 'sala', 48000.00, 'karta', 0, {PLIK});
            INSERT INTO pos_pozycje VALUES (1, 2609300003, 'P0999', 1, 48000.0, 23)""",
        "cena ręczna w zakresie 0–500 zł",
        1,
        id="POS-06 cena reczna 48 000 zl",
    ),
    pytest.param(
        pos.POS_07,
        "UPDATE pos_paragony SET metoda_platnosci = NULL WHERE nr_paragonu = 2609300002",
        "metoda_platnosci: brak wartości",
        1,
        id="POS-07 paragon bez metody platnosci",
    ),
    pytest.param(
        pos.POS_08,
        # zakup ziarna i zwrot latte na jednym paragonie: suma dodatnia, pozycja ujemna, storno = 0
        f"""{NOWY_PARAGON} VALUES (1, 2609300003, TIMESTAMP '2026-09-30 10:00:00', 'sala', 155.00, 'karta', 0, {PLIK});
            INSERT INTO pos_pozycje VALUES
                (1, 2609300003, 'P0201', 1, 169.0, 23), (1, 2609300003, 'P0101', -1, 14.0, 8)""",
        "ujemna ilość lub kwota bez storno = 1",
        1,
        id="POS-08 ujemna ilosc na paragonie bez storno",
    ),
    pytest.param(
        pos.POS_08,
        f"""{NOWY_PARAGON} VALUES (1, 2609300003, TIMESTAMP '2026-09-30 10:00:00', 'sala', -14.00, 'karta', 0, {PLIK});
            INSERT INTO pos_pozycje VALUES (1, 2609300003, 'P0101', -1, 14.0, 8)""",
        "ujemna ilość lub kwota bez storno = 1",
        1,
        id="POS-08 ujemna kwota bez storno",
    ),
    pytest.param(
        pos.POS_09,
        # storno latte z paragonu 0001 — plik z kasy nie mówi, który paragon stornuje
        f"""{NOWY_PARAGON} VALUES (1, 2609300003, TIMESTAMP '2026-09-30 08:05:00', 'sala', -14.00, 'karta', 1, {PLIK});
            INSERT INTO pos_pozycje VALUES (1, 2609300003, 'P0101', -1, 14.0, 8)""",
        "brak kolumny nr_paragonu_stornowanego",
        1,
        id="POS-09 storno bez paragonu pierwotnego",
    ),
    pytest.param(
        pos.POS_10,
        "INSERT INTO lokale VALUES (2, 'Kawosz Gdańsk – ul. Długa 1', 'Gdańsk', 'ul. Długa 1', DATE '2026-01-01')",
        "lokal ma paragony z dnia (dni zamknięte: 1.01, Wielkanoc, 25.12)",
        1,
        id="POS-10 otwarty lokal bez pliku z dnia",
    ),
    pytest.param(
        pos.POS_11,
        # 28 poprzednich dni po 1 paragonie, a w dniu eksportu 2 (ok. 2 × — jak zdublowany plik)
        f"""{NOWY_PARAGON}
            SELECT 1, strftime(d, '%y%m%d')::BIGINT * 10000 + 1, d + INTERVAL 8 HOUR, 'sala', 14.00, 'karta', 0,
                   format('pos_paragony_1_{{}}.csv', strftime(d, '%Y-%m-%d'))
            FROM (SELECT DATE '2026-09-30' - i::INTEGER AS d FROM range(1, 29) t(i))""",
        "paragony = 0.4–1.8 × mediana z 28 dni",
        1,
        id="POS-11 dzien z podwojnym wolumenem",
    ),
    pytest.param(
        pos.POS_12,
        # jak od 1.06.2026: kasa wstawia `kanal` po `data_czas`; reszta kolumn kontraktu zostaje w kolejności
        f"UPDATE pos_pliki SET kolumny = {NAGLOWEK[:3] + ['kanal'] + NAGLOWEK[3:]}",
        "kolumna spoza kontraktu",
        1,
        id="POS-12 nowa kolumna w srodku pliku",
    ),
    pytest.param(
        pos.POS_12,
        f"UPDATE pos_pliki SET kolumny = {[k for k in NAGLOWEK if k != 'storno']}",
        "brak kolumny z kontraktu",
        1,
        id="POS-12 brak kolumny storno",
    ),
    pytest.param(
        pos.POS_12,
        f"UPDATE pos_pliki SET kolumny = {NAGLOWEK[:3] + [NAGLOWEK[4], NAGLOWEK[3]] + NAGLOWEK[5:]}",
        "kolumna w innej kolejności niż w kontrakcie",
        2,
        id="POS-12 zamienione kolumny kwoty i metody platnosci",
    ),
    pytest.param(
        pos.POS_13,
        "UPDATE pos_pliki SET czas_dostawy = TIMESTAMP '2026-10-01 07:30:00'",
        "plik dotarł w terminie (D+1 do 6:00)",
        1,
        id="POS-13 plik po 6:00 nastepnego dnia",
    ),
]


@pytest.mark.parametrize("regula", pos.REGULY, ids=lambda r: r.id)
def test_czyste_dane_przechodza(sprawdz, regula):
    wynik = sprawdz(regula)
    assert wynik.ok, wynik.naruszenia


@pytest.mark.parametrize("regula, psucie, naruszenie, rekordy", PRZYKLADY)
def test_regula_lapie_zly_przyklad(baza, sprawdz, regula, psucie, naruszenie, rekordy):
    baza.execute(psucie)
    wynik = sprawdz(regula)
    assert naruszenie in wynik.naruszenia, wynik.naruszenia
    assert wynik.bledne == rekordy


def test_kazda_regula_ma_zly_przyklad():
    assert {p.values[0].id for p in PRZYKLADY} == {r.id for r in pos.REGULY}


def test_storno_ze_wskazaniem_paragonu_przechodzi(baza, sprawdz):
    """Gdy kasa doda na końcu pliku numer stornowanego paragonu, POS-09 przechodzi, a POS-01 i POS-12 go przyjmują:
    kontrakt przewiduje tę kolumnę jako opcjonalną, więc nie trzeba nowej wersji."""
    baza.execute(f"""ALTER TABLE pos_paragony ADD COLUMN nr_paragonu_stornowanego BIGINT;
            UPDATE pos_pliki SET kolumny = {NAGLOWEK + ['nr_paragonu_stornowanego']};
            {NOWY_PARAGON.replace(", plik)", ", plik, nr_paragonu_stornowanego)")}
            VALUES (1, 2609300003, TIMESTAMP '2026-09-30 08:05:00', 'sala', -14.00, 'karta', 1, {PLIK}, 2609300001);
            INSERT INTO pos_pozycje VALUES (1, 2609300003, 'P0101', -1, 14.0, 8)""")
    for regula in [pos.POS_01, pos.POS_08, pos.POS_09, pos.POS_12]:
        wynik = sprawdz(regula)
        assert wynik.ok, (regula.id, wynik.naruszenia)


def test_kolumna_spoza_kontraktu_w_tabeli_nie_lamie_pos_01(baza, sprawdz):
    """Tabela pos_paragony ma `kanal` z plików od 1.06.2026 (łączenie po nazwach), także dla starszych dni (NULL).
    To nie błąd paragonu: który plik przysłał obcą kolumnę, sprawdza POS-12 na rejestrze plików."""
    baza.execute("UPDATE pos_paragony SET kanal = NULL")
    assert sprawdz(pos.POS_01).ok
    assert sprawdz(pos.POS_12).ok


def test_plik_bez_czasu_dostawy_nie_jest_sprawdzany(baza, sprawdz):
    """Archiwum ZIP nie ma czasu dostawy: POS-13 nie zgłasza błędu, ale też niczego nie sprawdza."""
    baza.execute("UPDATE pos_pliki SET czas_dostawy = NULL")
    wynik = sprawdz(pos.POS_13)
    assert wynik.ok and wynik.wiersze == 0
