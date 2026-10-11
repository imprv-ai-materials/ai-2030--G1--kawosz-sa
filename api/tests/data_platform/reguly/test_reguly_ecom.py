"""Reguły e-commerce: na czystych danych przechodzą, a każdy zepsuty przykład łapie właściwa reguła."""

import pytest

from api.data_platform.reguly import ecom

# (reguła, SQL psujący czyste dane, oczekiwane naruszenie, ile rekordów ma oznaczyć reguła)
PRZYKLADY = [
    pytest.param(
        ecom.ECOM_01,
        "UPDATE ecom_zamowienia SET waluta = 'USD' WHERE id = 1000002",
        "waluta: isin(['PLN', 'EUR'])",
        1,
        id="ECOM-01 waluta spoza slownika",
    ),
    pytest.param(
        ecom.ECOM_01,
        "UPDATE ecom_zamowienia SET metoda_platnosci = 'pobranie' WHERE id = 1000002",
        "pobranie tylko w PLN",
        1,
        id="ECOM-01 pobranie w EUR",
    ),
    pytest.param(
        ecom.ECOM_02,
        "UPDATE ecom_zamowienia SET brutto = 70.0 WHERE id = 1000001",
        "brutto = Σ ilosc × cena_brutto",
        1,
        id="ECOM-02 naglowek inny niz suma pozycji",
    ),
    pytest.param(
        ecom.ECOM_03,
        "INSERT INTO ecom_pozycje VALUES (1000001, 'KW-NIEZNANY-999', 1, 10.0)",
        "SKU spoza ecom_produkty (poza DOSTAWA)",
        1,
        id="ECOM-03 SKU spoza cennika",
    ),
    pytest.param(
        ecom.ECOM_04,
        "DELETE FROM kursy_nbp",
        "kurs z poprzedniego dnia roboczego, najwyżej 7 dni wstecz",
        1,
        id="ECOM-04 zamowienie w EUR bez kursu NBP",
    ),
    pytest.param(
        ecom.ECOM_04,
        # jest tylko kurs z dnia zamówienia, a księgowość przelicza kursem z dnia poprzedzającego
        "DELETE FROM kursy_nbp WHERE data = DATE '2026-09-29'",
        "eur_pln: brak wartości",
        1,
        id="ECOM-04 tylko kurs z dnia zamowienia",
    ),
    pytest.param(
        ecom.ECOM_05,
        "UPDATE ecom_zamowienia SET email = 'qa@kawosz.pl', notatka = 'zamówienie testowe QA' WHERE id = 1000001",
        "e-mail w domenie @kawosz.pl",
        1,
        id="ECOM-05 zamowienie testowe",
    ),
    pytest.param(
        ecom.ECOM_06,
        "UPDATE ecom_zamowienia SET email = NULL, metoda_platnosci = 'pobranie' WHERE id = 1000001",
        "email: brak wartości",
        1,
        id="ECOM-06 pobranie bez e-maila",
    ),
    pytest.param(
        ecom.ECOM_07,
        "UPDATE ecom_zamowienia SET zwrot = true WHERE id = 1000001",
        "brak kolumny data_zwrotu",
        1,
        id="ECOM-07 zwrot bez daty i kwoty",
    ),
    pytest.param(
        ecom.ECOM_08,
        "INSERT INTO ecom_produkty VALUES ('KW-ETIOPIA-009', 'Etiopia Yirgacheffe – kawa ziarnista 250 g', 40.40)",
        "sku_o_tej_nazwie: equal_to(1)",
        1,
        id="ECOM-08 dwa SKU o tej samej nazwie",
    ),
    pytest.param(
        ecom.ECOM_09,
        "UPDATE ecom_subskrypcje SET kwota = 399.0 WHERE id = 'SUB-000001'",
        "kwota = cena planu (39 / 399)",
        1,
        id="ECOM-09 plan miesieczny za 399 zl",
    ),
    pytest.param(
        ecom.ECOM_09,
        # 02:30 zapisane jako czas polski: w UTC nocny batch ma godziny 22–01
        "UPDATE ecom_subskrypcje SET data_platnosci = TIMESTAMP '2026-09-30 02:30:00' WHERE id = 'SUB-000001'",
        "godzina zapisu poza nocnym batchem w UTC (22–01)",
        1,
        id="ECOM-09 zapis w czasie polskim zamiast UTC",
    ),
    pytest.param(
        ecom.ECOM_10,
        "UPDATE karty_podarunkowe SET data_realizacji = DATE '2026-09-30'",
        "realizacje kart = płatności „karta podarunkowa” w POS i sklepie",
        1,
        id="ECOM-10 realizacja karty bez platnosci karta podarunkowa",
    ),
    pytest.param(
        ecom.ECOM_11,
        # bez zamówienia z 22:30 dzień kończy się o 10:00 czasu polskiego
        "DELETE FROM ecom_zamowienia WHERE id = 1000002",
        "ostatnie zamówienie przed 22:00 czasu polskiego",
        1,
        id="ECOM-11 dzien uciety przed 22:00",
    ),
    pytest.param(
        ecom.ECOM_12,
        # 28 poprzednich dni po 10 zamówień, a w dniu eksportu 2
        """INSERT INTO ecom_zamowienia
           SELECT 2000000 + i * 100 + n, (DATE '2026-09-30' - i::INTEGER) + INTERVAL 10 HOUR, 'PLN', 61.16,
                  'klient@example.com', NULL, false, 'BLIK'
           FROM range(1, 29) t(i), range(10) u(n)""",
        "zamówienia = 0.3–3.5 × mediana z 28 dni",
        1,
        id="ECOM-12 dzien z ulamkiem zwyklego ruchu",
    ),
]


@pytest.mark.parametrize("regula", ecom.REGULY, ids=lambda r: r.id)
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
    assert {p.values[0].id for p in PRZYKLADY} == {r.id for r in ecom.REGULY}


def test_zwrot_z_data_i_kwota_przechodzi(baza, sprawdz):
    """Gdy sklep doda datę i kwotę zwrotu, ECOM-07 przechodzi, a typy z ECOM-01 nadal się zgadzają."""
    baza.execute("""ALTER TABLE ecom_zamowienia ADD COLUMN data_zwrotu TIMESTAMP_NS;
           ALTER TABLE ecom_zamowienia ADD COLUMN kwota_zwrotu DOUBLE;
           UPDATE ecom_zamowienia
           SET zwrot = true, data_zwrotu = '2026-09-30 12:00:00'::TIMESTAMP_NS, kwota_zwrotu = 46.17
           WHERE id = 1000001""")
    for regula in [ecom.ECOM_01, ecom.ECOM_07]:
        wynik = sprawdz(regula)
        assert wynik.ok, (regula.id, wynik.naruszenia)
