"""Poniedziałkowa lista wizyt: biura opiekuna z p ≥ C / (s × V), od najwyższego p, najwyżej tyle, ile opiekunowi
zostało wizyt w kwartale; bez biur po niedawnym kontakcie retencyjnym; część biur losowo w grupie kontrolnej; trzy
powody ryzyka. Zapis do lista_wizyt i zadanie Inngest."""

import os
from datetime import date, datetime

import duckdb
import inngest
import pandas as pd
import pytest

from api.contexts_boundaries.retention_bc.radar import lista_tygodnia as lt

# Klient Inngest (api/inngest_app.py) powstaje przy imporcie: w testach w trybie deweloperskim.
os.environ.setdefault("INNGEST_DEV", "1")

from api import inngest_app  # noqa: E402

# C / (s × V) = 1 000 / (0,5 × 10 000) = 0,2; wartość wizyty = p × 5 000 − 1 000
S, V, C = 0.5, 10_000, 1_000
TYDZIEN = date(2026, 10, 5)  # poniedziałek, IV kwartał


@pytest.fixture
def opiekunowie() -> pd.DataFrame:
    return pd.DataFrame({"am_id": [1, 2, 3], "imie_nazwisko": ["Ola", "Jan", "Ewa"]})


@pytest.fixture
def biura() -> pd.DataFrame:
    """Ola: cztery biura nad progiem i jedno pod; Jan: jedno nad progiem; Ewa: żadnego."""
    return pd.DataFrame({
        "id_biura": [1, 2, 3, 4, 5, 6, 7],
        "nazwa": list("abcdefg"),
        "miasto": ["Poznań"] * 7,
        "am_id": [1, 1, 1, 1, 1, 2, 3],
        "p": [0.3, 0.9, 0.25, 0.5, 0.1, 0.4, 0.05],
    })


BEZ_KONTAKTOW = pd.DataFrame({"id_biura": [], "data": [], "typ": [], "czy_retencyjna": []})


def kontakty(*wiersze: tuple[int, str, str, bool]) -> pd.DataFrame:
    return pd.DataFrame(wiersze, columns=["id_biura", "data", "typ", "czy_retencyjna"]).assign(
        data=lambda d: pd.to_datetime(d["data"])
    )


def lista(biura, opiekunowie, kontakty_=BEZ_KONTAKTOW, limit=10, udzial=0.0, tydzien=TYDZIEN):
    return lt.lista_tygodnia(biura, opiekunowie, kontakty_, tydzien, S, V, C, limit, udzial)


def ids(wiersze: pd.DataFrame, am_id: int, grupa: str = "wizyta") -> list[int]:
    return wiersze.loc[(wiersze["am_id"] == am_id) & (wiersze["grupa"] == grupa), "id_biura"].tolist()


def test_lista_opiekuna_to_jego_biura_z_p_od_progu_od_najwyzszego_p(biura, opiekunowie):
    wiersze, _ = lista(biura, opiekunowie)
    assert ids(wiersze, 1) == [2, 4, 1, 3]
    assert ids(wiersze, 2) == [6]
    assert wiersze.loc[wiersze["am_id"] == 1, "lp"].tolist() == [1, 2, 3, 4]


def test_wartosc_wizyty_to_p_s_V_minus_C(biura, opiekunowie):
    wiersze, _ = lista(biura, opiekunowie)
    assert wiersze.set_index("id_biura").loc[2, "wartosc_wizyty"] == pytest.approx(0.9 * 5_000 - 1_000)


def test_lista_ma_najwyzej_tyle_biur_ile_wizyt_na_opiekuna(biura, opiekunowie):
    wiersze, podsumowanie = lista(biura, opiekunowie, limit=2)
    assert ids(wiersze, 1) == [2, 4]
    ola = next(o for o in podsumowanie if o["am_id"] == 1)
    assert (ola["nad_progiem"], ola["na_liscie"]) == (4, 2)


def test_opiekun_bez_biur_nad_progiem_ma_pusta_liste_ale_jest_w_podsumowaniu(biura, opiekunowie):
    wiersze, podsumowanie = lista(biura, opiekunowie)
    assert ids(wiersze, 3) == []
    assert [o["opiekun"] for o in podsumowanie] == ["Ola", "Jan", "Ewa"]


def test_pomija_biura_po_kontakcie_retencyjnym_w_ostatnich_90_dniach(biura, opiekunowie):
    k = kontakty(
        (2, "2026-09-20", "wizyta", True),  # 15 dni temu: pomijamy
        (4, "2026-08-01", "telefon", True),  # 65 dni temu, telefon z rabatem: pomijamy
        (1, "2026-07-06", "wizyta", True),  # 91 dni temu: rabat się skończył, wraca na listę
        (3, "2026-09-30", "wizyta", False),  # zwykła wizyta, nie retencyjna: zostaje
    )
    wiersze, podsumowanie = lista(biura, opiekunowie, k)
    assert ids(wiersze, 1) == [1, 3]
    assert next(o for o in podsumowanie if o["am_id"] == 1)["pominiete_po_kontakcie"] == 2


