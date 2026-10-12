"""Nocny potok: dwa przebiegi tej samej nocy i ponowienie kroku po awarii dają te same liczby.

Baza to czyste dane z conftest.py, z których dzień DZIEN przenosimy do katalogu dostaw: stan sprzed nocy i dostawa
tej nocy. Pliki z kas zapisujemy w formacie z kontraktu (cp1250, `;`, przecinek dziesiętny).
"""

import os
from datetime import date, datetime
from decimal import Decimal

import duckdb
import inngest
import pytest

from api import inngest_app
from api.data_platform import noc
from api.data_platform.kontrakty.kontrakt import wczytaj
from tests.data_platform.conftest import CZYSTE_DANE, DZIEN

KONTRAKT_POS = wczytaj("pos_paragony")
PLIK_Z_KASY = f"pos_paragony_1_{DZIEN}.csv"
DOSTAWA_PARQUET = {
    "pos": {"pos_pozycje": "SELECT * FROM pos_pozycje"},
    "erp": {
        "erp_faktury": "SELECT * FROM erp_faktury WHERE data = $d",
        "erp_pozycje": "SELECT * FROM erp_pozycje SEMI JOIN (SELECT nr_faktury FROM erp_faktury WHERE data = $d)"
        " USING (nr_faktury)",
        "erp_platnosci": "SELECT * FROM erp_platnosci WHERE data_platnosci = $d",
    },
    "ecom": {
        "ecom_zamowienia": "SELECT * FROM ecom_zamowienia",
        "ecom_pozycje": "SELECT * FROM ecom_pozycje",
        "ecom_subskrypcje": "SELECT * FROM ecom_subskrypcje",
        "kursy_nbp": "SELECT * FROM kursy_nbp WHERE data = $d",
    },
}
# Stan sprzed nocy: bez wierszy z dostawy (w czystych danych z DZIEN są wszystkie paragony, zamówienia i obciążenia)
COFNIJ_DZIEN = """
    DELETE FROM pos_paragony; DELETE FROM pos_pliki; DELETE FROM pos_pozycje;
    DELETE FROM erp_pozycje WHERE nr_faktury IN (SELECT nr_faktury FROM erp_faktury WHERE data = $d);
    DELETE FROM erp_faktury WHERE data = $d; DELETE FROM erp_platnosci WHERE data_platnosci = $d;
    DELETE FROM ecom_zamowienia; DELETE FROM ecom_pozycje; DELETE FROM ecom_subskrypcje;
    DELETE FROM kursy_nbp WHERE data = $d;
"""
MAPA_KONTRAHENTOW = """
    CREATE TABLE mapa_kontrahentow AS
    SELECT id_kontrahenta AS id_stary, id_kontrahenta AS id_nowy FROM erp_kontrahenci
    UNION ALL SELECT id_kontrahenta, id_kontrahenta FROM erp_kontrahenci_archiwum;
"""

# Źródła cech churnu spoza nocnych dostaw (CRM, IoT, helpdesk). Biuro 10001 ma aktywną umowę, 10002 wypowiedziało ją
# przed nocą, więc nie ma go w populacji cech.
ZRODLA_CECH = """
    CREATE TABLE crm_biura (
        id_biura BIGINT, miasto VARCHAR, branza VARCHAR, liczba_pracownikow BIGINT, am_id BIGINT, plan VARCHAR,
        cena_mies DOUBLE, data_startu DATE, data_konca_umowy DATE, status VARCHAR);
    INSERT INTO crm_biura VALUES
        (10001, 'Poznań', 'IT', 50, 3, 'S', 999, DATE '2024-03-01', DATE '2027-02-28', 'aktywny'),
        (10002, 'Poznań', 'Bank', 20, 3, 'M', 1500, DATE '2023-11-01', DATE '2026-10-31', 'zakończony');
    CREATE TABLE crm_umowy_historia (id_biura BIGINT, data_zdarzenia DATE, typ VARCHAR, plan VARCHAR, cena DOUBLE);
    INSERT INTO crm_umowy_historia VALUES
        (10001, DATE '2024-03-01', 'start', 'S', 999),
        (10002, DATE '2023-11-01', 'start', 'M', 1500),
        (10002, DATE '2026-09-15', 'wypowiedzenie', 'M', 1500);
    CREATE TABLE iot_ekspresy (id_ekspresu VARCHAR, id_biura BIGINT);
    CREATE TABLE iot_telemetria (
        id_ekspresu VARCHAR, data DATE, zaparzenia BIGINT, bledy BIGINT, data_dostarczenia DATE);
    CREATE TABLE helpdesk_zgloszenia (id VARCHAR, id_biura BIGINT, utworzono TIMESTAMP, kategoria VARCHAR);
    CREATE TABLE crm_kontakty_am (id_biura BIGINT, data DATE, rabat_retencyjny_pct BIGINT);
    CREATE TABLE ankiety_nps (id_biura BIGINT, data_wysylki DATE, data_odpowiedzi DATE, wynik BIGINT);
"""


