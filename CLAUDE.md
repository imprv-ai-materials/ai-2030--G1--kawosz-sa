# Kawosz S.A.

## Zasady pracy z danymi

- **`data/` jest tylko do odczytu.** Nie modyfikuj, nie nadpisuj, nie usuwaj ani nie generuj ponownie plików w `data/`. Wyniki pośrednie i analizy zapisuj poza tym katalogiem.
- **`data/kawosz_gen/` jest zakazany.** Nie czytaj, nie przeszukuj, nie importuj ani nie uruchamiaj kodu z tego katalogu — to generator danych, który zdradza mechanizmy i klucz odpowiedzi.

## Model churnu

- **Każdą nową wersję modelu logujemy w MLflow pod nazwą folderu z `api/api/ai/churn_model/versions/`.** Eksperyment
  `churn`, nazwa runu = nazwa folderu = `wersja` modelu. Run zawiera parametry, sposób oceny (tag `sposob_oceny`),
  AUC i wykres ważności cech. Służy do tego `api/api/ai/churn_model/rejestr.py` (`loguj_wersje`). Serwer:
  `poetry run pypyr start_mlflow` → http://127.0.0.1:5050 (dane w `dev/mlflow/`, poza gitem). Wersję dopisz też do
  `api/api/ai/churn_model/evals/porownanie.md`.
