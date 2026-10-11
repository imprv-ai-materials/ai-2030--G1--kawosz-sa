# ai-2030--G1--kawosz-sa

Dane kursowe Kawosz S.A. w `data/` (opis: [data/README.md](data/README.md)).

```bash
poetry install
PYTHONPATH=api poetry run python -m api.data_platform.load_raw   # data/ → kawosz.duckdb
```
