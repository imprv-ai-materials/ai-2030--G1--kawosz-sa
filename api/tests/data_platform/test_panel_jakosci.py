"""Panel jakości: API pokazuje to, co zapisała noc (status, wycena, wynik każdej reguły), i jasno mówi, gdy nocy
jeszcze nie było."""

import pytest
from fastapi.testclient import TestClient

from api import inngest_app
from api.data_platform import noc, panel_jakosci
from tests.data_platform.conftest import DZIEN
from tests.data_platform.test_noc import PLIK_Z_KASY, ust  # noqa: F401 (fikstura)


@pytest.fixture
def klient():
    from api.main import app  # INNGEST_DEV=1 ustawia conftest.py

    return TestClient(app)


def test_panel_pokazuje_wsady_wyniki_regul_i_most_po_nocy(ust):  # noqa: F811
    kopia = ust.dostawy / str(DZIEN) / "pos" / f"pos_paragony_1_{DZIEN} (1).csv"
    kopia.write_bytes((ust.dostawy / str(DZIEN) / "pos" / PLIK_Z_KASY).read_bytes())
    inngest_app.przebieg(DZIEN, ust)

    dane = panel_jakosci.dane(ust.baza, dni=30)

    assert (dane["od"], dane["do"]) == (DZIEN.replace(day=1), DZIEN)
    wsady = {w["zrodlo"]: w for w in dane["wsady"]}
    assert wsady["pos"]["status"] == "kwarantanna" and "POS-02" in wsady["pos"]["blokujace"]
    assert wsady["pos"]["zawyzenie"] == 150.36 and wsady["erp"]["status"] == "opublikowany"
    assert len(dane["naruszenia"]) == sum(len(r) for r in noc.REGULY.values())
    assert {r["id"] for r in dane["reguly"]} >= {"POS-02", "ERP-06", "ECOM-05"}
    assert all(r["co_zrobic"] for r in dane["reguly"])
    assert {k["krok"] for k in dane["most"]} >= {"0. Surowa suma BI", "Przychód netto", "Niewyjaśniona reszta"}


def test_api_bez_nocy_odpowiada_404_z_wyjasnieniem(ust, klient, monkeypatch):  # noqa: F811
    monkeypatch.setenv("KAWOSZ_BAZA", str(ust.baza))

    odpowiedz = klient.get("/api/jakosc")

    assert odpowiedz.status_code == 404
    assert "Nocny potok jeszcze nie działał" in odpowiedz.json()["detail"]


def test_api_po_nocy_zwraca_dane_panelu(ust, klient, monkeypatch):  # noqa: F811
    inngest_app.przebieg(DZIEN, ust)
    monkeypatch.setenv("KAWOSZ_BAZA", str(ust.baza))

    odpowiedz = klient.get("/api/jakosc?dni=7")

    assert odpowiedz.status_code == 200
    assert odpowiedz.json()["dni"] == 7 and len(odpowiedz.json()["wsady"]) == 3
