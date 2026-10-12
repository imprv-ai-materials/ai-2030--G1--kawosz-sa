"""Proces API: serwuje funkcje Inngest pod /api/inngest (serwer Inngest woła je stąd).

    INNGEST_DEV=http://127.0.0.1:8488 PYTHONPATH=api poetry run uvicorn api.main:app --app-dir api --port 8103
"""

import fastapi
import inngest.fast_api

from api.inngest_app import FUNKCJE, client

app = fastapi.FastAPI(title="Kawosz S.A.")
inngest.fast_api.serve(app, client, FUNKCJE)