def _zapisz_plik_z_kasy(con: duckdb.DuckDBPyConnection, sciezka) -> None:
    dostawa, kolumny = KONTRAKT_POS.dostawa, KONTRAKT_POS.wymagane
    wiersze = con.execute(f"SELECT {', '.join(kolumny)} FROM pos_paragony ORDER BY nr_paragonu").fetchall()

    def pole(v) -> str:
        if v is None:
            return ""
        return str(v) if isinstance(v, datetime) else str(v).replace(".", dostawa.separator_dziesietny)

    linie = [dostawa.separator.join(kolumny)] + [dostawa.separator.join(pole(v) for v in w) for w in wiersze]
    sciezka.write_text("\n".join(linie) + "\n", encoding=dostawa.kodowanie)
    czas = datetime(2026, 10, 1, 5, 12).timestamp()  # dotarł przed terminem D+1 6:00
    os.utime(sciezka, (czas, czas))


@pytest.fixture
def ust(tmp_path) -> noc.Ustawienia:
    """Baza w stanie sprzed nocy i dostawa dnia DZIEN w katalogu dostaw."""
    ust = noc.Ustawienia(
        baza=tmp_path / "kawosz.duckdb", dostawy=tmp_path / "dostawy", raporty=tmp_path / "kwarantanna"
    )
    con = duckdb.connect(str(ust.baza))
    con.execute(CZYSTE_DANE + MAPA_KONTRAHENTOW + ZRODLA_CECH)
    for zrodlo, pliki in DOSTAWA_PARQUET.items():
        (ust.dostawy / str(DZIEN) / zrodlo).mkdir(parents=True)
        for plik, sql in pliki.items():
            sql = sql.replace("$d", f"DATE '{DZIEN}'")
            con.execute(f"COPY ({sql}) TO '{ust.dostawy / str(DZIEN) / zrodlo / plik}.parquet' (FORMAT parquet)")
    _zapisz_plik_z_kasy(con, ust.dostawy / str(DZIEN) / "pos" / PLIK_Z_KASY)
    con.execute(COFNIJ_DZIEN.replace("$d", f"DATE '{DZIEN}'"))
    con.close()
    return ust


def odcisk(ust: noc.Ustawienia) -> dict:
    """Liczba wierszy i suma skrótów wierszy każdej tabeli, którą zmienia noc: równe odciski = te same dane."""
    tabele = [t.nazwa for ts in noc.TABELE.values() for t in ts]
    tabele += ["kwarantanna", "wsady", "naruszenia", "most_przychodu", "cechy_aktualne"]
    con = duckdb.connect(str(ust.baza), read_only=True)
    try:
        wynik = {}
        for t in tabele:
            kolumny = "* EXCLUDE (zapisano)" if t == "wsady" else "*"  # czas zapisu statusu to nie liczba z danych
            wynik[t] = con.sql(f"SELECT count(*), sum(hash(w)) FROM (SELECT {kolumny} FROM {t}) w").fetchone()
        robocze = "SELECT count(*) FROM duckdb_schemas() WHERE schema_name LIKE 'wsad_%'"
        wynik["schematy robocze"] = con.sql(robocze).fetchone()
        return wynik
    finally:
        con.close()


