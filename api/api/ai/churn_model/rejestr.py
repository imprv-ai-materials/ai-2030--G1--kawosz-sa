"""Logowanie wersji modelu churnu w MLflow: eksperyment „churn”, run nazwany jak folder w versions/.

Serwer uruchamia `poetry run pypyr start_mlflow` (dev/start_mlflow.yaml). Adres można zmienić zmienną
MLFLOW_TRACKING_URI.
"""

import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402
import mlflow  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from api.ai.churn_model.base import ChurnModel  # noqa: E402

ADRES = os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5050")
EKSPERYMENT = "churn"

# Paleta referencyjna (dataviz): jedna seria, więc jeden kolor; tekst w kolorach tekstu, nie serii.
KOLOR_SERII = "#2a78d6"
TLO = "#fcfcfb"
TEKST = "#0b0b0b"
TEKST_DRUGI = "#52514e"


def _sprawdz_serwer() -> None:
    try:
        requests.get(f"{ADRES}/health", timeout=3).raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"MLflow nie odpowiada pod {ADRES}. Uruchom: poetry run pypyr start_mlflow") from e


def waznosc_permutacyjna(
    model: ChurnModel, X: pd.DataFrame, y: pd.Series, powtorzenia: int = 10, ziarno: int = 42
) -> pd.Series:
    """Średni spadek AUC po przemieszaniu jednej cechy (działa też dla reguł bez wbudowanej ważności)."""
    rng = np.random.default_rng(ziarno)
    bazowe = roc_auc_score(y, model.predict_proba(X))
    spadki = {}
    for cecha in model.cechy:
        wyniki = []
        for _ in range(powtorzenia):
            Xp = X.copy()
            Xp[cecha] = rng.permutation(Xp[cecha].to_numpy())
            wyniki.append(bazowe - roc_auc_score(y, model.predict_proba(Xp)))
        spadki[cecha] = float(np.mean(wyniki))
    return pd.Series(spadki).sort_values(ascending=False)


def wykres_waznosci(waznosc: pd.Series, tytul: str, os_x: str, format_wartosci: str, podpisane: int = 5):
    """Poziome słupki od najważniejszej cechy u góry; wartości podpisane tylko przy `podpisane` największych."""
    w = waznosc.sort_values()
    fig, ax = plt.subplots(figsize=(8, 0.32 * len(w) + 1.4), facecolor=TLO)
    ax.set_facecolor(TLO)
    ax.barh(w.index, w.to_numpy(), height=0.6, color=KOLOR_SERII)
    for i, (nazwa, wartosc) in enumerate(w.items()):
        if i >= len(w) - podpisane:
            ax.annotate(
                format_wartosci.format(wartosc),
                (wartosc, i),
                xytext=(4 if wartosc >= 0 else -4, 0),
                textcoords="offset points",
                va="center",
                ha="left" if wartosc >= 0 else "right",
                fontsize=8,
                color=TEKST_DRUGI,
            )
    ax.set_title(tytul, loc="left", fontsize=11, color=TEKST)
    ax.set_xlabel(os_x, fontsize=9, color=TEKST_DRUGI)
    ax.tick_params(colors=TEKST_DRUGI, labelsize=8, length=0)
    ax.grid(axis="x", color="#e4e3df", linewidth=0.8)
    ax.set_axisbelow(True)
    for strona in ax.spines.values():
        strona.set_visible(False)
    ax.axvline(0, color=TEKST_DRUGI, linewidth=0.8)
    if "%" in format_wartosci:
        ax.xaxis.set_major_formatter(PercentFormatter(1.0))
    ax.margins(x=0.12)
    fig.tight_layout()
    return fig


def loguj_wersje(
    wersja: str,
    sposob_oceny: str,
    parametry: dict,
    metryki: dict,
    wykres,
    artefakty: Path,
    opis: str = "",
) -> str:
    """Zapisuje run `wersja` w eksperymencie churn: tagi, parametry, metryki, wykres i pliki z `artefakty`.

    Wykres trafia też do `artefakty/waznosc_cech.png`, żeby był widoczny bez MLflow. Zwraca run_id.
    """
    _sprawdz_serwer()
    wykres_png = artefakty / "waznosc_cech.png"
    wykres.savefig(wykres_png, dpi=150, facecolor=TLO)
    plt.close(wykres)

    mlflow.set_tracking_uri(ADRES)
    mlflow.set_experiment(EKSPERYMENT)
    with mlflow.start_run(run_name=wersja) as run:
        mlflow.set_tags({"wersja": wersja, "sposob_oceny": sposob_oceny, "mlflow.note.content": opis})
        mlflow.log_params(parametry)
        mlflow.log_metrics(metryki)
        mlflow.log_artifact(str(wykres_png))
        for plik in sorted(artefakty.iterdir()):
            if plik != wykres_png:
                mlflow.log_artifact(str(plik), artifact_path="artefakty")
        return run.info.run_id
