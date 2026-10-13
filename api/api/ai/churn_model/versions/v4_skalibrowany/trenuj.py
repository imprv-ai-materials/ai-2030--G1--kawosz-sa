"""Trening i ocena v4_skalibrowany na tym samym podziale w czasie co v3_katalog.

Zbiór uczący i testowy jak w v3 (podzial_czasowy): uczenie na t0 2024-04 – 2025-07, test na t0 2025-10 – 2026-04.
fit() dzieli zbiór uczący na model bazowy (t0 2024-04 – 2025-01) i walidację do kalibracji (t0 2025-05 – 2025-07).

Sprawdzamy, że kalibracja nie zmieniła kolejności biur: rangi wyników na teście przed i po kalibracji muszą być
identyczne, a więc i AUC. Liczymy Brier score (średni kwadrat pomyłki prognozy) względem stałej prognozy 3,5% dla
każdego biura. Model trafia do artefakty/, wynik do artefakty/ocena.json i do MLflow (eksperyment churn, run
v4_skalibrowany). Wymaga tabeli cechy_treningowe i serwera MLflow (poetry run pypyr start_mlflow).

    PYTHONPATH=api poetry run python -m api.ai.churn_model.versions.v4_skalibrowany.trenuj
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

from api.adapters.duckdb_conn import connect
from api.ai.churn_model.ocena_w_czasie import przedzial_bootstrap
from api.ai.churn_model.rejestr import loguj_wersje, wykres_waznosci
from api.ai.churn_model.versions.v3_katalog.model import ModelKatalog, waznosc_cech
from api.ai.churn_model.versions.v3_katalog.trenuj import ARTEFAKTY as ARTEFAKTY_V3
from api.ai.churn_model.versions.v3_katalog.trenuj import podzial_czasowy
from api.ai.churn_model.versions.v4_skalibrowany.model import MIESIACE_WALIDACJI, ModelSkalibrowany

WERSJA = Path(__file__).parent.name
ARTEFAKTY = Path(__file__).parent / "artefakty"
STALA = 0.035  # punkt odniesienia dla Briera: każde biuro 3,5% (odsetek odejść na teście, zaokrąglony)
SPOSOB_OCENY = (
    "podział w czasie jak w v3: test na t0 2025-10 – 2026-04, wszystkie miesięczne wiersze cechy_treningowe; "
    "model bazowy uczony na t0 2024-04 – 2025-01, kalibracja Platta na t0 2025-05 – 2025-07"
)


def kolejnosc_bez_zmian(przed: pd.Series, po: pd.Series) -> dict:
    """Czy kalibracja zachowała kolejność wierszy: rangi (remisy jako średnia) przed i po muszą być równe."""
    rangi_przed, rangi_po = przed.rank(), po.rank()
    zmienione = int((rangi_przed != rangi_po).sum())
    return {
        "wiersze": len(przed),
        "wiersze_ze_zmieniona_ranga": zmienione,
        "rozne_wyniki_przed": int(przed.nunique()),
        "rozne_wyniki_po": int(po.nunique()),
        "spearman": round(float(rangi_przed.corr(rangi_po)), 6),
    }


def main() -> None:
    con = connect(read_only=True)
    try:
        treningowe = con.sql("SELECT * FROM cechy_treningowe").df()
    finally:
        con.close()
    treningowe["t0"] = pd.to_datetime(treningowe["t0"])
    uczacy, testowy = podzial_czasowy(treningowe)
    y = testowy["odejdzie_90d"].astype(int)

    model = ModelSkalibrowany().fit(uczacy, uczacy["odejdzie_90d"])
    model.save(ARTEFAKTY)
    model = ModelSkalibrowany.load(ARTEFAKTY)  # oceniamy to, co zapisane
    assert model.wersja == WERSJA, "wersja modelu musi się nazywać jak folder w versions/"
    p = model.predict_proba(testowy)
    przed = model.predict_proba_bazowy(testowy)
    p_v3 = ModelKatalog.load(ARTEFAKTY_V3).predict_proba(testowy)

    kolejnosc = kolejnosc_bez_zmian(przed, p)
    auc, auc_przed = float(roc_auc_score(y, p)), float(roc_auc_score(y, przed))
    assert kolejnosc["wiersze_ze_zmieniona_ranga"] == 0, f"kalibracja zmieniła kolejność biur: {kolejnosc}"
    assert auc == auc_przed, f"AUC po kalibracji {auc} ≠ przed {auc_przed}"
    dol, gora = przedzial_bootstrap(y, p, testowy["id_biura"])

    brier = {
        nazwa: round(float(brier_score_loss(y, wynik)), 5)
        for nazwa, wynik in (
            ("v4_skalibrowany", p),
            ("bazowy_przed_kalibracja", przed),
            ("v3_katalog", p_v3),
            ("stala_3_5", np.full(len(y), STALA)),
        )
    }
    udzial = waznosc_cech(model.bazowy)
    ocena = {
        "wersja": model.wersja,
        "sposob_oceny": SPOSOB_OCENY,
        "auc": round(auc, 4),
        "auc_95": [round(dol, 4), round(gora, 4)],
        "auc_przed_kalibracja": round(auc_przed, 4),
        "kolejnosc_przed_i_po_kalibracji": kolejnosc,
        "brier": brier,
        "log_loss": round(float(log_loss(y, p)), 4),
        "srednie_p": round(float(p.mean()), 4),
        "odsetek_odejsc": round(float(y.mean()), 4),
        "max_p": round(float(p.max()), 4),
        "kalibracja_platt": model.platt,
        "okresy": model.okresy,
        "test": {
            "snapszoty": f"{testowy['t0'].min():%Y-%m} – {testowy['t0'].max():%Y-%m}",
            "wiersze": len(testowy),
            "jedynki": int(y.sum()),
        },
        "waznosc_gain": {k: round(float(v), 4) for k, v in udzial.items()},
        "bootstrap": "1000 losowań biur ze zwracaniem, ziarno 42",
    }
    (ARTEFAKTY / "ocena.json").write_text(json.dumps(ocena, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(ocena, ensure_ascii=False, indent=2))

    parametry = {
        "zbior": "cechy_treningowe (ai/features/build.py, sql/ i katalog.yaml), etykieta odejdzie_90d ze snapshoty",
        "model_bazowy": "Pipeline v3_katalog (one-hot → StandardScaler → LightGBM class_weight=balanced)",
        "kalibracja": "Platt: CalibratedClassifierCV(FrozenEstimator(bazowy), method=sigmoid)",
        "miesiace_walidacji": MIESIACE_WALIDACJI,
        "bazowy_snapszoty": model.okresy["bazowy"]["snapszoty"],
        "walidacja_snapszoty": model.okresy["walidacja"]["snapszoty"],
        "wiersze_bazowy": model.okresy["bazowy"]["wiersze"],
        "wiersze_walidacja": model.okresy["walidacja"]["wiersze"],
        "wiersze_testowe": len(testowy),
        "platt_a": model.platt["a"],
        "platt_b": model.platt["b"],
        **{f"lgbm_{k}": v for k, v in model.bazowy.named_steps["lgbm"].get_params().items()},
    }
    metryki = {
        "auc": auc,
        "auc_przed_kalibracja": auc_przed,
        "brier": brier["v4_skalibrowany"],
        "brier_przed_kalibracja": brier["bazowy_przed_kalibracja"],
        "brier_v3_katalog": brier["v3_katalog"],
        "brier_stala_3_5": brier["stala_3_5"],
        "log_loss": ocena["log_loss"],
        "srednie_p": ocena["srednie_p"],
        "wiersze_ze_zmieniona_ranga": kolejnosc["wiersze_ze_zmieniona_ranga"],
    }
    wykres = wykres_waznosci(
        udzial,
        tytul=f"{WERSJA}: ważność cech modelu bazowego (udział w gain, one-hot zsumowany)",
        os_x="udział w sumie gain",
        format_wartosci="{:.1%}",
    )
    run_id = loguj_wersje(
        WERSJA,
        SPOSOB_OCENY,
        parametry,
        metryki,
        wykres,
        ARTEFAKTY,
        opis="Pipeline v3_katalog uczony na t0 2024-04 – 2025-01 i skalibrowany metodą Platta na t0 2025-05 – "
        "2025-07, żeby wynik był P(odejście w 90 dni) do wzoru p × s × V − C (evals/kalibracja.md).",
    )
    print(f"MLflow: run {run_id}")


if __name__ == "__main__":
    main()
