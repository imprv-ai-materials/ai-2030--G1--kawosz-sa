"""Każda reguła przychodu netto na ręcznie policzonym przypadku (docs/przychod_netto.md, sekcja 3).

Przypadki są w conftest.py. Każdą regułę sprawdzamy osobno na liniach takich, jak liczy je BI, a całą definicję
na końcu. Kwoty w oczekiwanych wartościach są wypisane działaniem, tak jak liczy się je ręcznie.
"""

from datetime import date

import pytest

from api.contexts_boundaries.revenue_bc.przychod import definicja as d

WRZESIEN = date(2026, 9, 1)
KROK = {k.sql.__name__: k for k in d.KROKI}
POS_NETTO = 14 / 1.08 + 169 / 1.23  # latte z VAT 8% + kawa z VAT 23% = 150,36 zł
BI = {d.POS: 2 * 183.00, d.ZAMOWIENIA: 645.00, d.SUBSKRYPCJE: 438.00, d.KARTY: 300.00, d.ERP: 1000.00 - 100.00}


def _zrodla(baza, kroki, bez_duplikatow=False) -> dict[str, float]:
    wynik = d.suma(baza, WRZESIEN, kroki, bez_duplikatow)
    return dict(zip(wynik["zrodlo"], wynik["kwota_pln"]))


def _po_regule(baza, regula: str, **zmienione) -> None:
    """Reguła sama na liniach BI zmienia tylko podane źródła, i to dokładnie do ręcznie policzonej kwoty."""
    assert _zrodla(baza, [KROK[regula]]) == pytest.approx(BI | zmienione)


def test_linie_startowe_to_suma_bi(baza):
    """Zamówienia we wrześniu w UTC: 123 + 61,50 + 20 (EUR) + 123 + 246 + 61,50 (30.09 22:15) + 10 (EUR) = 645.
    Subskrypcje: 39 + 399. Karty sprzedane we wrześniu: 100 + 50 + 150. ERP: faktura 1000 i korekta −100."""
    assert _zrodla(baza, []) == pytest.approx(BI)


def test_1_pos_netto_wedlug_stawek_z_pozycji(baza):
    _po_regule(baza, "pos_netto", **{d.POS: 2 * POS_NETTO})  # BI ma ten paragon dwa razy (zdublowany plik)


def test_2_ecom_subskrypcje_i_karty_netto_23(baza):
    _po_regule(baza, "vat_23", **{d.ZAMOWIENIA: 645 / 1.23, d.SUBSKRYPCJE: 438 / 1.23, d.KARTY: 300 / 1.23})


def test_3_korekty_erp_i_zwroty_ecom_odjete(baza):
    """Korekta −100 jest już w BI (ERP bez zmian), zwrot 61,50 znika z zamówień."""
    _po_regule(baza, "korekty_i_zwroty", **{d.ZAMOWIENIA: 645 - 61.50})


def test_4_erp_po_mapowaniu_kontrahentow(baza):
    """Faktura na drugi rekord firmy (260001) trafia na rekord główny 200001, a suma się nie zmienia."""
    _po_regule(baza, "mapa_kontrahentow")
    erp = d.linie(baza, WRZESIEN, [KROK["mapa_kontrahentow"]], bez_duplikatow=False).query("zrodlo == @d.ERP")
    klienci = erp.set_index("dokument")["id_kontrahenta"].to_dict()
    assert klienci == {"FV/2026/09/00001": 200001, "KOR/2026/09/0001": 200001}


def test_5_plan_roczny_na_12_miesiecy(baza):
    """Wrzesień: miesięczny 39 + 1/12 planu z 2.09.2026 + 1/12 planu z 14.10.2025. Plan z 30.09.2025 (UTC) kończy się
    w sierpniu 2026."""
    _po_regule(baza, "roczne_na_12_miesiecy", **{d.SUBSKRYPCJE: 39 + 399 / 12 + 399 / 12})


def test_6_karty_w_dniu_realizacji(baza):
    """Wrzesień: karta 200 sprzedana w sierpniu i karta 50; nie ma karty niezrealizowanej (100) i zrealizowanej
    w październiku (150)."""
    _po_regule(baza, "karty_w_dniu_realizacji", **{d.KARTY: 200 + 50})


