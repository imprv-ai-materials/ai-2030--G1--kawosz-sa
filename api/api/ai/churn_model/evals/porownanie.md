# Porównanie wersji modelu churnu

Etykieta: `odejdzie_90d` z tabeli `snapshoty` (docs/target.md). AUC na części testowej. Wiersze o różnym sposobie oceny
nie są wprost porównywalne.

| Wersja | Sposób oceny | AUC | Szczegóły |
|---|---|---:|---|
| v0_agencja | losowy podział wierszy 80/20 (stratyfikowany, seed 42) na `agencja_features`; 12 346 wierszy, 9 snapszotów kwartalnych | 0,9999 | [v0_agencja.md](v0_agencja.md): przeciek `dni_do_konca_umowy`, bez niej 0,968 |
