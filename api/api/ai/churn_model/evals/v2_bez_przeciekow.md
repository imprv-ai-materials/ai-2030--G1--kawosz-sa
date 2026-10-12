# v2_bez_przeciekow: model agencji na cechach bez przecieków

**AUC = 0,812** (95% przedział bootstrap 0,755–0,862) na tym samym zbiorze testowym co v0_agencja (2 470 wierszy, 87
odejść). Przy podziale w czasie AUC wynosi **0,799**. Model i parametry LightGBM są te same co w v0. Zmieniły się
tylko cechy, zgodnie z decyzjami w [docs/przecieki.md](../../../../../docs/przecieki.md), sekcja 7. Spadek z 0,9999
do 0,81 to więc cena usunięcia informacji z przyszłości, a nie gorszy model.

## 1. Jak liczone

| | |
|---|---|
| Wiersze i etykieta | te same co v0: `agencja_features` ⋈ `snapshoty`, 12 346 wierszy, 436 jedynek. Z tabeli agencji bierzemy tylko klucze i etykietę |
| Cechy | `api/ai/features/cechy_snapszotu.sql`, liczone na stan z początku dnia snapszotu, wyłącznie z rekordów sprzed tego dnia. 16 kolumn wejściowych i `miasto_te` liczone w modelu |
| `miasto_te` | średnia etykiety w mieście, tylko na zbiorze uczącym. Wiersze uczące dostają wartość policzoną poza swoim foldem (5 foldów po biurach), a testowe średnią z całego zbioru uczącego (`api/ai/features/kodowanie_celu.py`) |
| Podział (główny) | losowy po wierszach 80/20, stratyfikowany, `random_state=42`, jak u agencji (`zbior_agencji.py`): 9 876 uczących, 2 470 testowych |
| Podział w czasie (dodatkowy) | uczenie na snapszotach 2024-04 – 2025-07 (8 167 wierszy), test na 2025-10 – 2026-04 (4 179 wierszy, 148 odejść). Okna 90 dni snapszotów uczących kończą się przed pierwszym snapszotem testowym |
| Model | `LGBMClassifier` z domyślnymi parametrami, `random_state=42` (jak v0) |
| Kod | `versions/v2_bez_przeciekow/` (`model.py`, `trenuj.py`); model i `ocena.json` w `artefakty/`; MLflow: eksperyment `churn`, run `v2_bez_przeciekow` |

```bash
PYTHONPATH=api poetry run python -m api.ai.churn_model.versions.v2_bez_przeciekow.trenuj
```

## 2. Co się zmieniło względem v0

| Cecha v0 | v2 |
|---|---|
| `dni_do_konca_umowy`, `status_crm`, `zgloszenia_odbior_ekspresu`, `rabat_retencyjny_max` | **usunięte**: powstają dopiero po wypowiedzeniu |
| — | **`dni_do_rocznicy`**: dni do najbliższej rocznicy `data_startu`, czyli do terminu odnowienia |
| `dni_od_ostatniego_zamowienia` | do dnia snapszotu, a nie do dnia eksportu. Ostatnia faktura z kawą sprzed snapszotu |
| `zaparzenia_30d` | 30 ostatnich znanych dni przed snapszotem, a nie 30 dni po nim. Telemetria dociera z 2-dniowym opóźnieniem |
| `trend_zaparzen` | jawna definicja: ostatnie 30 znanych dni / poprzednie 30 dni |
| `plan`, `cena_mies` | z ostatniego zdarzenia umowy sprzed snapszotu, a nie stan z eksportu. Cena jest pusta, gdy ostatnie zdarzenie jest starsze niż rok (17% wierszy `snapshoty`), bo historia odnowień zaczyna się w 2024 |
| `bledy_60d`, `awarie_60d`, `kontakty_am_90d`, `nps_ostatni`, `sr_opoznienie_platnosci` | przeliczone z jawnymi oknami przed snapszotem |
| `miasto_te` | tylko na zbiorze uczącym, poza foldem |
| `liczba_pracownikow`, `am_id`, `miasto`, `branza`, `staz_mies` | bez zmian. Pierwsze cztery to stan z eksportu, bo nie mają historii |

Żadna cecha v2 nie ma AUC samej cechy powyżej 0,76 (wcześniej 4 miały powyżej 0,85). Najwyżej są
`zaparzenia_30d` (0,757), `dni_od_ostatniego_zamowienia` (0,724), `dni_do_rocznicy` (0,722) i `trend_zaparzen`
(0,713).

## 3. Wyniki

| | AUC losowy podział | AUC podział w czasie |
|---|---:|---:|
| v0_agencja | 0,9999 | 0,9995 |
| **v2_bez_przeciekow** | **0,812** | **0,799** |
| regula_opiekunow (punkt odniesienia) | 0,703 | — |

- **Podział nie tłumaczy wyniku agencji.** v0 ma przy podziale w czasie nadal 0,9995, więc 0,99 dają przecieki w
  cechach. v2 traci przy podziale w czasie tylko 0,013, a to wynik w granicach szumu.
- **Przy tej samej liczbie oznaczonych biur co reguła (84) v2 trafia 30 odejść: precyzja 35,7%, czułość 34,5%.**
  Reguła trafia 37 (44,0% / 42,5%). Wyższe AUC v2 oznacza lepszy ranking całego zbioru, ale na samej górze listy reguła
  jest na razie lepsza. v2 to LightGBM z domyślnymi parametrami i bez cech typu „koniec okresu w 90 dni i spadek
  zaparzeń”, które reguła łączy wprost.

Ważność cech (udział w gain): `dni_do_rocznicy` 20,0%, `trend_zaparzen` 18,2%, `zaparzenia_30d` 11,1%,
`cena_mies` 7,2%, `sr_opoznienie_platnosci` 6,8%. Żadna cecha nie dominuje, a w v0 jedna miała 95,5%.

## 4. Wniosek

v2 to pierwszy uczciwy punkt odniesienia dla modelu: AUC około 0,80 niezależnie od podziału. Następne kroki to ocena
podziałem w czasie jako główną metodą, dopasowanie parametrów LightGBM i cechy łączące termin odnowienia ze spadkiem
zaparzeń. Wtedy warto też porównywać wersje precyzją przy ustalonej liczbie oznaczonych biur.