def policz(ust: noc.Ustawienia, sql: str):
    con = duckdb.connect(str(ust.baza), read_only=True)
    try:
        return con.sql(sql).fetchall()
    finally:
        con.close()


def test_dobra_dostawa_jest_opublikowana_a_drugi_przebieg_niczego_nie_dubluje(ust):
    pierwszy = inngest_app.przebieg(DZIEN, ust)
    po_pierwszym = odcisk(ust)
    drugi = inngest_app.przebieg(DZIEN, ust)

    assert {z: w["status"] for z, w in pierwszy["wsady"].items()} == dict.fromkeys(noc.ZRODLA, "opublikowany")
    liczby = "SELECT (SELECT count(*) FROM pos_paragony), (SELECT count(*) FROM pos_pozycje),"
    liczby += " (SELECT count(*) FROM erp_faktury), (SELECT count(*) FROM ecom_zamowienia)"
    assert policz(ust, liczby) == [(2, 2, 2, 2)]
    assert odcisk(ust) == po_pierwszym
    assert drugi["most"] == pierwszy["most"]
    assert po_pierwszym["schematy robocze"] == (0,)


def test_wsad_z_bledem_blokujacym_idzie_do_kwarantanny_z_raportem_a_reszta_jest_publikowana(ust):
    kopia = ust.dostawy / str(DZIEN) / "pos" / f"pos_paragony_1_{DZIEN} (1).csv"  # kasa wysłała plik drugi raz
    kopia.write_bytes((ust.dostawy / str(DZIEN) / "pos" / PLIK_Z_KASY).read_bytes())

    wynik = inngest_app.przebieg(DZIEN, ust)
    po_pierwszym = odcisk(ust)
    inngest_app.przebieg(DZIEN, ust)

    pos = wynik["wsady"]["pos"]
    assert pos["status"] == "kwarantanna" and "POS-02" in pos["blokujace"]
    pozostale = {z: w["status"] for z, w in wynik["wsady"].items() if z != "pos"}
    assert pozostale == {"erp": "opublikowany", "ecom": "opublikowany"}
    assert policz(ust, "SELECT count(*) FROM pos_paragony") == [(0,)]  # raporty nie widzą złego wsadu
    assert policz(ust, "SELECT tabela, count(*) FROM kwarantanna GROUP BY 1 ORDER BY 1") == [
        ("pos_paragony", 4),  # dwa paragony z oryginału i dwa z kopii
        ("pos_pliki", 2),
        ("pos_pozycje", 2),
    ]
    assert "POS-02" in (ust.raporty / f"pos_{DZIEN}.md").read_text()
    assert odcisk(ust) == po_pierwszym


def test_wycena_wsadu_to_przychod_netto_a_kopia_pliku_to_zawyzenie(ust):
    """Paragony z czystych danych: latte 14 zł z VAT 8% i kawa 169 zł z VAT 23% → 12,96 + 137,40 = 150,36 zł netto.
    Kopia pliku z kasy zawyżyłaby przychód o tyle samo, bo powtarza oba paragony."""
    kopia = ust.dostawy / str(DZIEN) / "pos" / f"pos_paragony_1_{DZIEN} (1).csv"
    kopia.write_bytes((ust.dostawy / str(DZIEN) / "pos" / PLIK_Z_KASY).read_bytes())

    wynik = inngest_app.przebieg(DZIEN, ust)

    assert wynik["wsady"]["pos"]["wycena"] == {"przychod_netto": 150.36, "zawyzenie": 150.36, "uwaga": None}
    assert wynik["wsady"]["erp"]["wycena"]["przychod_netto"] == 1500.0  # faktury netto 1000 + 500 zł
    assert policz(ust, "SELECT wsad, przychod_netto, zawyzenie FROM wsady WHERE zrodlo = 'pos'") == [
        (f"pos/{DZIEN}", Decimal("150.36"), Decimal("150.36"))
    ]
    # wynik każdej reguły źródła, także tych bez naruszeń (panel jakości liczy z nich trend)
    naruszenia = dict(policz(ust, "SELECT regula, bledne FROM naruszenia WHERE zrodlo = 'pos'"))
    assert len(naruszenia) == len(noc.REGULY["pos"]) and naruszenia["POS-02"] == 2 and naruszenia["POS-07"] == 0


