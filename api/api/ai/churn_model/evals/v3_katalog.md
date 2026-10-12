# v3_katalog: jeden Pipeline na cechach z `cechy_treningowe`

**AUC = 0,783** (95% przedział bootstrap po biurach 0,734–0,829) przy podziale w czasie takim jak w v2: uczenie na
snapszotach 2024-04 – 2025-07, test na 2025-10 – 2026-04, wszystkie miesięczne wiersze `cechy_treningowe`. v2 na tych
samych wierszach ma 0,791. Różnica −0,007 mieści się w szumie (95% przedział różnicy −0,032…+0,021).

**Przeniesienie cech nie zmieniło AUC.** Pliki `api/ai/features/sql/` z opóźnieniem dostaw 0 dają v2 identyczne
predykcje jak `cechy_snapszotu.sql` (AUC 0,7989 = 0,7989). Opóźnienia dostaw (docs/opoznienia_danych.md) zmieniają
AUC v2 o −0,002 (0,7989 → 0,7966), też w szumie.

## 1. Jak liczone

| | |
|---|---|
| Dane | tabela `cechy_treningowe` (`api/ai/features/build.py`): 16 cech z `katalog.yaml`, etykieta `odejdzie_90d` ze `snapshoty` |
| Podział | jak `auc_podzial_czasowy` w v2: uczenie na t0 od 2024-04 do ostatniego snapszotu z oknem etykiety przed 2025-10-01 (2025-07), test na t0 2025-10 – 2026-04. v2 brała z tych miesięcy wiersze agencji (kwartalne), v3 bierze wszystkie miesięczne: 21 827 uczących (779 odejść), 9 769 testowych (346 odejść) |
| Model | jeden `sklearn.pipeline.Pipeline`: `kodowanie` (OneHotEncoder na `plan`, `branza`, `miasto`, `am_id`; brak to osobna kategoria, nieznana kategoria daje zera) → `skalowanie` (StandardScaler na wszystkich kolumnach, braki zostają NaN) → `lgbm` (`LGBMClassifier`, `class_weight="balanced"`, `random_state=42`, poza tym domyślny) |
| Uczenie przekształceń | kodowanie i skalowanie to kroki Pipeline, więc uczą się w `fit()` tylko na części uczącej. W walidacji krzyżowej `cross_validate` klonuje Pipeline w każdym foldzie. Test `test_kodowanie_i_skalowanie_ucza_sie_tylko_na_czesci_uczacej_kazdego_foldu` sprawdza kategorie i średnie skalera w każdym foldzie |
| Walidacja krzyżowa | 3 foldy w czasie w części uczącej: walidacja na kwartałach od 2024-10, 2025-01 i 2025-04, uczenie na snapszotach z oknem etykiety przed foldem |
| Względem v2 | brak `miasto_te` (kodowanie etykietą): `miasto` jest w one-hot, który etykiety nie widzi. `am_id` jest kategorią, a nie liczbą. Wagi klas `balanced` |
| Kod | `versions/v3_katalog/` (`model.py`, `trenuj.py`); `model.joblib`, `meta.json`, `ocena.json` i wykres w `artefakty/`; MLflow: eksperyment `churn`, run `v3_katalog` |

```bash
PYTHONPATH=api poetry run python -m api.ai.features.build            # tabela cechy_treningowe
PYTHONPATH=api poetry run python -m api.ai.churn_model.versions.v3_katalog.trenuj
```

## 2. Czy AUC zmieniło się po przeniesieniu cech

Na wierszach i podziale v2 (klucze agencji, uczenie 2024-04 – 2025-07, test 2025-10 – 2026-04: 8 167 / 4 179
wierszy, 148 odejść w teście) zmieniam po jednym elemencie:

