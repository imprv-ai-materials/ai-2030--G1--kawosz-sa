"""Reguła opiekunów: progi reguły i cechy liczone na stan z dnia snapszotu (koniec okresu, opóźnienie telemetrii)."""

from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from api.ai.churn_model.base import ChurnModel
from api.ai.churn_model.versions.regula_opiekunow import RegulaOpiekunow

CECHY_SQL = Path(__file__).parents[3] / "api/ai/churn_model/versions/regula_opiekunow/cechy.sql"


def test_regula_wymaga_obu_warunkow():
    X = pd.DataFrame(
        {
            "dni_do_konca_okresu": [10, 10, 200, 89, 90],
            "zaparzenia_30d_iot": [60, 80, 10, 69, 10],
            "zaparzenia_90d_iot": [300, 300, 300, 300, 300],  # średnia 30-dniowa = 100
        },
        index=[7, 8, 9, 10, 11],
    )

    p = RegulaOpiekunow().fit(X, pd.Series(0, index=X.index)).predict_proba(X)

    assert isinstance(RegulaOpiekunow(), ChurnModel)
    # spadek 40% i koniec za 10 dni | spadek 20% | koniec za 200 dni | spadek 31%, koniec za 89 dni | koniec za 90 dni
    assert p.to_dict() == {7: 1.0, 8: 0.0, 9: 0.0, 10: 1.0, 11: 0.0}


def test_spadek_dokladnie_30_procent_nie_wystarcza():
    X = pd.DataFrame({"dni_do_konca_okresu": [10], "zaparzenia_30d_iot": [70], "zaparzenia_90d_iot": [300]})

    assert RegulaOpiekunow().predict_proba(X).iloc[0] == 0.0


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE crm_biura (id_biura BIGINT, data_startu DATE, data_konca_umowy DATE);
        -- data_konca_umowy z dnia eksportu (po odnowieniach) nie może wpływać na cechy
        INSERT INTO crm_biura VALUES
            (1, DATE '2020-03-15', DATE '2027-03-14'),
            (2, DATE '2016-02-29', DATE '2027-02-27');
        CREATE TABLE snapshoty (data_snapszotu DATE, id_biura BIGINT, odejdzie_90d INTEGER);
        INSERT INTO snapshoty VALUES (DATE '2024-03-01', 1, 0), (DATE '2024-04-01', 1, 0), (DATE '2025-02-01', 2, 0);
        CREATE TABLE iot_ekspresy (id_ekspresu VARCHAR, id_biura BIGINT);
        INSERT INTO iot_ekspresy VALUES ('A', 1), ('B', 1);
        CREATE TABLE iot_telemetria (id_ekspresu VARCHAR, data DATE, zaparzenia BIGINT, data_dostarczenia DATE);
    """)
    return con


def _telemetria(con, ekspres: str, dzien: date, zaparzenia: int):
    con.execute(
        "INSERT INTO iot_telemetria VALUES (?, ?, ?, ?)", [ekspres, dzien, zaparzenia, dzien + timedelta(days=2)]
    )


def _cechy(con) -> pd.DataFrame:
    df = con.sql(CECHY_SQL.read_text()).df()
    df["data_snapszotu"] = pd.to_datetime(df["data_snapszotu"]).dt.date
    return df.set_index(["id_biura", "data_snapszotu"])


def test_koniec_okresu_z_rocznicy_a_nie_z_dnia_eksportu(con):
    c = _cechy(con)

    assert c.loc[(1, date(2024, 3, 1)), "dni_do_konca_okresu"] == 13  # okres kończy się 2024-03-14
    assert c.loc[(1, date(2024, 4, 1)), "dni_do_konca_okresu"] == 347  # po rocznicy: koniec 2025-03-14
    assert c.loc[(2, date(2025, 2, 1)), "dni_do_konca_okresu"] == 26  # start 29.02: rocznica 2025-02-28, koniec 27.02


def test_okna_telemetrii_tylko_z_dostarczonych_dni(con):
    d = date(2024, 4, 1)
    _telemetria(con, "A", d - timedelta(days=2), 1000)  # dostarczone w dniu d: jeszcze nieznane
    _telemetria(con, "A", d - timedelta(days=3), 1)  # ostatni znany dzień
    _telemetria(con, "B", d - timedelta(days=32), 10)  # początek okna 30 dni, drugi ekspres biura
    _telemetria(con, "A", d - timedelta(days=33), 100)  # tylko w oknie 90 dni
    _telemetria(con, "A", d - timedelta(days=92), 1000)  # początek okna 90 dni
    _telemetria(con, "A", d - timedelta(days=93), 10000)  # poza oknem 90 dni

    w = _cechy(con).loc[(1, d)]

    assert w["zaparzenia_30d_iot"] == 11
    assert w["zaparzenia_90d_iot"] == 1111


def test_biuro_bez_telemetrii_ma_zera(con):
    w = _cechy(con).loc[(2, date(2025, 2, 1))]

    assert (w["zaparzenia_30d_iot"], w["zaparzenia_90d_iot"]) == (0, 0)
