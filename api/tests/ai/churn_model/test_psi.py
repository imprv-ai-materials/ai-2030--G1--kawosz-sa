"""PSI cech: przedziały z treningu, wzór, zapis w psi_cech i alerty_psi z wykresem, powtórzenie tygodnia."""

import os
from datetime import date, datetime

import duckdb
import inngest
import numpy as np
import pandas as pd
import pytest

from api.ai.churn_model import psi
from api.ai.features import build
from api.data_platform import noc
from tests.ai.features.test_build import T0, T1, zaloz_baze

# Klient Inngest (api/inngest_app.py) powstaje przy imporcie: w testach w trybie deweloperskim.
os.environ.setdefault("INNGEST_DEV", "1")

from api import inngest_app  # noqa: E402


def test_psi_tego_samego_rozkladu_to_zero_a_przesuniecia_zgodny_ze_wzorem():
    przed = pd.Series([0.5, 0.5, 0.0])
    po = pd.Series([0.2, 0.8, 0.0])

    assert psi.psi(przed, przed) == 0
    assert psi.psi(przed, po) == pytest.approx((0.2 - 0.5) * np.log(0.2 / 0.5) + (0.8 - 0.5) * np.log(0.8 / 0.5))


def test_pusty_przedzial_nie_daje_nieskonczonosci():
    assert np.isfinite(psi.psi(pd.Series([1.0, 0.0]), pd.Series([0.0, 1.0])))


def test_cecha_liczbowa_ma_10_przedzialow_decyli_treningu_i_przedzial_brak():
    trening = pd.Series(range(1, 101), name="zaparzenia_30d", dtype=float)
    przedzialy = psi.przedzialy_z_treningu(trening)

    assert len(przedzialy.etykiety()) == 10 + 1 and przedzialy.etykiety()[-1] == psi.BRAK
    assert przedzialy.udzialy(trening).tolist() == pytest.approx([0.1] * 10 + [0.0])
    # (a, b] zawiera prawą granicę; wartości spoza zakresu treningu trafiają do skrajnych przedziałów
    tydzien = pd.Series([-5, przedzialy.granice[0], przedzialy.granice[0] + 0.01, 1000, None], dtype=float)
    assert przedzialy.przypisz(tydzien).tolist() == [
        przedzialy.etykiety()[0], przedzialy.etykiety()[0], przedzialy.etykiety()[1], przedzialy.etykiety()[9],
        psi.BRAK,
    ]


def test_powtorzone_decyle_lacza_przedzialy():
    trening = pd.Series([0] * 80 + [1] * 15 + [2] * 5, name="awarie_60d", dtype=float)

    przedzialy = psi.przedzialy_z_treningu(trening)

    assert przedzialy.granice == (0.0, 1.0)
    assert przedzialy.udzialy(trening).tolist() == pytest.approx([0.8, 0.15, 0.05, 0.0])


def test_cecha_kategoryczna_ma_9_najczestszych_kategorii_i_inne():
    trening = pd.Series([f"m{i:02d}" for i in range(12) for _ in range(12 - i)] + [None], name="miasto")

    przedzialy = psi.przedzialy_z_treningu(trening)

    assert przedzialy.etykiety() == [f"m{i:02d}" for i in range(9)] + [psi.INNE, psi.BRAK]
    assert przedzialy.przypisz(pd.Series(["m00", "m11", "nowe", None])).tolist() == ["m00", "inne", "inne", "brak"]


def test_zbior_uczacy_i_kategoryczne_jak_w_v3_katalog():
    from api.ai.churn_model.versions.v3_katalog import model, trenuj

    assert pd.Timestamp(psi.POCZATEK_UCZENIA) == trenuj.POCZATEK_UCZENIA
    assert pd.Timestamp(psi.POCZATEK_TESTU) == trenuj.POCZATEK_TESTU
    assert pd.Timedelta(psi.OKNO_ETYKIETY) == trenuj.OKNO_ETYKIETY
    assert psi.KATEGORYCZNE == model.KATEGORYCZNE


def test_poniedzialki():
    assert psi.poniedzialki(date(2026, 1, 1), date(2026, 1, 19)) == [date(2026, 1, 5), date(2026, 1, 12),
                                                                     date(2026, 1, 19)]
    assert psi.poniedzialki(date(2026, 1, 6), date(2026, 1, 11)) == []