| Model | Cechy | AUC | Zmiana | Co się zmieniło |
|---|---|---:|---:|---|
| v2 | `cechy_snapszotu.sql` | 0,7989 | — | wynik v2 z `ocena.json`, odtworzony |
| v2 | `sql/` z opóźnieniem 0 (`znane_do = t0 − 1`) | 0,7989 | 0,0000 | przeniesienie cech do plików rodzin i ASOF JOIN; predykcje identyczne |
| v2 | `cechy_treningowe` (opóźnienia dostaw) | 0,7966 | −0,0022 | opóźnienia CRM, ERP i helpdesku D+1; 95% przedział różnicy −0,023…+0,018 |
| v3 | `cechy_treningowe` | 0,7906 | −0,0060 | nowy Pipeline |

Wiersz z opóźnieniem 0 liczyłem jednorazowo, na kopii plików `sql/` ze stałą `- 1` zamiast `- 2`. Ten sam test
co wartość po wartości porównuje cechy jest w docs/opoznienia_danych.md, sekcja 6. Pozostałe wiersze liczy
`trenuj.py` (`porownanie_z_v2_na_jej_wierszach` w `ocena.json`).

## 3. Wyniki

| | AUC | 95% przedział |
|---|---:|---|
| **v3_katalog**, test miesięczny 2025-10 – 2026-04 | **0,7834** | 0,734–0,829 |
| v2_bez_przeciekow, te same wiersze i cechy | 0,7905 | różnica v3 − v2: −0,032…+0,021 |
| v3, walidacja krzyżowa w części uczącej (foldy 2024-10, 2025-01, 2025-04) | 0,822 / 0,818 / 0,756, średnio 0,799 | — |

Pojedyncze zmiany Pipeline na teście miesięcznym, liczone jednorazowo (bez składania ich w kombinacje):

| Zmiana względem v3 | AUC |
|---|---:|
| v3 bez zmian | 0,7834 |
| bez `class_weight="balanced"` | 0,8006 |
| bez StandardScaler | 0,7727 |

StandardScaler nie zmienia kolejności wartości, więc dla drzew powinien być obojętny. Zmienia jednak granice
koszyków histogramu LightGBM, a różnica ±0,01 to skala szumu tego zbioru. `class_weight="balanced"` obniża AUC o
0,017. Wagi zmieniają głównie kalibrację prawdopodobieństw, a nie ranking. Przy 3,5% odejść model z wagami
przeszacowuje prawdopodobieństwo, więc jego wyników nie wolno czytać jako P(odejście) bez ponownej kalibracji.

Ważność cech (udział w gain, one-hot zsumowany do cechy): `trend_zaparzen` 22,3%, `dni_do_rocznicy` 16,8%,
`zaparzenia_30d` 10,9%, `branza` 9,6%, `cena_mies` 8,4%. `dni_od_ostatniego_zamowienia` spada do 2,1% (w v2 4,9%), bo
po opóźnieniu ERP w t0 nie widać faktury z ostatniego dnia miesiąca.

## 4. Wniosek

- Przeniesienie cech do `api/ai/features/sql/` i tabeli `cechy_treningowe` zachowuje wynik v2. Opóźnienia dostaw
  kosztują około 0,002 AUC, czyli tyle, co szum. To cena liczenia tylko z danych, które na produkcji byłyby dostępne.
- v3 nie jest lepsza od v2 (−0,007, w szumie). Zyskuje to, że cały model to jeden obiekt `Pipeline` uczony na
  jednej tabeli, bez kodowania etykietą. Każdy krok przekształceń uczy się tylko na części uczącej.
- `class_weight="balanced"` w tej konfiguracji szkodzi rankingowi o 0,017. Warto przetestować v3 bez wag albo z
  kalibracją, zanim wyniki trafią do opiekunów.
- Zgodność tabeli z danymi z przeszłości sprawdza przy każdym commicie test
  `api/tests/ai/features/test_cechy_z_przeszlosci.py` (5 losowych par biuro × t0, hook `cechy-z-przeszlosci`).
