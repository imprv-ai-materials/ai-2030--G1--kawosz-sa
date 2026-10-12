# Porównanie wersji modelu churnu

Etykieta: `odejdzie_90d` z tabeli `snapshoty` (docs/target.md). AUC na części testowej. Wiersze o różnym sposobie oceny
nie są wprost porównywalne. Każda wersja ma też run o tej samej nazwie w MLflow (eksperyment `churn`,
`poetry run pypyr start_mlflow` → http://127.0.0.1:5050).

| Wersja | Sposób oceny | AUC | Szczegóły |
|---|---|---:|---|
| v0_agencja | losowy podział wierszy 80/20 (stratyfikowany, seed 42) na `agencja_features`; 12 346 wierszy, 9 snapszotów kwartalnych | 0,9999 | [v0_agencja.md](v0_agencja.md): przeciek `dni_do_konca_umowy`, bez niej 0,968 |
| regula_opiekunow (**punkt odniesienia**) | ten sam zbiór testowy co v0_agencja (2 470 wierszy, 87 odejść); reguła 0/1 bez uczenia; cechy z `iot_telemetria` i rocznicy umowy na dzień snapszotu | 0,7028 | [regula_opiekunow.md](regula_opiekunow.md): oznacza 84, precyzja 44,0%, czułość 42,5% |
| v2_bez_przeciekow | ten sam zbiór i podział co v0_agencja; cechy z `ai/features/cechy_snapszotu.sql` na dzień snapszotu, bez 4 cech powstających po wypowiedzeniu, `miasto_te` tylko na zbiorze uczącym | 0,8123 | [v2_bez_przeciekow.md](v2_bez_przeciekow.md): podział w czasie 0,7989 (v0: 0,9995); przy 84 oznaczonych precyzja 35,7%, czułość 34,5% |
| v0_agencja | **podział w czasie** ([ocena_w_czasie.md](ocena_w_czasie.md)): uczenie na wierszach agencji 2024-04 – 2025-10, 3 miesiące przerwy, test na wierszach agencji 2026-01 i 2026-04 (2 793 wiersze, 98 odejść) | 0,9995 | przedział 95% 0,9991–0,9998; nadal przeciek w cechach, nie do osiągnięcia w produkcji |
| v2_bez_przeciekow | **podział w czasie**, ten sam test; uczenie na wszystkich miesięcznych snapszotach 2024-01 – 2025-10 | 0,8273 | przedział 95% 0,774–0,878; w top 84 trafia 36 odejść (reguła 38); na wszystkich snapszotach 2026-01 – 2026-06: 0,787 |
| regula_opiekunow | **podział w czasie**, ten sam test; bez uczenia | 0,6853 | przedział 95% 0,641–0,734; oznacza 84, precyzja 45,2%, czułość 38,8%; na wszystkich snapszotach 2026-01 – 2026-06: 0,671 |
