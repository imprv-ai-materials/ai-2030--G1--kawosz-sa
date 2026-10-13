"""Proces API: funkcje Inngest pod /api/inngest (serwer Inngest woła je stąd), dane panelu jakości i katalogu cech
dla ui/, kalkulator wizyt opiekunów i cechy modelu churnu jednego biura.

    INNGEST_DEV=http://127.0.0.1:8488 PYTHONPATH=api poetry run uvicorn api.main:app --app-dir api --port 8101

Baza: kawosz.duckdb albo KAWOSZ_BAZA (np. _symulacja/kawosz.duckdb z symulacji nocnego potoku).
"""

from datetime import date

import duckdb
import fastapi
import inngest.fast_api

from api.adapters.duckdb_conn import connect
from api.ai.features import build as cechy_churnu
from api.ai.features import katalog
from api.contexts_boundaries.retention_bc.prog import kalkulator
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


@app.get("/api/katalog")
def katalog_cech() -> dict:
    """Katalog cech: karty z katalog.yaml, modele wyliczone z wersji i ostatnie PSI z psi_cech."""
    try:
        return katalog.dane(Ustawienia.z_env().baza)
    except duckdb.IOException as e:  # nocny potok trzyma bazę do zapisu
        raise fastapi.HTTPException(
            status_code=503, detail="Dane są właśnie aktualizowane przez nocny potok. Spróbuj za kilka minut."
        ) from e


@app.get("/api/wizyty")
def kalkulator_wizyt(
    s: float | None = fastapi.Query(None, gt=0, le=1),
    V: float | None = fastapi.Query(None, gt=0),
    C: float | None = fastapi.Query(None, ge=0),
    budzet: int | None = fastapi.Query(None, ge=0),
    kontrola: float = fastapi.Query(0.0, ge=0, le=0.5),
) -> dict:
    """Kalkulator wizyt: próg C / (s × V), dzisiejsze biura do odwiedzenia w budżecie, zysk i krzywa wartości.
    Brakujące s, V, C i budżet bierze z retention_bc/zalozenia.yaml. kontrola: udział listy losowo bez wizyty
    (grupa kontrolna do pomiaru skuteczności wizyty)."""
    try:
        return kalkulator.dane(Ustawienia.z_env().baza, s, V, C, budzet, kontrola)
    except duckdb.IOException as e:  # nocny potok trzyma bazę do zapisu
        raise fastapi.HTTPException(
            status_code=503, detail="Dane są właśnie aktualizowane przez nocny potok. Spróbuj za kilka minut."
        ) from e


@app.get("/api/biura/{id_biura}/cechy")
def cechy_biura(id_biura: int, t0: date | None = None) -> dict:
    """Cechy modelu churnu jednego biura na początek dnia t0 (domyślnie DZIS), liczone na żywo z ai/features/sql/ tym
    samym kodem co cechy_treningowe i cechy_aktualne. Kolumny jak w cechy_aktualne."""
    t0 = t0 or cechy_churnu.DZIS
    if t0 > cechy_churnu.DZIS:
        raise fastapi.HTTPException(
            status_code=422,
            detail=f"t0 = {t0} jest po dniu dzisiejszym ({cechy_churnu.DZIS}): dane kończą się na eksporcie, więc "
            "okna cech byłyby częściowo bez danych.",
        )
    try:
        con = connect(read_only=True, db_path=Ustawienia.z_env().baza)
    except duckdb.IOException as e:  # nocny potok trzyma bazę do zapisu
        raise fastapi.HTTPException(
            status_code=503, detail="Dane są właśnie aktualizowane przez nocny potok. Spróbuj za kilka minut."
        ) from e
    try:
        cechy = cechy_churnu.cechy_biura(con, id_biura, t0)
    finally:
        con.close()
    if cechy is None:
        raise fastapi.HTTPException(
            status_code=404,
            detail=f"Biuro {id_biura} nie ma w {t0} aktywnej umowy bez wypowiedzenia albo nie istnieje, więc model "
            "go nie ocenia.",
        )
    return cechy
