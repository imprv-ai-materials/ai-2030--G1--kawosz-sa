"""Proces API: funkcje Inngest pod /api/inngest (serwer Inngest woła je stąd) i dane panelu jakości dla ui/.

    INNGEST_DEV=http://127.0.0.1:8488 PYTHONPATH=api poetry run uvicorn api.main:app --app-dir api --port 8101

Baza: kawosz.duckdb albo KAWOSZ_BAZA (np. _symulacja/kawosz.duckdb z symulacji nocnego potoku).
"""

import duckdb
import fastapi
import inngest.fast_api

from api.data_platform import panel_jakosci
from api.data_platform.noc import Ustawienia
from api.inngest_app import FUNKCJE, client

app = fastapi.FastAPI(title="Kawosz S.A.")
inngest.fast_api.serve(app, client, FUNKCJE)


@app.get("/api/jakosc")
def jakosc(dni: int = fastapi.Query(30, ge=1, le=366)) -> dict:
    """Panel jakości: wsady, naruszenia reguł, wycena i most przychodu za ostatnie `dni` dni z wynikiem nocy."""
    try:
        return panel_jakosci.dane(Ustawienia.z_env().baza, dni)
    except panel_jakosci.BrakDanych as e:
        raise fastapi.HTTPException(status_code=404, detail=str(e)) from e
    except duckdb.IOException as e:  # nocny potok trzyma bazę do zapisu
        raise fastapi.HTTPException(
            status_code=503, detail="Dane są właśnie aktualizowane przez nocny potok. Spróbuj za kilka minut."
        ) from e
