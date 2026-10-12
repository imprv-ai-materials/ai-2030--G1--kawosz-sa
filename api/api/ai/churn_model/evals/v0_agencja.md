# v0_agencja: odtworzenie modelu agencji

**AUC = 0,9999** na losowych 20% wierszy. Agencja podaje 0,99, więc wynik się odtwarza (a nawet go przewyższa).
To nie jest jednak miara jakości prognozy: 95,5% ważności daje jedna cecha, która zna przyszłość (sekcja 3).

## 1. Jak liczone

| | |
|---|---|
| Dane | `agencja_features` (`data/agencja/`) ⋈ `snapshoty` po `id_biura` i `data_migawki = data_snapszotu` |
| Etykieta | `odejdzie_90d` z `snapshoty` (docs/target.md); kolumnę agencji pominięto, na wspólnych wierszach jest identyczna |
| Wiersze | 12 346 (9 snapszotów kwartalnych 2024-04 – 2026-04), 436 jedynek (3,53%). 5 wierszy agencji nie ma odpowiednika w `snapshoty`: to biura w okresie wypowiedzenia, wykluczone z populacji |
| Cechy | 20 kolumn agencji bez zmian; `status_crm`, `plan`, `branza`, `miasto` jako kategoryczne |
| Podział | losowy po wierszach 80/20, stratyfikowany, `random_state=42`: 9 876 uczących, 2 470 testowych |
| Model | `LGBMClassifier` z domyślnymi parametrami, `random_state=42` |
| Kod | dane i podział: `zbior_agencji.py`; model: `versions/v0_agencja/` (`model.py`, `trenuj.py`); model i `ocena.json` w `versions/v0_agencja/artefakty/` |

```bash
PYTHONPATH=api poetry run python -m api.ai.churn_model.versions.v0_agencja.trenuj
```

## 2. 10 najważniejszych cech

Udział w sumie gain LightGBM. „AUC samej cechy” to AUC rankingu po surowej wartości cechy na wszystkich 12 346
wierszach (brak = mediana), liczone bez modelu.

| # | Cecha | Udział gain | AUC samej cechy |
|---:|---|---:|---:|
| 1 | `dni_do_konca_umowy` | 95,50% | 0,999 |
| 2 | `zaparzenia_30d` | 0,67% | 0,795 |
| 3 | `dni_od_ostatniego_zamowienia` | 0,60% | 0,944 |
| 4 | `bledy_60d` | 0,51% | 0,540 |
| 5 | `staz_mies` | 0,44% | 0,529 |
| 6 | `sr_opoznienie_platnosci` | 0,40% | 0,587 |
| 7 | `cena_mies` | 0,38% | 0,559 |
| 8 | `trend_zaparzen` | 0,35% | 0,737 |
| 9 | `liczba_pracownikow` | 0,35% | 0,535 |
| 10 | `am_id` | 0,32% | 0,520 |

## 3. Dlaczego 0,99: przecieki i podział losowy

**`dni_do_konca_umowy` przecieka z przyszłości.** We wszystkich 12 351 wierszach agencji
`dni_do_konca_umowy = crm_biura.data_konca_umowy − data_migawki`. `data_konca_umowy` to stan z dnia eksportu
(2026-09-30):
- u biura, które później odnowiło umowę, to koniec *ostatniej odnowionej* umowy, czyli lata po snapszocie;
- u biura, które odeszło, to faktyczny koniec umowy, czyli najwyżej ~4 miesiące po snapszocie.

W efekcie najmniejsza wartość wśród zer to 89 dni, a 313 z 436 jedynek ma mniej niż 90. Uczciwy odpowiednik to liczba
dni do najbliższej rocznicy umowy, liczona od `data_startu`. Też niesie sygnał, bo brak odnowienia zdarza się tylko w
rocznicę, ale nie rozdziela klas po fakcie: biuro, które odnowi umowę, ma rocznicę równie blisko jak biuro, które jej
nie odnowi.

**Bez tej cechy AUC to nadal 0,968** (ten sam podział, usunięta tylko ta jedna cecha). Inne cechy też rozdzielają
klasy zbyt dobrze jak na stan z dnia snapszotu. Poniższe obserwacje nie są jeszcze zweryfikowane w źródłach:

| Cecha | AUC samej cechy | Co widać | Podejrzenie |
|---|---:|---|---|
| `zgloszenia_odbior_ekspresu` | 0,910 | średnio 1,0 u jedynek, 0,2 u zer | zgłoszenie odbioru ekspresu to skutek odejścia, a nie jego zapowiedź |
| `dni_od_ostatniego_zamowienia` | 0,944 | u jedynek min 92, mediana 607; u zer mediana 0 | liczone do dnia eksportu, a nie do snapszotu |
| `rabat_retencyjny_max` | 0,808 | mediana 10 u jedynek, 0 u zer | rabat retencyjny daje się klientowi, który już zgłosił odejście |
| `status_crm` | — | wszystkie 436 jedynek mają `zakończony`; to status z dnia eksportu | jawny przeciek, choć model z niego nie korzysta, bo ma lepszą cechę |
| `miasto_te` | — | nazwa sugeruje target encoding | nie wiadomo, na jakich wierszach go liczono |

Usunięcie dowolnej z nich pojedynczo nie zmienia AUC (0,9998–0,9999), bo `dni_do_konca_umowy` wystarcza sama.

**Podział losowy po wierszach** dodatkowo zawyża wynik. To samo biuro jest w kilku snapszotach, więc trafia jednocześnie
do części uczącej i testowej, a model widzi na teście biuro, którego cechy już zna. Snapszoty kwartalne nie dają nakładania się
okien 90-dniowych, ale cechy stałe biura (branża, AM, liczba pracowników) i tak przechodzą przez podział.

## 4. Wniosek

v0 to punkt odniesienia, a nie model do wdrożenia. AUC 0,99 agencji wynika z cech liczonych na stanie z dnia eksportu
i z losowego podziału. Kolejne wersje powinny liczyć cechy wyłącznie ze zdarzeń sprzed `data_snapszotu` i być
oceniane podziałem w czasie (uczenie na starszych snapszotach, test na nowszych), najlepiej z rozłącznymi biurami.
