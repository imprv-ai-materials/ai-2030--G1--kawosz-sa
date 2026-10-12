"""GET /api/biura/{id}/cechy: cechy jednego biura liczone tym samym kodem co trening, więc równe wierszowi
cechy_aktualne (domyślne t0 = DZIS) albo cechy_treningowe bez etykiety (t0 z przeszłości)."""

import os
from datetime import date

import duckdb
import pytest
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient

from api.ai.features import build
from tests.ai.features.test_build import T0, T1, zaloz_baze

# Klient Inngest (api/inngest_app.py) powstaje przy imporcie api.main: w testach w trybie deweloperskim.
os.environ.setdefault("INNGEST_DEV", "1")

DZIS = date(2025, 5, 12)  # w bazie testowej umowy kończą się w 2025–2026, więc „dziś” musi być wcześniej


@pytest.fixture
def baza(tmp_path, monkeypatch):
    """Plik bazy z cechy_treningowe na T0 i T1 i cechy_aktualne na DZIS, jak po treningu i nocy."""
    sciezka = tmp_path / "kawosz.duckdb"
    con = duckdb.connect(str(sciezka))
    zaloz_baze(con)
    build.zbuduj_cechy_treningowe([T0, T1], con)
    build.zbuduj_cechy_aktualne(DZIS, con)
    con.close()
    monkeypatch.setenv("KAWOSZ_BAZA", str(sciezka))
    monkeypatch.setattr(build, "DZIS", DZIS)
    return sciezka


@pytest.fixture
def klient():
    from api.main import app

    return TestClient(app)


def _wiersze(sciezka, sql: str, params: list | None = None) -> dict[int, dict]:
    """Wiersze tabeli cech jak w JSON odpowiedzi API, po id_biura."""
    con = duckdb.connect(str(sciezka), read_only=True)
    try:
        rel = con.execute(sql, params or [])
        kolumny = [k[0] for k in rel.description]
        return {w[0]: jsonable_encoder(dict(zip(kolumny, w))) for w in rel.fetchall()}
    finally:
        con.close()


def test_domyslnie_zwraca_wiersz_cech_aktualnych(baza, klient):
    aktualne = _wiersze(baza, "SELECT * FROM cechy_aktualne")

    assert list(aktualne) == [1]
    for id_biura, wiersz in aktualne.items():
        odpowiedz = klient.get(f"/api/biura/{id_biura}/cechy")
        assert odpowiedz.status_code == 200
        assert odpowiedz.json() == wiersz


@pytest.mark.parametrize("t0", [T0, T1])
def test_dla_daty_z_przeszlosci_zwraca_wiersz_cech_treningowych_bez_etykiety(baza, klient, t0):
    treningowe = _wiersze(baza, "SELECT * EXCLUDE (odejdzie_90d) FROM cechy_treningowe WHERE t0 = ?", [t0])

    assert treningowe
    for id_biura, wiersz in treningowe.items():
        odpowiedz = klient.get(f"/api/biura/{id_biura}/cechy", params={"t0": str(t0)})
        assert odpowiedz.status_code == 200
        assert odpowiedz.json() == wiersz


@pytest.mark.parametrize("id_biura", [2, 999])  # 2: wypowiedzenie przed T0, 999: nie ma takiego biura
def test_biuro_spoza_populacji_w_t0_to_404(baza, klient, id_biura):
    odpowiedz = klient.get(f"/api/biura/{id_biura}/cechy", params={"t0": str(T0)})

    assert odpowiedz.status_code == 404
    assert "aktywnej umowy" in odpowiedz.json()["detail"]


def test_t0_po_dniu_dzis_to_422(baza, klient):
    odpowiedz = klient.get("/api/biura/1/cechy", params={"t0": "2025-05-13"})

    assert odpowiedz.status_code == 422
    assert "po dniu dzisiejszym" in odpowiedz.json()["detail"]
