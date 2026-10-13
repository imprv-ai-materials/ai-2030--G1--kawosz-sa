"""Kalkulator wizyt: próg C / (s × V), lista biur do odwiedzenia w budżecie, zysk według modelu i na historii,
krzywa wartości, suwaki z zalozenia.yaml."""

import os

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.contexts_boundaries.retention_bc import kontrola as los_kontroli
from api.contexts_boundaries.retention_bc.prog import kalkulator
from api.contexts_boundaries.retention_bc.prog.kalkulator import policz, przedzial_s, suwaki
from api.contexts_boundaries.retention_bc.prog.krzywa_wartosci import zalozenia

# Klient Inngest (api/inngest_app.py) powstaje przy imporcie api.main: w testach w trybie deweloperskim.
os.environ.setdefault("INNGEST_DEV", "1")

# C / (s × V) = 1 000 / (0,5 × 10 000) = 0,2; trafiona wizyta daje 4 000 zł, zbędna kosztuje 1 000 zł
S, V, C = 0.5, 10_000, 1_000


@pytest.fixture
def dzis() -> pd.DataFrame:
    """Dzisiejsze biura bez etykiet: cztery z p ≥ 0,2."""
    return pd.DataFrame({
        "id_biura": [1, 2, 3, 4, 5, 6],
        "nazwa": list("abcdef"),
        "miasto": ["Poznań"] * 6,
        "opiekun": ["Ola"] * 6,
        "p": [0.3, 0.9, 0.2, 0.5, 0.1, 0.05],
        "powody": [["3 awarie w 60 dni"], ["NPS 2/10", "pakiet S"], [], [], [], []],
    })


@pytest.fixture
def historia() -> pd.DataFrame:
    """Dwa snapszoty po trzy biura z faktycznymi odejściami."""
    return pd.DataFrame({
        "t0": ["2026-01-01"] * 3 + ["2026-02-01"] * 3,
        "odejdzie_90d": [1, 0, 0, 0, 1, 0],
        "p": [0.6, 0.3, 0.1, 0.4, 0.25, 0.15],
    })


def test_prog_to_C_przez_s_razy_V(dzis, historia):
    w = policz(dzis, historia, S, V, C, budzet=60)
    assert w["prog"] == pytest.approx(0.2)
    assert w["zysk_trafionej"] == 4_000


def test_lista_to_biura_z_p_od_progu_od_najwyzszego_p(dzis, historia):
    w = policz(dzis, historia, S, V, C, budzet=60)
    assert [b["id_biura"] for b in w["lista"]] == [2, 4, 1, 3]
    assert w["nad_progiem"] == 4
    assert w["lista"][0]["wartosc_wizyty"] == pytest.approx(0.9 * 5_000 - 1_000)


def test_biura_na_liscie_maja_powody_ryzyka(dzis, historia):
    w = policz(dzis, historia, S, V, C, budzet=60)
    assert {b["id_biura"]: b["powody"] for b in w["lista"]}[2] == ["NPS 2/10", "pakiet S"]


def test_budzet_przycina_liste_do_biur_z_najwyzszym_p(dzis, historia):
    w = policz(dzis, historia, S, V, C, budzet=2)
    assert [b["id_biura"] for b in w["lista"]] == [2, 4]
    assert w["nad_progiem"] == 4
    assert w["zysk_oczekiwany_nad_progiem"] == pytest.approx((0.9 + 0.5 + 0.3 + 0.2) * 5_000 - 4 * 1_000)
    assert w["max_p"] == 0.9


def test_zysk_oczekiwany_to_suma_p_s_V_minus_C_po_liscie(dzis, historia):
    w = policz(dzis, historia, S, V, C, budzet=2)
    assert w["zysk_oczekiwany"] == pytest.approx((0.9 + 0.5) * 5_000 - 2 * 1_000)


