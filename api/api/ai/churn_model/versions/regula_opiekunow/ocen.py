"""Ocena reguły opiekunów na zbiorze testowym agencji (ten sam podział co v0_agencja, zbior_agencji.py).

Cechy reguły liczy cechy.sql z iot_telemetria i crm_biura na stan z dnia snapszotu, a nie bierze ich z tabeli
agencji. Wynik trafia do artefakty/ocena.json i do MLflow (eksperyment churn, run regula_opiekunow). Wymaga
serwera: poetry run pypyr start_mlflow.

    PYTHONPATH=api poetry run python -m api.ai.churn_model.versions.regula_opiekunow.ocen
"""

import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import roc_auc_score

from api.adapters.duckdb_conn import connect
from api.ai.churn_model.rejestr import loguj_wersje, waznosc_permutacyjna, wykres_waznosci
from api.ai.churn_model.versions.regula_opiekunow.model import DNI_DO_KONCA, SPADEK, RegulaOpiekunow
from api.ai.churn_model.zbior_agencji import SPOSOB_OCENY, ZIARNO, dane, podzial

KATALOG = Path(__file__).parent
WERSJA = KATALOG.name
ARTEFAKTY = KATALOG / "artefakty"


def cechy() -> pd.DataFrame:
    con = connect(read_only=True)
    try:
        return con.sql((KATALOG / "cechy.sql").read_text()).df()
    finally:
        con.close()


def main() -> None:
    _, testowy = podzial(dane())
    klucz = testowy[["id_biura", "data_migawki", "odejdzie_90d"]].rename(columns={"data_migawki": "data_snapszotu"})
    X = klucz.merge(cechy(), on=["id_biura", "data_snapszotu"], how="left", validate="one_to_one")
    assert X[RegulaOpiekunow.cechy].notna().all().all(), "brak cech reguły dla części wierszy testowych"
    y = X["odejdzie_90d"]

    model = RegulaOpiekunow()
    assert model.wersja == WERSJA, "wersja modelu musi się nazywać jak folder w versions/"
    model.save(ARTEFAKTY)
    oznaczone = model.predict_proba(X) == 1
    trafione = int((oznaczone & (y == 1)).sum())
    sposob_oceny = SPOSOB_OCENY + "; ocena tylko na części testowej, reguła się nie uczy"
    ocena = {
        "wersja": model.wersja,
        "sposob_oceny": sposob_oceny,
        "wiersze_testowe": len(X),
        "jedynki_testowe": int(y.sum()),
        "auc": round(float(roc_auc_score(y, oznaczone.astype(float))), 4),
        "oznaczone": int(oznaczone.sum()),
        "trafione": trafione,
        "precyzja": round(trafione / int(oznaczone.sum()), 4),
        "czulosc": round(trafione / int(y.sum()), 4),
    }
    (ARTEFAKTY / "ocena.json").write_text(json.dumps(ocena, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(ocena, ensure_ascii=False, indent=2))

    parametry = {
        "zbior": "agencja_features ⋈ snapshoty (tylko klucze i etykieta); cechy z cechy.sql",
        "podzial_seed": ZIARNO,
        "podzial_test": 0.2,
        "wiersze_testowe": len(X),
        "liczba_cech": len(model.cechy),
        "dni_do_konca": DNI_DO_KONCA,
        "spadek": SPADEK,
        "okno_30d": "[d-32, d-3]",
        "okno_90d": "[d-92, d-3]",
        "opoznienie_telemetrii_dni": 2,
    }
    metryki = {k: float(ocena[k]) for k in ("auc", "precyzja", "czulosc", "oznaczone", "trafione")}
    waznosc = waznosc_permutacyjna(model, X, y, ziarno=ZIARNO)
    wykres = wykres_waznosci(
        waznosc,
        tytul=f"{WERSJA}: ważność cech (permutacyjna, 10 powtórzeń)",
        os_x="średni spadek AUC po przemieszaniu cechy",
        format_wartosci="{:.3f}",
    )
    run_id = loguj_wersje(
        WERSJA,
        sposob_oceny,
        parametry,
        metryki,
        wykres,
        ARTEFAKTY,
        opis="Punkt odniesienia: reguła opiekunów (koniec umowy w 90 dni i spadek zaparzeń o ponad 30%). "
        "Szczegóły: evals/regula_opiekunow.md.",
    )
    print(f"MLflow: run {run_id}")


if __name__ == "__main__":
    main()