def test_wizyty_retencyjne_z_tego_kwartalu_zmniejszaja_limit_opiekuna(biura, opiekunowie):
    # biuro 5 (Ola, pod progiem) dostało wizytę retencyjną 1.10, czyli w IV kwartale; biuro 2 we wrześniu (III kw.)
    k = kontakty((5, "2026-10-01", "wizyta", True), (2, "2026-09-15", "wizyta", True))
    wiersze, podsumowanie = lista(biura, opiekunowie, k, limit=3)
    ola = next(o for o in podsumowanie if o["am_id"] == 1)
    assert (ola["wizyty_w_kwartale"], ola["limit"]) == (1, 2)
    assert ids(wiersze, 1) == [4, 1]  # 2 pominięte po wrześniowej wizycie, zostały 2 miejsca


def test_biura_z_kontroli_sa_na_liscie_bez_wizyty_i_nie_zajmuja_miejsc(biura, opiekunowie, monkeypatch):
    # Ola od najwyższego p: 2, 4 (kontrola), 1, 3 (kontrola); limit 2 wizyt: 2 i 1, a 4 to kontrola z tego samego
    # zakresu p. Biuro 3 jest poniżej ostatniej wizyty, więc i tak by jej nie dostało: nie trafia do kontroli.
    monkeypatch.setattr(lt, "w_kontroli", lambda id_biura, kwartal, udzial: id_biura in (3, 4))
    wiersze, podsumowanie = lista(biura, opiekunowie, limit=2, udzial=0.1)
    assert (ids(wiersze, 1), ids(wiersze, 1, "kontrola")) == ([2, 1], [4])
    ola = next(o for o in podsumowanie if o["am_id"] == 1)
    assert (ola["na_liscie"], ola["w_kontroli"]) == (2, 1)


def test_biuro_jest_w_kontroli_przez_caly_kwartal_niezaleznie_od_tygodnia(biura, opiekunowie):
    def grupy(tydzien):
        wiersze, _ = lista(biura, opiekunowie, udzial=0.5, tydzien=tydzien)
        return dict(zip(wiersze["id_biura"], wiersze["grupa"]))

    assert grupy(TYDZIEN) == grupy(date(2026, 10, 12)) == grupy(date(2026, 12, 28))


def test_bez_kontroli_wszystkie_biura_z_listy_dostaja_wizyte(biura, opiekunowie):
    wiersze, _ = lista(biura, opiekunowie)
    assert set(wiersze["grupa"]) == {"wizyta"}


def test_kontakty_z_dnia_listy_i_pozniej_sie_nie_licza(biura, opiekunowie):
    k = kontakty((2, "2026-10-05", "wizyta", True), (4, "2026-10-09", "wizyta", True))
    wiersze, podsumowanie = lista(biura, opiekunowie, k)
    assert ids(wiersze, 1) == [2, 4, 1, 3]
    assert next(o for o in podsumowanie if o["am_id"] == 1)["wizyty_w_kwartale"] == 0


# --- zapis i zadanie Inngest na bazie w pliku ---


class ModelZKolumny:
    """Zamiast aktywnego modelu: p to kolumna p_testowe z cechy_aktualne."""

    wersja = "testowa"
    cechy = ["p_testowe"]

    def predict_proba(self, X: pd.DataFrame) -> pd.Series:
        return X["p_testowe"].rename("p_odejdzie_90d")


@pytest.fixture
def baza(tmp_path, monkeypatch, biura, opiekunowie):
    sciezka = tmp_path / "kawosz.duckdb"
    con = duckdb.connect(str(sciezka))
    # jak w bazie: miasto i am_id są w cechy_aktualne, nazwa w crm_biura
    cechy = biura.rename(columns={"p": "p_testowe"})[["id_biura", "am_id", "miasto", "p_testowe"]].assign(
        t0=date(2026, 10, 5)
    )
    con.execute("CREATE TABLE cechy_aktualne AS SELECT * FROM cechy")
    con.execute("CREATE TABLE crm_biura AS SELECT id_biura, nazwa FROM biura")
    con.execute("CREATE TABLE crm_opiekunowie AS SELECT * FROM opiekunowie")
    con.execute(
        "CREATE TABLE crm_kontakty_am (id_biura BIGINT, data DATE, typ VARCHAR, czy_retencyjna BOOLEAN)"
    )
    con.close()
    monkeypatch.setattr(lt.aktywny, "wczytaj", lambda: ModelZKolumny())
    monkeypatch.setattr(
        lt, "zalozenia", lambda: {"s": S, "V": V, "C": C, "wizyty_na_opiekuna": 10, "udzial_kontroli": 0.0}
    )
    return sciezka