def test_historia_usrednia_regule_progu_po_snapszotach(dzis, historia):
    # 2026-01: p ≥ 0,2 to 0,6 (odeszło) i 0,3: 4 000 − 1 000; 2026-02: 0,4 i 0,25 (odeszło): −1 000 + 4 000
    w = policz(dzis, historia, S, V, C, budzet=60)
    assert w["historia"] == {"snapszoty": 2, "od": "2026-01-01", "do": "2026-02-01", "wizyty": 2, "zysk": 3_000}


def test_historia_tez_trzyma_sie_budzetu(dzis, historia):
    # budżet 1: 2026-01 tylko 0,6 (odeszło): 4 000; 2026-02 tylko 0,4: −1 000
    assert policz(dzis, historia, S, V, C, budzet=1)["historia"]["zysk"] == 1_500


def test_krzywa_ma_zysk_oczekiwany_dzis_i_sredni_zysk_na_historii(dzis, historia):
    k = {w["prog"]: w for w in policz(dzis, historia, S, V, C, budzet=60)["krzywa"]}
    assert len(k) == 99
    assert k[0.5]["wizyty_dzis"] == 2
    assert k[0.5]["zysk_oczekiwany_dzis"] == pytest.approx((0.9 + 0.5) * 5_000 - 2 * 1_000)
    # 2026-01: tylko 0,6 (odeszło) → 4 000; 2026-02: nikt → 0
    assert (k[0.5]["wizyty_historia"], k[0.5]["zysk_historia"]) == (0.5, 2_000)


def test_prog_ponad_najwyzsze_p_daje_pusta_liste_i_zero(dzis, historia):
    w = policz(dzis, historia, 0.05, V, C, budzet=60)  # próg 2,0
    assert (w["lista"], w["nad_progiem"], w["zysk_oczekiwany"], w["historia"]["zysk"]) == ([], 0, 0, 0)


def test_bez_kontroli_wszystkie_biura_z_listy_dostaja_wizyte(dzis, historia):
    w = policz(dzis, historia, S, V, C, budzet=60)
    assert {b["grupa"] for b in w["lista"]} == {"wizyta"}
    assert (w["kontrola"]["biura"], w["kontrola"]["koszt"]) == (0, 0)


def kwartal_z_obiema_grupami(ids: list[int], udzial: float) -> str:
    """Kwartał, w którym los daje na liście biura i w kontroli, i z wizytą (żeby test coś sprawdzał)."""
    for r in range(2026, 2040):
        for q in range(1, 5):
            w = [los_kontroli.w_kontroli(b, f"{r}-Q{q}", udzial) for b in ids]
            if 0 < sum(w) < len(w):
                return f"{r}-Q{q}"
    raise AssertionError("brak takiego kwartału")


def test_w_kontroli_sa_biura_z_listy_z_losem_ponizej_udzialu(dzis, historia):
    kw = kwartal_z_obiema_grupami([2, 4, 1, 3], 0.5)
    w = policz(dzis, historia, S, V, C, budzet=60, kontrola=0.5, kwartal=kw)
    for b in w["lista"]:
        assert (b["grupa"] == "kontrola") == los_kontroli.w_kontroli(b["id_biura"], kw, 0.5)
    assert w["kontrola"]["biura"] == sum(b["grupa"] == "kontrola" for b in w["lista"])


def test_przydzial_do_kontroli_jest_powtarzalny_w_kwartale(dzis, historia):
    def kontrola(kwartal):
        w = policz(dzis, historia, S, V, C, budzet=60, kontrola=0.5, kwartal=kwartal)
        return [b["id_biura"] for b in w["lista"] if b["grupa"] == "kontrola"]

    assert kontrola("2026-Q4") == kontrola("2026-Q4")
    assert {tuple(kontrola(f"20{r}-Q{q}")) for r in range(26, 30) for q in range(1, 5)} != {tuple(kontrola("2026-Q4"))}


def test_zysk_liczy_tylko_wizyty_a_kontrola_kosztuje_ich_utracona_wartosc(dzis, historia):
    kw = kwartal_z_obiema_grupami([2, 4, 1, 3], 0.5)
    w = policz(dzis, historia, S, V, C, budzet=60, kontrola=0.5, kwartal=kw)
    wartosc = {"wizyta": 0.0, "kontrola": 0.0}
    for b in w["lista"]:
        wartosc[b["grupa"]] += b["wartosc_wizyty"]
    assert w["zysk_oczekiwany"] == pytest.approx(wartosc["wizyta"])
    assert w["kontrola"]["koszt"] == pytest.approx(wartosc["kontrola"])


