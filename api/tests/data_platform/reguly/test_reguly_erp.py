"""Reguły ERP: na czystych danych przechodzą, a każdy zepsuty przykład łapie właściwa reguła."""

import pytest

from api.data_platform.reguly import erp

# (reguła, SQL psujący czyste dane, oczekiwane naruszenie, ile rekordów ma oznaczyć reguła)
PRZYKLADY = [
    pytest.param(
        erp.ERP_01,
        "INSERT INTO erp_faktury VALUES"
        " ('FV/2026/08/00003', 200001, DATE '2026-09-30', 'faktura', 'PLN', 100.0, 23.0)",
        "rok i miesiąc w numerze = data",
        1,
        id="ERP-01 miesiac w numerze inny niz data",
    ),
    pytest.param(
        erp.ERP_01,
        "UPDATE erp_faktury SET waluta = 'EUR' WHERE nr_faktury = 'FV/2026/09/00002'",
        "waluta: isin(['PLN'])",
        1,
        id="ERP-01 faktura w EUR",
    ),
    pytest.param(
        erp.ERP_02,
        "UPDATE erp_platnosci SET kwota = 1229.00 WHERE nr_faktury = 'FV/2026/09/00001'",
        "płatność = netto + VAT",
        1,
        id="ERP-02 platnosc rozna od netto + VAT",
    ),
    pytest.param(
        erp.ERP_03,
        # 10 l mleka UHT po 3 zł z VAT 23% zamiast 5%
        """INSERT INTO erp_faktury VALUES ('FV/2026/09/00003', 200001, DATE '2026-09-30', 'faktura', 'PLN', 30.0, 6.90);
           INSERT INTO erp_pozycje VALUES ('FV/2026/09/00003', '20.01.0001', 10, 3.0)""",
        "VAT = Σ netto pozycji × stawka indeksu",
        1,
        id="ERP-03 mleko z VAT 23 procent",
    ),
    pytest.param(
        erp.ERP_04,
        "UPDATE erp_faktury SET kwota_netto = 1001.0 WHERE nr_faktury = 'FV/2026/09/00001'",
        "kwota_netto = Σ ilosc × cena (±1 gr)",
        1,
        id="ERP-04 naglowek inny niz suma pozycji",
    ),
    pytest.param(
        erp.ERP_05,
        "UPDATE erp_faktury SET id_kontrahenta = 299999 WHERE nr_faktury = 'FV/2026/09/00002'",
        "kontrahent jest w dokładnie jednej z tabel: aktywni, archiwum",
        1,
        id="ERP-05 kontrahent spoza aktywnych i archiwum",
    ),
    pytest.param(
        erp.ERP_06,
        "UPDATE erp_kartoteka SET kategoria = NULL WHERE indeks = '80.01.0001'",
        "kategoria: brak wartości",
        1,
        id="ERP-06 abonament bez kategorii",
    ),
    pytest.param(
        erp.ERP_07,
        "INSERT INTO erp_kartoteka VALUES ('10.02.0001', 'KAWA ZIARN. CREMA 1KG', 'Detal')",
        "indeksy_o_tej_nazwie: equal_to(1)",
        1,
        id="ERP-07 druga pozycja kartoteki o tej samej nazwie",
    ),
    pytest.param(
        erp.ERP_08,
        # drugi rekord firmy Alfa: ten sam NIP bez myślników, ten sam adres, inna pisownia nazwy
        """INSERT INTO erp_kontrahenci VALUES (260001, 'ALFA SP Z OO', '1234563218', 'ul. Biurowa 1', '60-001', NULL);
           UPDATE erp_faktury SET id_kontrahenta = 260001 WHERE nr_faktury = 'FV/2026/09/00002'""",
        "brak starszego kontrahenta z tym samym NIP-em",
        1,
        id="ERP-08 faktura na drugi rekord kontrahenta",
    ),
    pytest.param(
        erp.ERP_09,
        "UPDATE erp_kontrahenci SET nip = '123456321' WHERE id_kontrahenta = 200001",
        "NIP: 10 cyfr i poprawna suma kontrolna",
        1,
        id="ERP-09 NIP z 9 cyframi",
    ),
    pytest.param(
        erp.ERP_09,
        "UPDATE erp_kontrahenci SET nip = '1234563219' WHERE id_kontrahenta = 200001",
        "NIP: 10 cyfr i poprawna suma kontrolna",
        1,
        id="ERP-09 NIP ze zla suma kontrolna",
    ),
    pytest.param(
        erp.ERP_10,
        "UPDATE erp_kontrahenci SET id_biura_crm = NULL WHERE id_kontrahenta = 200002",
        "id_biura_crm: brak wartości",
        1,
        id="ERP-10 kontrahent bez ID z CRM",
    ),
    pytest.param(
        erp.ERP_11,
        # trzy zwykłe faktury po 1 000 zł, a wrześniowa 10 × większa
        """INSERT INTO erp_faktury VALUES
               ('FV/2026/06/00001', 200001, DATE '2026-06-30', 'faktura', 'PLN', 1000.0, 230.0),
               ('FV/2026/07/00001', 200001, DATE '2026-07-31', 'faktura', 'PLN', 1000.0, 230.0),
               ('FV/2026/08/00001', 200001, DATE '2026-08-31', 'faktura', 'PLN', 1000.0, 230.0);
           UPDATE erp_faktury SET kwota_netto = 10000.0, vat = 2300.0 WHERE nr_faktury = 'FV/2026/09/00001'""",
        "netto ≤ 8 × mediana faktur klienta z 365 dni",
        1,
        id="ERP-11 faktura 10 razy wieksza niz zwykle",
    ),
    pytest.param(
        erp.ERP_12,
        "INSERT INTO erp_faktury VALUES"
        " ('KOR/2026/09/0001', 200001, DATE '2026-09-30', 'korekta', 'PLN', -100.0, -23.0)",
        "brak kolumny nr_faktury_korygowanej",
        1,
        id="ERP-12 korekta bez faktury korygowanej",
    ),
    pytest.param(
        erp.ERP_13,
        "UPDATE erp_platnosci SET data_platnosci = DATE '2026-09-20'",
        "ostatnia płatność nie starsza niż 5 dni",
        1,
        id="ERP-13 platnosci sprzed 10 dni",
    ),
    pytest.param(
        erp.ERP_14,
        # po 10 faktur w czerwcu, lipcu i sierpniu, a we wrześniu tylko 2
        """INSERT INTO erp_faktury
           SELECT format('FV/2026/{:02d}/{:05d}', m, n), 200001, last_day(make_date(2026, m, 1)),
                  'faktura', 'PLN', 100.0, 23.0
           FROM range(6, 9) a(m), range(1, 11) b(n)""",
        "faktury = 0.9–1.1 × mediana z 3 miesięcy",
        1,
        id="ERP-14 brak hurtowych faktur z konca miesiaca",
    ),
]


@pytest.mark.parametrize("regula", erp.REGULY, ids=lambda r: r.id)
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
    assert {p.values[0].id for p in PRZYKLADY} == {r.id for r in erp.REGULY}


def test_korekta_ze_wskazaniem_faktury_przechodzi(baza, sprawdz):
    """Gdy ERP doda numer faktury korygowanej, ERP-12 przechodzi, a typy z ERP-01 nadal się zgadzają."""
    baza.execute("""ALTER TABLE erp_faktury ADD COLUMN nr_faktury_korygowanej VARCHAR;
           INSERT INTO erp_faktury VALUES
               ('KOR/2026/09/0001', 200001, DATE '2026-09-30', 'korekta', 'PLN', -100.0, -23.0, 'FV/2026/09/00001')""")
    for regula in [erp.ERP_01, erp.ERP_12]:
        wynik = sprawdz(regula)
        assert wynik.ok, (regula.id, wynik.naruszenia)