def test_7_eur_po_kursie_z_dnia_sprzedazy(baza):
    """Sobota 5.09 i niedziela 6.09 (UTC) nie mają notowania, więc obie biorą kurs z piątku 4.09: 4,2208."""
    _po_regule(baza, "eur_po_kursie", **{d.ZAMOWIENIA: 123 + 61.50 + 20 * 4.2208 + 123 + 246 + 61.50 + 10 * 4.2208})


def test_8_bez_zamowien_testowych(baza):
    """Znika zamówienie z e-mailem qa@kawosz.pl (123) i z notatką „zamówienie testowe QA” (246)."""
    _po_regule(baza, "bez_testowych", **{d.ZAMOWIENIA: 645 - 123 - 246})


def test_9_doba_wedlug_czasu_polskiego(baza):
    """Wchodzi zamówienie z 31.08 22:30 UTC (123) i subskrypcja z 31.08 22:20 UTC (39); wychodzi zamówienie
    z 30.09 22:15 UTC (61,50), bo w Warszawie to już 1.10."""
    _po_regule(baza, "czas_polski", **{d.ZAMOWIENIA: 645 + 123 - 61.50, d.SUBSKRYPCJE: 438 + 39})


def test_przychod_netto_wedlug_definicji(baza):
    zamowienia = 123 / 1.23 + 20 / 1.23 * 4.2208 + 10 / 1.23 * 4.2039 + 123 / 1.23  # bez zwrotu, testowych i 1.10
    subskrypcje = 2 * 39 / 1.23 + 3 * 399 / 1.23 / 12  # dwa miesięczne i 1/12 trzech planów rocznych
    wynik = d.przychod_netto(baza, WRZESIEN)
    assert dict(zip(wynik["zrodlo"], wynik["kwota_pln"])) == pytest.approx(
        {d.POS: POS_NETTO, d.ZAMOWIENIA: zamowienia, d.SUBSKRYPCJE: subskrypcje, d.KARTY: 250 / 1.23, d.ERP: 900}
    )


def test_wynik_nie_zalezy_od_kolejnosci_regul(baza):
    """Kurs EUR i miesiąc planu rocznego liczymy przy sumowaniu, więc kolejność kroków zmienia tylko most."""
    assert _zrodla(baza, d.KROKI[::-1], True) == pytest.approx(_zrodla(baza, d.KROKI, True))


def test_kurs_z_dnia_po_czasie_polskim(baza):
    """Niedziela 6.09 22:30 UTC to poniedziałek 7.09 w Warszawie: po kroku „czas polski” kurs z 7.09."""
    kroki = [KROK["eur_po_kursie"], KROK["czas_polski"]]
    zamowienie = d.linie(baza, WRZESIEN, kroki).query("dokument == '1000008'").iloc[0]
    assert (str(zamowienie["data_kursu"].date()), zamowienie["kwota_pln"]) == ("2026-09-07", pytest.approx(42.039))


@pytest.mark.parametrize(
    "notatka, email, testowe",
    [
        ("Proszę o szybką wysyłkę", "anna@example.com", False),
        (None, None, False),  # pobranie bez e-maila
        ("TEST – nie wysyłać", "anna@example.com", True),
        ("[TEST] sprawdzenie integracji z kurierem", None, True),
        ("prosze nie realizowac (test)", None, True),
        ("Bez folii bąbelkowej, dziękuję :)", "QA+108@Kawosz.pl", True),
    ],
)
def test_rozpoznanie_zamowienia_testowego(baza, notatka, email, testowe):
    sql = f"SELECT {d.JEST_TESTOWE} FROM (SELECT ?::VARCHAR AS notatka, ?::VARCHAR AS email)"
    assert baza.execute(sql, [notatka, email]).fetchone()[0] is testowe


@pytest.mark.parametrize(
    "psucie, komunikat",
    [
        ("DELETE FROM kursy_nbp WHERE data <= DATE '2026-09-04'", "bez kursu EUR"),  # 5.09 nie ma wcześniejszego kursu
        ("DELETE FROM pos_pozycje", "bez kwoty"),  # paragon bez pozycji nie ma netto
    ],
)
def test_brak_kursu_albo_pozycji_to_blad_a_nie_pominieta_linia(baza, psucie, komunikat):
    baza.execute(psucie)
    with pytest.raises(ValueError, match=komunikat):
        d.przychod_netto(baza, WRZESIEN)