def test_odsetek_odejsc_bez_wizyty_to_odejscia_na_liscie_w_historii(dzis, historia):
    # historia, p ≥ 0,2: odeszły 2 z 4 biur
    k = policz(dzis, historia, S, V, C, budzet=60, kontrola=0.5, kwartal="2026-Q4")["kontrola"]
    assert k["odejscia_bez_wizyty"] == 0.5


def test_dokladnosc_pomiaru_s_metoda_delta():
    # r_C = 0,5, z wizytą r_T = 0,5 × (1 − s) = 0,25; 2 + 2 biura na kwartał:
    # wariancja s = (0,25 / 0,5)² × (0,5 / (2 × 0,5) + 0,75 / (2 × 0,25)) = 0,5
    p = przedzial_s(0.5, S, 2, 2)
    assert p["1"] == pytest.approx(1.645 * 0.5**0.5, rel=1e-3)
    assert p["4"] == pytest.approx(1.645 * (0.5 / 4) ** 0.5, rel=1e-3)
    assert przedzial_s(0.5, S, 0, 4) is None


def test_suwaki_startuja_z_zalozen_i_obejmuja_przedzial():
    z, s = zalozenia(), {w["klucz"]: w for w in suwaki()}
    assert list(s) == ["V", "C", "s", "budzet_wizyt"]
    for klucz, w in s.items():
        assert w["wartosc"] == z[klucz]
        assert w["min"] <= w["wartosc"] <= w["max"]
        if w["przedzial"]:
            assert w["min"] <= w["przedzial"][0] and w["przedzial"][1] <= w["max"]
    assert s["s"]["min"] > 0 and s["s"]["max"] <= 1


@pytest.fixture
def klient(dzis, historia, monkeypatch, tmp_path):
    """API z biurami z fixture zamiast bazy i modelu."""
    baza = tmp_path / "kawosz.duckdb"
    baza.touch()
    monkeypatch.setenv("KAWOSZ_BAZA", str(baza))
    monkeypatch.setattr(kalkulator, "DB_PATH", baza)
    monkeypatch.setattr(kalkulator, "_wczytaj", lambda *_: (dzis.assign(t0=pd.Timestamp("2026-10-01")), historia))
    from api.main import app

    return TestClient(app)


def test_api_bez_parametrow_liczy_na_zalozeniach(klient):
    z = zalozenia()
    w = klient.get("/api/wizyty").json()
    assert w["zalozenia"] == {"s": z["s"], "V": z["V"], "C": z["C"], "budzet_wizyt": z["budzet_wizyt"]}
    assert w["dzis"] == "2026-10-01" and len(w["suwaki"]) == 4


def test_api_liczy_na_parametrach_z_suwakow(klient):
    w = klient.get("/api/wizyty", params={"s": S, "V": V, "C": C, "budzet": 2}).json()
    assert w["prog"] == pytest.approx(0.2)
    assert [b["id_biura"] for b in w["lista"]] == [2, 4]


def test_api_przekazuje_udzial_kontroli_i_kwartal_z_dnia_listy(klient):
    w = klient.get("/api/wizyty", params={"s": S, "V": V, "C": C, "kontrola": 0.5}).json()
    assert w["kontrola"]["kwartal"] == "2026-Q4"
    assert [b["grupa"] == "kontrola" for b in w["lista"]] == [
        los_kontroli.w_kontroli(b["id_biura"], "2026-Q4", 0.5) for b in w["lista"]
    ]


def test_api_odrzuca_kontrole_ponad_polowe(klient):
    assert klient.get("/api/wizyty", params={"kontrola": 0.6}).status_code == 422


def test_api_odrzuca_zerowa_skutecznosc(klient):
    assert klient.get("/api/wizyty", params={"s": 0}).status_code == 422
