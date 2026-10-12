"""Katalog cech: każda cecha z sql/ ma kompletną kartę w katalog.yaml i odwrotnie, a modele cechy są wyliczane
z wersji w ai/churn_model/versions/, nie wpisywane ręcznie."""

import json
import os
import re
from pathlib import Path

import duckdb
import pytest
import yaml
from fastapi.testclient import TestClient

from api.ai.churn_model import psi as psi_cech
from api.ai.features import katalog
from api.ai.features.build import KATALOG_SQL, KLUCZ, RODZINY
from tests.ai.features.test_build import T0, con, zaloz_baze  # noqa: F401 (fikstura)

# Klient Inngest (api/inngest_app.py) powstaje przy imporcie api.main: w testach w trybie deweloperskim.
os.environ.setdefault("INNGEST_DEV", "1")

KARTA = {
    "opis": "Ile kaw zaparzyło biuro.",
    "sql": "sql/uzycie.sql",
    "zrodlo": {"system": "IoT", "tabele": ["iot_telemetria"]},
    "okno": "od t0 − 32 do t0 − 3",
    "opoznienie": "2 dni",
    "wlasciciel": "Zespół danych",
    "wersja": "1.0.0",
}


def _bez_komentarzy(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def test_kazda_cecha_z_sql_ma_karte_i_kazda_karta_ma_ceche_w_sql(con):  # noqa: F811
    karty = katalog.wczytaj()  # niekompletna karta przerywa z listą błędów

    assert {p.stem for p in KATALOG_SQL.glob("*.sql")} == set(RODZINY)
    for rodzina in RODZINY:
        kolumny = con.execute((KATALOG_SQL / f"{rodzina}.sql").read_text(), {"t0": T0}).df().columns
        # ta sama kolejność: v3_katalog bierze z katalogu kolejność wejść modelu
        assert [k for k in kolumny if k not in KLUCZ] == [k.cecha for k in karty if k.rodzina == rodzina], rodzina


def test_tabele_ze_zrodla_karty_czyta_jej_plik_sql():
    for karta in katalog.wczytaj():
        sql = _bez_komentarzy((KATALOG_SQL.parent / karta.sql).read_text())
        for tabela in karta.tabele:
            assert re.search(rf"\b(FROM|JOIN)\s+{tabela}\b", sql), f"{karta.cecha}: {karta.sql} nie czyta {tabela}"


@pytest.mark.parametrize(
    "zmiana, blad",
    [
        ({"wlasciciel": None}, "brak pola wlasciciel"),
        ({"okno": "  "}, "puste pole okno"),
        ({"autor": "ktoś"}, "nieznane pole autor"),
        ({"wersja": "1.0"}, "wersja '1.0'"),
        ({"sql": "sql/umowa.sql"}, "jest w rodzinie uzycie"),
        ({"zrodlo": {"system": "IoT"}}, "zrodlo musi mieć"),
        ({"zrodlo": {"system": "IoT", "tabele": []}}, "zrodlo.tabele"),
    ],
)
def test_niekompletna_karta_daje_blad(zmiana, blad):
    karta = {k: v for k, v in (KARTA | zmiana).items() if v is not None}

    assert katalog.bledy_karty("uzycie", "zaparzenia_30d", KARTA) == []
    assert any(blad in b for b in katalog.bledy_karty("uzycie", "zaparzenia_30d", karta))


def test_modele_cechy_to_wersje_z_katalogu_a_nie_te_o_tych_samych_nazwach_cech():
    karty = katalog.wczytaj()
    wersje = {w["wersja"]: w for w in katalog.wersje_modeli()}

    modele = katalog.modele_cech(karty, list(wersje.values()))

    meta_v3 = json.loads((katalog.WERSJE_MODELI / "v3_katalog" / "artefakty" / "meta.json").read_text())
    assert all(modele[c] == ["v3_katalog"] for c in meta_v3["cechy"])
    # v2 ma te same nazwy cech, ale liczy je cechy_snapszotu.sql, więc nie jest modelem tych kart
    assert set(wersje["v2_bez_przeciekow"]["cechy"]) & {k.cecha for k in karty}
    assert {w for w, d in wersje.items() if d["z_katalogu"]} == {"v3_katalog"}


@pytest.mark.parametrize(
    "importy, z_katalogu",
    [
        ("from api.ai.features.build import RODZINY", True),
        ("from api.ai.features import build", True),
        ("import api.ai.features.build", True),
        ("from api.ai.features.cechy import cechy_snapszotu", False),
        ("from api.ai.features import kodowanie_celu", False),
    ],
)
def test_wersja_korzysta_z_katalogu_gdy_model_importuje_build(tmp_path, importy, z_katalogu):
    wersja = _wersja(tmp_path, "v9_proba", importy, ["plan"])

    assert katalog.wersje_modeli(tmp_path) == [{"wersja": "v9_proba", "cechy": ["plan"], "z_katalogu": z_katalogu}]
    assert wersja.exists()


def test_cecha_wersji_z_katalogu_bez_karty_przerywa(tmp_path):
    _wersja(tmp_path, "v9_proba", "from api.ai.features.build import RODZINY", ["plan", "nowa_cecha"])

    with pytest.raises(ValueError, match="nowa_cecha"):
        katalog.modele_cech(katalog.wczytaj(), katalog.wersje_modeli(tmp_path))


def _wersja(katalog_wersji: Path, nazwa: str, importy: str, cechy: list[str]) -> Path:
    folder = katalog_wersji / nazwa
    (folder / "artefakty").mkdir(parents=True)
    (folder / "model.py").write_text(f'"""Wersja próbna."""\n\n{importy}\n')
    (folder / "artefakty" / "meta.json").write_text(json.dumps({"wersja": nazwa, "cechy": cechy}))
    return folder


@pytest.fixture
def klient():
    from api.main import app

    return TestClient(app)


def test_api_katalogu_daje_karty_z_modelami_i_ostatnim_psi(tmp_path, klient, monkeypatch):
    baza = tmp_path / "kawosz.duckdb"
    con = duckdb.connect(str(baza))
    con.execute(f"""
        CREATE TABLE {psi_cech.TABELA_PSI} AS SELECT * FROM (VALUES
            (DATE '2026-09-21', 'plan', 0.01, 4, 1400, 21827, FALSE, TIMESTAMP '2026-09-21 05:00:00'),
            (DATE '2026-09-28', 'plan', 0.30, 4, 1400, 21827, TRUE, TIMESTAMP '2026-09-28 05:00:00'))
            t(t0, cecha, psi, przedzialy, wiersze_tydzien, wiersze_trening, alert, zapisano)
    """)
    con.close()
    monkeypatch.setenv("KAWOSZ_BAZA", str(baza))

    dane = klient.get("/api/katalog").json()

    karty = {k["cecha"]: k for k in dane["karty"]}
    assert list(karty) == [c for r in RODZINY for c in yaml.safe_load(katalog.PLIK.read_text())[r]]
    assert karty["plan"]["psi"] == {"t0": "2026-09-28", "psi": 0.3, "alert": True, "alerty": 1, "tygodnie": 2}
    assert karty["miasto"]["psi"] is None and karty["plan"]["modele"] == ["v3_katalog"]
    assert dane["psi_t0"] == "2026-09-28" and dane["psi_prog"] == psi_cech.PROG
    assert {k: karty["plan"][k] for k in ("sql", "system", "tabele", "wlasciciel", "wersja")} == {
        "sql": "sql/umowa.sql", "system": "CRM", "tabele": ["crm_umowy_historia"], "wlasciciel": "Zespół danych",
        "wersja": "1.0.0",
    }


def test_api_katalogu_bez_tabeli_psi_daje_karty_bez_psi(tmp_path, klient, monkeypatch):
    baza = tmp_path / "kawosz.duckdb"
    zaloz_baze(duckdb.connect(str(baza)))
    monkeypatch.setenv("KAWOSZ_BAZA", str(baza))

    dane = klient.get("/api/katalog").json()

    assert dane["psi_t0"] is None and all(k["psi"] is None for k in dane["karty"])