TYDZIEN = date(2025, 5, 12)  # poniedziałek; biuro 1 w populacji, zbiór uczący: T0 i T1 (2025-04 i 2025-05)


@pytest.fixture
def ust(tmp_path, monkeypatch) -> noc.Ustawienia:
    """Baza z cechy_treningowe na T0 i T1; potem biuro 1 rośnie do 500 pracowników, więc w TYDZIEN
    liczba_pracownikow odjeżdża od treningu (tam 50 i 80)."""
    ust = noc.Ustawienia(baza=tmp_path / "kawosz.duckdb", wykresy_psi=tmp_path / "psi")
    con = duckdb.connect(str(ust.baza))
    zaloz_baze(con)
    build.zbuduj_cechy_treningowe([T0, T1], con)
    con.execute("UPDATE crm_biura SET liczba_pracownikow = 500 WHERE id_biura = 1")
    con.close()
    monkeypatch.setattr(build, "DZIS", date(2025, 6, 1))
    return ust


def _tabela(ust, sql):
    con = duckdb.connect(str(ust.baza), read_only=True)
    try:
        return con.sql(sql).fetchall()
    finally:
        con.close()


def test_psi_tygodnia_zapisuje_kazda_ceche_a_alert_z_wykresem(ust):
    wynik = inngest_app.przebieg_psi(TYDZIEN, ust)

    cechy = [c for (c,) in _tabela(ust, "SELECT cecha FROM psi_cech WHERE t0 = DATE '2025-05-12'")]
    treningowe = _tabela(ust, "SELECT column_name FROM duckdb_columns() WHERE table_name = 'cechy_treningowe'")
    assert cechy == [k for (k,) in treningowe if k not in build.KLUCZ + ["odejdzie_90d"]]
    alerty = dict(_tabela(ust, "SELECT cecha, wykres FROM alerty_psi"))
    assert "liczba_pracownikow" in alerty and alerty == wynik["alerty"]
    assert (ust.wykresy_psi / "2025-05-12_liczba_pracownikow.png").exists()
    assert alerty["liczba_pracownikow"] == str(ust.wykresy_psi / "2025-05-12_liczba_pracownikow.png")
    assert _tabela(ust, "SELECT bool_and(alert = (psi > 0.25)) FROM psi_cech") == [(True,)]
    assert _tabela(ust, "SELECT psi > 0.25 FROM psi_cech WHERE cecha = 'liczba_pracownikow'") == [(True,)]


def test_drugi_przebieg_tygodnia_zastepuje_zapis(ust):
    pierwszy = inngest_app.przebieg_psi(TYDZIEN, ust)
    przed = _tabela(ust, "SELECT * EXCLUDE (zapisano) FROM psi_cech ORDER BY cecha")

    drugi = inngest_app.przebieg_psi(TYDZIEN, ust)

    assert drugi == pierwszy
    assert _tabela(ust, "SELECT * EXCLUDE (zapisano) FROM psi_cech ORDER BY cecha") == przed
    assert _tabela(ust, "SELECT count(*) FROM alerty_psi") == [(len(pierwszy["alerty"]),)]


def test_t0_po_dniu_dzis_przerywa_bez_ponawiania(ust):
    with pytest.raises(inngest.NonRetriableError):
        inngest_app.przebieg_psi(date(2025, 6, 2), ust)


def test_t0_z_crona_to_dzien_uruchomienia_w_czasie_polskim_a_z_recznego_zdarzenia_t0_ze_zdarzenia():
    poniedzialek_5_rano = int(datetime.fromisoformat("2026-09-28T05:00:00+02:00").timestamp() * 1000)
    cron = inngest.Event(name="inngest/scheduled.timer", data={"cron": inngest_app.CRON_PSI}, ts=poniedzialek_5_rano)
    reczne = inngest.Event(name=inngest_app.ZDARZENIE_PSI, data={"t0": "2026-01-05"})

    assert inngest_app.tydzien_psi(cron) == date(2026, 9, 28)
    assert inngest_app.tydzien_psi(reczne) == date(2026, 1, 5)