def wiersze_bazy(baza, sql: str) -> list[tuple]:
    con = duckdb.connect(str(baza), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_przygotuj_zapisuje_liste_tygodnia_z_modelem_i_zalozeniami(baza):
    wynik = lt.przygotuj(baza, TYDZIEN)
    assert wynik["model"] == "testowa" and wynik["t0_cech"] == "2026-10-05"
    assert {o["opiekun"]: o["na_liscie"] for o in wynik["opiekunowie"]} == {"Ola": 4, "Jan": 1, "Ewa": 0}
    zapis = wiersze_bazy(
        baza, "SELECT tydzien, kwartal, am_id, lp, id_biura, grupa, model FROM lista_wizyt ORDER BY am_id, lp"
    )
    assert zapis[0] == (TYDZIEN, "2026-Q4", 1, 1, 2, "wizyta", "testowa")
    assert len(zapis) == 5


def test_przygotuj_zapisuje_grupe_kontrolna_i_udzial(baza, monkeypatch):
    monkeypatch.setattr(lt, "w_kontroli", lambda id_biura, kwartal, udzial: id_biura == 4)
    monkeypatch.setattr(
        lt, "zalozenia", lambda: {"s": S, "V": V, "C": C, "wizyty_na_opiekuna": 10, "udzial_kontroli": 0.1}
    )
    lt.przygotuj(baza, TYDZIEN)
    assert wiersze_bazy(baza, "SELECT id_biura, udzial_kontroli FROM lista_wizyt WHERE grupa = 'kontrola'") == [
        (4, 0.1)
    ]


def test_przygotuj_zapisuje_powody_ryzyka(baza):
    lt.przygotuj(baza, TYDZIEN)
    # jedyna cecha modelu testowego to p_testowe; biuro 2 (0,9) ma ją wyżej niż typowe biuro (mediana 0,3)
    assert wiersze_bazy(baza, "SELECT powod_1, powod_2 FROM lista_wizyt WHERE id_biura = 2") == [
        ("p_testowe: 0.9", None)
    ]


def test_drugi_przebieg_tego_samego_tygodnia_nadpisuje_liste_a_inne_tygodnie_zostaja(baza):
    lt.przygotuj(baza, TYDZIEN)
    lt.przygotuj(baza, date(2026, 10, 12))  # cechy z 5.10, tydzień starsze: jeszcze dopuszczalne
    lt.przygotuj(baza, TYDZIEN)
    assert wiersze_bazy(baza, "SELECT tydzien, count(*) FROM lista_wizyt GROUP BY 1 ORDER BY 1") == [
        (TYDZIEN, 5),
        (date(2026, 10, 12), 5),
    ]


def test_cechy_starsze_niz_tydzien_albo_z_przyszlosci_przerywaja_bez_ponawiania(baza):
    with pytest.raises(inngest.NonRetriableError, match="starsze"):
        lt.przygotuj(baza, date(2026, 10, 13))
    with pytest.raises(inngest.NonRetriableError, match="po dniu listy"):
        lt.przygotuj(baza, date(2026, 9, 28))


def test_zadanie_inngest_liczy_liste_w_jednym_kroku(baza, monkeypatch):
    monkeypatch.setenv("KAWOSZ_BAZA", str(baza))
    kroki = []

    def krok(nazwa, funkcja, *argumenty):
        kroki.append(nazwa)
        return funkcja(*argumenty)

    wynik = inngest_app.przebieg_listy(TYDZIEN, inngest_app.noc.Ustawienia.z_env(), krok)
    assert kroki == ["lista-wizyt"]
    assert wynik["tydzien"] == "2026-10-05"


def test_lista_z_crona_to_poniedzialek_uruchomienia_a_z_recznego_zdarzenia_tydzien_ze_zdarzenia():
    o_6_w_poniedzialek = int(datetime.fromisoformat("2026-10-05T06:00:00+02:00").timestamp() * 1000)
    cron = inngest.Event(name="inngest/scheduled.timer", data={"cron": inngest_app.CRON_LISTA}, ts=o_6_w_poniedzialek)
    reczne = inngest.Event(name=inngest_app.ZDARZENIE_LISTA, data={"t0": "2026-10-12"})
    assert inngest_app.tydzien_psi(cron) == date(2026, 10, 5)
    assert inngest_app.tydzien_psi(reczne) == date(2026, 10, 12)
    assert inngest_app.CRON_LISTA == "TZ=Europe/Warsaw 0 6 * * 1"
    assert inngest_app.kawosz_lista_wizyt in inngest_app.FUNKCJE