def test_poprawiona_dostawa_zdejmuje_wsad_z_kwarantanny(ust):
    kopia = ust.dostawy / str(DZIEN) / "pos" / f"pos_paragony_1_{DZIEN} (1).csv"
    kopia.write_bytes((ust.dostawy / str(DZIEN) / "pos" / PLIK_Z_KASY).read_bytes())
    inngest_app.przebieg(DZIEN, ust)

    kopia.unlink()  # zespół danych usuwa kopię i uruchamia noc ponownie
    wynik = inngest_app.przebieg(DZIEN, ust)

    assert wynik["wsady"]["pos"]["status"] == "opublikowany"
    assert policz(ust, "SELECT count(*) FROM pos_paragony") == [(2,)]
    assert policz(ust, "SELECT count(*) FROM kwarantanna") == [(0,)]
    assert policz(ust, "SELECT wsad, status FROM wsady WHERE zrodlo = 'pos'") == [
        (f"pos/{DZIEN}", "opublikowany")
    ]
    assert not (ust.raporty / f"pos_{DZIEN}.md").exists()


def test_ponowienie_kroku_po_awarii_po_zapisie_daje_te_same_liczby(ust):
    """Jak w Inngest: wyniki udanych kroków są zapamiętane, a krok, który padł, wykonuje się ponownie w całości.

    Najgorszy przypadek: publikacja zapisała dane, ale proces padł, zanim Inngest dostał wynik kroku."""
    pamiec: dict[str, object] = {}
    awaria = {"publikuj-ecom"}

    def krok(nazwa, funkcja, *argumenty):
        if nazwa not in pamiec:
            wynik = funkcja(*argumenty)
            if nazwa in awaria:
                awaria.discard(nazwa)
                raise RuntimeError("proces padł po zapisie")
            pamiec[nazwa] = wynik
        return pamiec[nazwa]

    with pytest.raises(RuntimeError):
        inngest_app.przebieg(DZIEN, ust, krok)
    wykonane_przed_awaria = set(pamiec)
    inngest_app.przebieg(DZIEN, ust, krok)
    po_ponowieniu = odcisk(ust)

    inngest_app.przebieg(DZIEN, ust)  # drugi, zwykły przebieg tej samej nocy
    assert "publikuj-ecom" not in wykonane_przed_awaria and "wczytaj-ecom" in wykonane_przed_awaria
    assert odcisk(ust) == po_ponowieniu


def test_noc_odswieza_cechy_aktualne_na_poczatek_dnia_po_dniu_nocy(ust):
    """Noc dla D działa o 3:00 w D + 1, więc cechy to stan na początek D + 1, jak t0 w treningu."""
    wynik = inngest_app.przebieg(DZIEN, ust)

    assert wynik["cechy"] == {"t0": "2026-10-01", "wiersze": 1}
    assert policz(ust, "SELECT id_biura, t0, plan FROM cechy_aktualne") == [(10001, date(2026, 10, 1), "S")]


def test_dzien_nocy_z_crona_to_wczoraj_w_czasie_polskim_a_z_recznego_zdarzenia_dzien_ze_zdarzenia():
    o_3_w_warszawie = int(datetime.fromisoformat("2026-10-01T03:00:00+02:00").timestamp() * 1000)
    cron = inngest.Event(name="inngest/scheduled.timer", data={"cron": inngest_app.CRON}, ts=o_3_w_warszawie)
    reczne = inngest.Event(name=inngest_app.ZDARZENIE, data={"dzien": "2026-09-12"})
    assert inngest_app.dzien_nocy(cron) == date(2026, 9, 30)
    assert inngest_app.dzien_nocy(reczne) == date(2026, 9, 12)
