# Przecieki w cechach modelu agencji

Model agencji (`v0_agencja`, LightGBM na 20 cechach `agencja_features`) ma **AUC 0,9999** na losowych 20% wierszy.
Sprawdzam, które cechy dają ten wynik. Dla każdej z 20 cech liczę AUC samej cechy oraz spadek AUC modelu po jej
usunięciu.

**Wynik:** 4 cechy mają AUC powyżej 0,85: `dni_do_konca_umowy`, `dni_od_ostatniego_zamowienia`, `status_crm` i
`zgloszenia_odbior_ekspresu`. Usunięcie jednej cechy obniża AUC zauważalnie tylko dla `dni_do_konca_umowy` (o 0,032).
Pozostałe przecieki są wtedy niewidoczne, bo ta jedna cecha wystarcza modelowi sama. Model bez wszystkich czterech
oznaczonych cech ma AUC 0,901, więc nadal za wysokie (sekcja 4).

**Skąd biorą się te przecieki (sekcja 6):** sprawdziłem 7 podejrzanych cech. W 6 z nich agencja użyła informacji, której w
dniu snapszotu jeszcze nie było. 4 cechy powstają dopiero po wypowiedzeniu: `dni_do_konca_umowy`, `status_crm`,
`zgloszenia_odbior_ekspresu` i `rabat_retencyjny_max`. 2 cechy mają uczciwe źródło, ale zły dzień odniesienia:
`dni_od_ostatniego_zamowienia` liczy do dnia eksportu, a `zaparzenia_30d` sumuje 30 dni *po* snapszocie. Decyzje,
co z każdą cechą zrobić, zatwierdzono 2026-10-12 (sekcja 7), a wdrożenie opisuje sekcja 8.

## 1. Jak liczone

| | |
|---|---|
| Dane | `agencja_features` ⋈ `snapshoty`, czyli ten sam zbiór co `v0_agencja`: 12 346 wierszy, 436 jedynek (3,53%) |
| Model i podział | jak w [`evals/v0_agencja.md`](../api/api/ai/churn_model/evals/v0_agencja.md): `LGBMClassifier` z parametrami domyślnymi, losowy podział 80/20, stratyfikowany, `random_state=42` (2 470 wierszy testowych, w tym 87 jedynek) |
| AUC samej cechy | na wszystkich 12 346 wierszach, bez modelu. **Cechy liczbowe:** ranking po surowej wartości, brak = mediana. Podaję `max(AUC, 1 − AUC)`, a kierunek jest w osobnej kolumnie (↑: wyższa wartość oznacza odejście). **Kategorie** (`status_crm`, `plan`, `branza`, `miasto`, a także `am_id`, bo numer AM to identyfikator): odsetek odejść w kategorii liczony na 4/5 wierszy i oceniany na pozostałej 1/5 (5 foldów) |
| AUC modelu jednej cechy | kontrola: LightGBM uczony tylko na tej cesze, oceniany na zbiorze testowym. Wychwytuje zależności niemonotoniczne |
| Spadek po usunięciu | AUC modelu na 20 cechach (0,9999) minus AUC modelu uczonego od nowa na 19 cechach. Podział jest ten sam |
| Próg | AUC samej cechy > 0,85 ⇒ ⚠️ |

W teście są tylko 87 jedynki, więc różnice AUC rzędu ±0,003 to szum.

## 2. AUC samej cechy (malejąco) i spadek po usunięciu

| # | Cecha | AUC samej cechy | Kierunek | AUC modelu jednej cechy | AUC bez cechy | Spadek | |
|---:|---|---:|:---:|---:|---:|---:|:---:|
| 1 | `dni_do_konca_umowy` | **0,999** | ↓ | 1,000 | 0,968 | **0,032** | ⚠️ |
| 2 | `dni_od_ostatniego_zamowienia` | **0,944** | ↑ | 0,939 | 1,000 | 0,000 | ⚠️ |
| 3 | `status_crm` | **0,922** | kat. | 0,922 | 1,000 | 0,000 | ⚠️ |
| 4 | `zgloszenia_odbior_ekspresu` | **0,910** | ↑ | 0,920 | 1,000 | 0,000 | ⚠️ |
| 5 | `rabat_retencyjny_max` | 0,808 | ↑ | 0,813 | 1,000 | 0,000 | |
| 6 | `zaparzenia_30d` | 0,795 | ↓ | 0,733 | 1,000 | 0,000 | |
| 7 | `trend_zaparzen` | 0,737 | ↓ | 0,683 | 1,000 | 0,000 | |
| 8 | `sr_opoznienie_platnosci` | 0,587 | ↑ | 0,596 | 1,000 | 0,000 | |
| 9 | `nps_ostatni` | 0,571 | ↓ | 0,560 | 1,000 | 0,000 | |
| 10 | `cena_mies` | 0,559 | ↓ | 0,526 | 1,000 | 0,000 | |
| 11 | `miasto_te` | 0,556 | ↑ | 0,471 | 1,000 | 0,000 | |
| 12 | `bledy_60d` | 0,540 | ↑ | 0,478 | 1,000 | 0,000 | |
| 13 | `liczba_pracownikow` | 0,535 | ↓ | 0,510 | 1,000 | 0,000 | |
| 14 | `awarie_60d` | 0,534 | ↑ | 0,558 | 1,000 | 0,000 | |
| 15 | `staz_mies` | 0,529 | ↑ | 0,721 | 1,000 | 0,000 | |
| 16 | `branza` | 0,525 | kat. | 0,563 | 1,000 | 0,000 | |
| 17 | `am_id` | 0,512 | kat. | 0,521 | 1,000 | 0,000 | |
| 18 | `plan` | 0,507 | kat. | 0,517 | 1,000 | 0,000 | |
| 19 | `kontakty_am_90d` | 0,501 | ↓ | 0,475 | 1,000 | 0,000 | |
| 20 | `miasto` | 0,477 | kat. | 0,470 | 1,000 | 0,000 | |

„1,000” w kolumnie „AUC bez cechy” oznacza 0,9998–0,9999. Spadek dla cech 2–20 mieści się w ±0,0001.

## 3. Cechy powyżej 0,85

| Cecha | Co widać w danych | Ocena |
|---|---|---|
| `dni_do_konca_umowy` | mediana 63 dni u jedynek, 632 u zer | **Potwierdzony przeciek** ([`v0_agencja.md`](../api/api/ai/churn_model/evals/v0_agencja.md), sekcja 3). Liczona jako `crm_biura.data_konca_umowy − data_migawki`, gdzie `data_konca_umowy` to stan z dnia eksportu. Biuro, które odejdzie, ma tam faktyczny koniec umowy, a biuro, które odnowi umowę, koniec ostatniej odnowionej umowy |
| `dni_od_ostatniego_zamowienia` | mediana 607 dni u jedynek, 0 u zer | **Prawie na pewno przeciek.** 607 dni bez zamówienia u biura z aktywną umową nie jest wiarygodne. Wygląda na wartość liczoną do dnia eksportu, a nie do snapszotu. Potwierdzone w sekcji 6.1 |
| `status_crm` | wszystkie 436 jedynek ma `zakończony`; wśród zer jest 1 842 `zakończony` | **Potwierdzony przeciek.** To status z dnia eksportu. Biuro z aktywną umową w dniu snapszotu nie może mieć wtedy statusu `zakończony` |
| `zgloszenia_odbior_ekspresu` | średnio 0,98 u jedynek, 0,16 u zer | **Potwierdzony przeciek** (sekcja 6.2). Odbiór ekspresu jest skutkiem odejścia: każde zgłoszenie powstaje 1–20 dni po wypowiedzeniu |

Tuż pod progiem są `rabat_retencyjny_max` (0,808) i `zaparzenia_30d` (0,795). Rabat retencyjny dostaje zwykle
klient, który już zgłosił odejście. Mediana zaparzeń u jedynek to 89 wobec 1 559 u zer, co może być prawdziwym
sygnałem (biuro przestaje używać ekspresu) albo oknem 30 dni liczonym od dnia eksportu. Sekcja 6 rozstrzyga obie
sprawy: rabat zawsze pada po wypowiedzeniu, a `zaparzenia_30d` sumuje 30 dni po snapszocie.

`staz_mies` ma AUC samej cechy 0,53, a model z tą jedną cechą 0,72. Zależność jest niemonotoniczna: brak odnowienia
zdarza się tylko w rocznicę umowy, więc liczy się staż modulo 12 miesięcy. To raczej uczciwy sygnał niż przeciek, o ile
staż liczono na dzień snapszotu.

## 4. Dlaczego usunięcie jednej cechy prawie niczego nie zmienia

Przecieki się dublują. `dni_do_konca_umowy` rozdziela klasy niemal idealnie, więc po usunięciu dowolnej innej cechy
model dalej ma ją do dyspozycji i AUC się nie zmienia. Pojedyncze usunięcie wykrywa tylko przeciek, który nie ma
zastępstwa. Dlatego test powtórzyłem dwa razy:

**a) Usuwanie po jednej cesze z modelu, który nie ma już `dni_do_konca_umowy`** (AUC bazowe 0,968). Największe spadki:
`dni_od_ostatniego_zamowienia` 0,008, `staz_mies` 0,005, `zaparzenia_30d` 0,004, `nps_ostatni` 0,002 i `status_crm`
0,001. Reszta mieści się w szumie (±0,003). Pozostałe przecieki nadal się dublują.

**b) Usuwanie cech łącznie** (ten sam podział):

| Usunięte cechy | AUC |
|---|---:|
| żadna | 0,9999 |
| `dni_do_konca_umowy` | 0,968 |
| 4 oznaczone (> 0,85) | 0,901 |
| 4 oznaczone + `rabat_retencyjny_max` | 0,839 |
| … + `zaparzenia_30d` | 0,764 |
| … + `trend_zaparzen` | 0,701 |

Po usunięciu czterech oznaczonych cech AUC nadal wynosi 0,90. To za dużo jak na cechy znane w dniu snapszotu, a
kolejne podejrzane cechy obniżają je stopniowo. Ostatnie trzy wiersze trzeba czytać ostrożnie: nie wiadomo, czy
`zaparzenia_30d` i `trend_zaparzen` przeciekają, czy po prostu niosą prawdziwy sygnał. Pewny jest tylko kierunek:
o wyniku agencji decydują cechy liczone na dzień eksportu.

Wszystkie liczby pochodzą z losowego podziału agencji. To samo biuro trafia wtedy do części uczącej i testowej, co
dodatkowo zawyża AUC ([`v0_agencja.md`](../api/api/ai/churn_model/evals/v0_agencja.md), sekcja 3).

## 5. Wniosek

Do kolejnej wersji modelu nie wolno brać z `agencja_features` cech `dni_do_konca_umowy`, `status_crm`,
`dni_od_ostatniego_zamowienia` ani `zgloszenia_odbior_ekspresu`. `rabat_retencyjny_max`, `zaparzenia_30d` i
`trend_zaparzen` wymagały sprawdzenia w źródłach (wynik: sekcja 6). Najbezpieczniej jest przeliczyć wszystkie cechy samemu,
wyłącznie ze zdarzeń sprzed `data_snapszotu`, i oceniać model podziałem w czasie.

## 6. Kiedy powstaje rekord, z którego liczona jest cecha

Pytanie brzmi: czy w dniu snapszotu dane, z których policzono cechę, już istniały? Jeśli rekord źródłowy powstaje
dopiero po wypowiedzeniu, cecha nie przewiduje odejścia, tylko je opisuje. Model uczy się wtedy rozpoznawać biura, które
już odeszły.

### 6.1 Jak agencja liczyła każdą cechę

Każdą definicję odtworzyłem z tabel źródłowych i porównałem z wartościami w `agencja_features`. W „Zgodności” podaję,
w ilu z 12 351 wierszy agencji moja wersja daje dokładnie tę samą wartość.

| Cecha | Rekord źródłowy | Jak liczy agencja | Zgodność |
|---|---|---|---|
| `dni_do_konca_umowy` | `crm_biura.data_konca_umowy` | `data_konca_umowy − data_migawki`, gdzie `data_konca_umowy` to stan z dnia eksportu (2026-09-30) | 12 351 / 12 351 |
| `status_crm` | `crm_biura.status` | status z dnia eksportu, ten sam we wszystkich snapszotach biura | 12 351 / 12 351 |
| `zgloszenia_odbior_ekspresu` | `helpdesk_zgloszenia`, kategoria `odbiór ekspresu` | liczba **wszystkich** zgłoszeń biura do dnia eksportu, także tych po snapszocie | 12 351 / 12 351 |
| `rabat_retencyjny_max` | `crm_kontakty_am.rabat_retencyjny_pct` | największy rabat z **wszystkich** kontaktów do dnia eksportu | 12 351 / 12 351 |
| `dni_od_ostatniego_zamowienia` | `erp_faktury` z pozycją kawy (indeks `10.*`), kontrahent przez `mapa_kontrahentow` | `2026-09-30 − data ostatniej faktury z kawą`, a więc liczone do dnia eksportu, a nie do snapszotu | 11 404 / 11 404 tam, gdzie da się przypisać kontrahenta; 947 wierszy bez kontrahenta w ERP |
| `zaparzenia_30d` | `iot_telemetria.zaparzenia` (dzień × ekspres) | suma zaparzeń w dniach **[snapszot, snapszot + 30)**, czyli w 30 dniach *po* snapszocie | 12 346 / 12 346; 5 wierszy bez telemetrii |
| `trend_zaparzen` | `iot_telemetria.zaparzenia` | definicji nie udało się odtworzyć dokładnie. Najsilniej koreluje z ilorazem „30 dni przed snapszotem / 30 dni wcześniej” (Spearman 0,86), a z ilorazem „30 dni po / 30 dni przed” tylko 0,26. Najpewniej liczony z danych sprzed snapszotu | — |

Dodatkowo cechy `dni_od_ostatniego_zamowienia`, `zgloszenia_odbior_ekspresu`, `rabat_retencyjny_max` i `status_crm`
mają w każdym biurze tę samą wartość we wszystkich snapszotach (0 z 1 793 biur ma różne wartości). To widać bez żadnej
rekonstrukcji: policzono je raz, na dzień eksportu.

### 6.2 Data rekordu względem daty wypowiedzenia

Wypowiedzenie złożyło 261 biur, każde jedno (`crm_umowy_historia`, `typ = 'wypowiedzenie'`). Dla każdego biura liczę
**różnicę = data rekordu źródłowego − data wypowiedzenia**, w dniach. Wynik ujemny oznacza rekord sprzed wypowiedzenia,
a dodatni rekord, który powstał już po nim.

Datą rekordu jest:
- `dni_do_konca_umowy`: `data_konca_umowy`, którą CRM wpisuje przy wypowiedzeniu (koniec następnego miesiąca);
- `status_crm`: dzień, w którym status zmienia się na `zakończony` (`data_konca_umowy + 1`);
- `zgloszenia_odbior_ekspresu`: data utworzenia zgłoszenia;
- `rabat_retencyjny_max`: data kontaktu AM z rabatem > 0;
- `dni_od_ostatniego_zamowienia`: data ostatniej faktury z kawą;
- `zaparzenia_30d`: ostatni dzień, w którym ekspres coś zaparzył.

| Cecha | Biura z rekordem | Przed wypowiedzeniem | Po wypowiedzeniu | Min | Mediana | Maks |
|---|---:|---:|---:|---:|---:|---:|
| `dni_do_konca_umowy` | 261 | 0 | **261** | +30 | +46 | +60 |
| `status_crm` (`zakończony`) | 241 | 0 | **241** | +31 | +47 | +61 |
| `zgloszenia_odbior_ekspresu` | 251 | 0 | **251** | +1 | +10 | +20 |
| `rabat_retencyjny_max` | 192 | 0 | **192** | +1 | +14 | +25 |
| `dni_od_ostatniego_zamowienia` | 239 | 189 (+3 w tym samym dniu) | 47 | −666 | −52 | +30 |
| `zaparzenia_30d` (ostatnie zaparzenie) | 252 | 34 | 218 | −144 | +42 | +60 |

Rozkład różnicy w przedziałach (liczba biur):

| Cecha | < −90 | −90…−31 | −30…−1 | 0 | 1…30 | 31…61 | > 61 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `dni_do_konca_umowy` | 0 | 0 | 0 | 0 | 1 | 260 | 0 |
| `status_crm` | 0 | 0 | 0 | 0 | 0 | 241 | 0 |
| `zgloszenia_odbior_ekspresu` | 0 | 0 | 0 | 0 | 251 | 0 | 0 |
| `rabat_retencyjny_max` | 0 | 0 | 0 | 0 | 192 | 0 | 0 |
| `dni_od_ostatniego_zamowienia` | 95 | 40 | 54 | 3 | 47 | 0 | 0 |
| `zaparzenia_30d` | 6 | 20 | 8 | 0 | 25 | 193 | 0 |

Do 261 brakuje biur, które nie mają danego rekordu. 20 biur jest jeszcze `w wypowiedzeniu`, 10 nie zgłosiło odbioru
ekspresu, 69 nie dostało rabatu, a 22 nie mają faktury z kawą przypisanej przez `mapa_kontrahentow`.

**Sprawdzenie na wierszach agencji.** W 436 wierszach z jedynką cecha `zgloszenia_odbior_ekspresu` liczy 426
zgłoszeń, a `rabat_retencyjny_max` 318 kontaktów z rabatem. **Wszystkie powstały po dniu snapszotu.** W całym zbiorze
agencji (12 346 wierszy) nie ma ani jednego zgłoszenia odbioru ani rabatu retencyjnego sprzed snapszotu. Liczone
uczciwie, obie cechy byłyby stałą równą 0.

**Zaparzenia wokół wypowiedzenia.** Średnia dzienna liczba zaparzeń w biurach, które złożyły wypowiedzenie, w
tygodniach względem daty wypowiedzenia:

| Tydzień | −12 | −8 | −4 | −1 | 0 | 1 | 2 | 4 | 6 | 8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Zaparzeń dziennie | 37,4 | 31,1 | 29,6 | 28,9 | 22,9 | 21,7 | 20,9 | 18,9 | 19,6 | 22,3 |

Korzystanie z ekspresu spada stopniowo już w trzech miesiącach przed wypowiedzeniem (z 37 do 29 dziennie). To uczciwy
sygnał. Wyraźny skok w dół następuje dopiero w tygodniu wypowiedzenia, a ekspres przestaje parzyć przy końcu umowy,
31–61 dni po wypowiedzeniu. Okno agencji „30 dni po snapszocie” obejmuje u wielu jedynek właśnie ten okres po
wypowiedzeniu.

**Odejścia bez wypowiedzenia** (brak odnowienia, 276 biur) wyglądają tak samo względem daty końca umowy. Zgłoszenie
odbioru ekspresu (265 biur) i rabat retencyjny (189 biur) zawsze pojawiają się 2–20 dni po terminie odnowienia.
Ostatnie zamówienie kawy i ostatnie zaparzenie wypadają zawsze przed nim.

### 6.3 Pięć przykładowych biur

Losowe biura z wypowiedzeniem i jedynką w wierszach agencji. Liczba w nawiasie to dni względem wypowiedzenia.

| | 10329 | 10442 | 10579 | 10843 | 11004 |
|---|---|---|---|---|---|
| Snapszot | 2024-10-01 | 2026-01-01 | 2025-04-01 | 2025-01-01 | 2025-07-01 |
| **Wypowiedzenie** | **2024-11-27** | **2026-01-25** | **2025-05-04** | **2025-01-06** | **2025-07-17** |
| Ostatnia faktura z kawą | 2024-07-31 (−119) | 2026-01-30 (+5) | 2024-11-29 (−156) | 2024-06-28 (−192) | 2025-01-31 (−167) |
| Zgłoszenie odbioru ekspresu | 2024-12-06 (+9) | 2026-02-04 (+10) | 2025-05-21 (+17) | 2025-01-25 (+19) | 2025-08-04 (+18) |
| Rabat retencyjny | 2024-12-09 (+12) | 2026-02-07 (+13) | 2025-05-27 (+23) | 2025-01-22 (+16) | 2025-07-26 (+9) |
| Koniec umowy (`data_konca_umowy`) | 2024-12-31 (+34) | 2026-02-28 (+34) | 2025-06-30 (+57) | 2025-02-28 (+53) | 2025-08-31 (+45) |
| Ostatnie zaparzenie | 2024-12-30 (+33) | 2026-02-28 (+34) | 2025-03-26 (−39) | 2025-02-28 (+53) | 2025-08-27 (+41) |
| `dni_od_ostatniego_zamowienia`: agencja → do snapszotu | 791 → 62 | 243 → 1 | 670 → 123 | 824 → 187 | 607 → 151 |
| `zaparzenia_30d`: agencja (30 dni po) → 30 dni przed | 408 → 825 | 1 168 → 964 | 0 → 1 | 120 → 7 | 0 → 2 |
| `status_crm` u agencji | `zakończony` | `zakończony` | `zakończony` | `zakończony` | `zakończony` |
| Odbiór / rabat u agencji | 1 / 10% | 1 / 20% | 1 / 10% | 1 / 10% | 1 / 10% |

We wszystkich pięciu biurach zgłoszenie odbioru i rabat pojawiają się 9–23 dni po wypowiedzeniu, a więc po snapszocie.
Mimo to agencja przypisuje je do snapszotu. Biuro 10442 złożyło ostatnie zamówienie kawy dzień przed snapszotem
(2025-12-31), a agencja podaje 243 dni bez zamówienia.

### 6.4 Prostym językiem

- **`dni_do_konca_umowy`**: data końca umowy w CRM zmienia się w dniu wypowiedzenia na koniec następnego miesiąca.
  Agencja wzięła datę z dnia eksportu, więc biuro, które *za dwa miesiące* złoży wypowiedzenie, ma w snapszocie już
  „krótką” umowę. To jak sprawdzanie wyniku meczu przed jego rozegraniem. **Powstaje po wypowiedzeniu.**
- **`status_crm`**: „zakończony” pojawia się w dniu końca umowy, 1–2 miesiące po wypowiedzeniu. W dniu snapszotu każde
  biuro z populacji miało aktywną umowę. **Powstaje po wypowiedzeniu.**
- **`zgloszenia_odbior_ekspresu`**: biuro prosi o odbiór ekspresu 1–20 dni *po* wypowiedzeniu, bo już odchodzi. To
  skutek odejścia, a nie jego zapowiedź. Przed snapszotem takiego zgłoszenia nie ma nigdzie. **Powstaje po
  wypowiedzeniu.**
- **`rabat_retencyjny_max`**: AM proponuje rabat retencyjny 1–25 dni *po* wypowiedzeniu, żeby zatrzymać klienta. Przed
  snapszotem takiego rabatu nie ma nigdzie. **Powstaje po wypowiedzeniu.**
- **`dni_od_ostatniego_zamowienia`**: samo zamówienie jest uczciwe, bo zwykle pada przed wypowiedzeniem (mediana 52
  dni wcześniej). Błąd polega na tym, że agencja liczy dni do 30 września 2026, a nie do dnia snapszotu. Biuro, które
  odeszło, nie zamawia od miesięcy, a aktywne zamówiło we wrześniu, więc cecha w praktyce mówi „czy biuro jest dziś
  klientem”. **Da się przeliczyć uczciwie:** dni od ostatniego zamówienia kawy *przed* snapszotem.
- **`zaparzenia_30d`**: telemetria jest uczciwa (i spada już przed wypowiedzeniem), ale agencja zsumowała 30 dni *po*
  snapszocie. **Da się przeliczyć uczciwie:** 30 dni przed snapszotem, i to wyłącznie dane już dostarczone, bo
  telemetria przychodzi z 2-dniowym opóźnieniem (`data_dostarczenia = data + 2`).
- **`trend_zaparzen`**: wygląda na liczony z danych sprzed snapszotu, ale definicji nie odtworzyłem dokładnie, więc nie
  mogę tego potwierdzić. **Bezpieczniej przeliczyć** z jawną definicją.

### 6.5 Inne kroki liczone na całym zbiorze albo na stanie z dnia eksportu

- **`miasto_te`** to średnia `odejdzie_90d` w mieście policzona na **wszystkich 12 351 wierszach**, także testowych
  (12 351 / 12 351 zgodnych). Model widzi więc fragment etykiety testu. Kodowanie trzeba liczyć tylko na zbiorze
  uczącym, a na nim w foldach, żeby wiersz nie widział własnej etykiety.
- **`plan`, `cena_mies`, `liczba_pracownikow`, `am_id`, `miasto`, `branza`** pochodzą z `crm_biura`, czyli ze stanu
  z dnia eksportu, i są stałe we wszystkich snapszotach biura. `plan` i `cena_mies` da się odtworzyć na dzień
  snapszotu z `crm_umowy_historia`. Plan z eksportu różni się od planu w dniu snapszotu w 1 409 wierszach (19
  jedynek, głównie po późniejszym downgradzie), a cena w 10 249. Dla `liczba_pracownikow`, `am_id`, `miasto` i
  `branza` historii nie ma.
- **`kontakty_am_90d`** policzono uczciwie: 90 dni przed snapszotem, 12 351 / 12 351 zgodnych. `staz_mies`
  (`(data_migawki − data_startu) / 30,44`) też jest liczony na dzień snapszotu. `bledy_60d` zgadza się z oknem 60 dni
  przed snapszotem w 9 319 wierszach (75%). `awarie_60d`, `nps_ostatni` i `sr_opoznienie_platnosci` nie były
  sprawdzane.

## 7. Decyzje

✅ **Decyzja 2026-10-12: zgoda na wszystkie propozycje.** Wdrożenie: sekcja 8.

| Cecha | Kiedy powstaje rekord | Propozycja | Decyzja |
|---|---|---|---|
| `dni_do_konca_umowy` | po wypowiedzeniu | usunąć; zamiast niej `dni_do_rocznicy`: dni do najbliższej rocznicy `data_startu` na dzień snapszotu | zgoda |
| `status_crm` | po wypowiedzeniu | usunąć. Na dzień snapszotu wszystkie biura z populacji mają umowę aktywną, a zawieszenia nie da się odtworzyć, bo brak daty wznowienia | zgoda |
| `zgloszenia_odbior_ekspresu` | po wypowiedzeniu | usunąć (liczona uczciwie byłaby zawsze 0) | zgoda |
| `rabat_retencyjny_max` | po wypowiedzeniu | usunąć (liczona uczciwie byłaby zawsze 0) | zgoda |
| `dni_od_ostatniego_zamowienia` | przed wypowiedzeniem; zły dzień odniesienia | przeliczyć: `data_snapszotu − ostatnia faktura z kawą przed snapszotem` | zgoda |
| `zaparzenia_30d` | okno po snapszocie | przeliczyć: suma z 30 dni przed snapszotem, tylko wiersze z `data_dostarczenia < data_snapszotu` | zgoda |
| `trend_zaparzen` | nie odtworzono | przeliczyć: zaparzenia z ostatnich 30 dni / z 30 dni wcześniej (te same zasady dostarczenia) | zgoda |
| `miasto_te` | kodowanie na całym zbiorze | liczyć tylko na zbiorze uczącym (w foldach) wewnątrz modelu | zgoda |
| `plan`, `cena_mies` | stan z eksportu | przeliczyć na dzień snapszotu z `crm_umowy_historia` | zgoda |
| `liczba_pracownikow`, `am_id`, `miasto`, `branza` | stan z eksportu, brak historii | zostawić z adnotacją (nie widać, by przeciekały: AUC 0,48–0,54) | zgoda |
| pozostałe czasowe (`bledy_60d`, `awarie_60d`, `kontakty_am_90d`, `nps_ostatni`, `sr_opoznienie_platnosci`) | do sprawdzenia | przeliczyć samemu z danych sprzed snapszotu, zamiast brać z tabeli agencji | zgoda |

## 8. Wdrożenie decyzji

Cechy są w [`api/api/ai/features/cechy_snapszotu.sql`](../api/api/ai/features/cechy_snapszotu.sql) (wczytuje je
`cechy.py`). Liczą się dla każdego wiersza `snapshoty` (41 190), tylko z rekordów sprzed dnia snapszotu. Model to
[`versions/v2_bez_przeciekow/`](../api/api/ai/churn_model/versions/v2_bez_przeciekow/), a wyniki opisuje
[`evals/v2_bez_przeciekow.md`](../api/api/ai/churn_model/evals/v2_bez_przeciekow.md).

| Decyzja | Jak wdrożona |
|---|---|
| usunąć 4 cechy powstające po wypowiedzeniu | nie ma ich w SQL ani w modelu; test `test_brak_cech_z_przeciekiem` |
| `dni_do_rocznicy` zamiast `dni_do_konca_umowy` | najbliższa rocznica `data_startu` ≥ dnia snapszotu (start 29.02 → 28.02 w latach nieprzestępnych) |
| `dni_od_ostatniego_zamowienia` | dzień snapszotu − ostatnia faktura z kawą (indeks `10.*`) sprzed snapszotu; kontrahent przez `mapa_kontrahentow` |
| `zaparzenia_30d`, `trend_zaparzen`, `bledy_60d` | okna `[d − 32, d − 3]`, `[d − 62, d − 33]` i `[d − 62, d − 3]`, tylko wiersze z `data_dostarczenia < d` |
| `plan`, `cena_mies` | ostatnie zdarzenie `crm_umowy_historia` sprzed snapszotu. Cena jest pusta, gdy zdarzenie jest starsze niż 366 dni: historia odnowień zaczyna się w 2024, a odnowienie zmienia cenę |
| pozostałe cechy czasowe | `awarie_60d` w `[d − 60, d)`, `kontakty_am_90d` w `[d − 90, d)`, `nps_ostatni` z ostatniej odpowiedzi sprzed d, `sr_opoznienie_platnosci` z płatności w `[d − 90, d)` (termin 14 dni) |
| `miasto_te` tylko na zbiorze uczącym | liczone w modelu (`api/api/ai/features/kodowanie_celu.py`): poza foldem, 5 foldów po biurach; test `test_wiersz_uczacy_nie_widzi_etykiety_swojego_biura` |
| cechy z CRM bez historii | `liczba_pracownikow`, `am_id`, `miasto`, `branza` bez zmian, z adnotacją w SQL |

**Przegląd innych kroków liczonych na całym zbiorze:**
- Kodowanie kategorii `plan`, `branza` i `miasto` w LightGBM uczy się na zbiorze uczącym, a nowe dane są mapowane na
  kategorie z uczenia. Model nie skaluje cech i nie uzupełnia braków (LightGBM obsługuje braki sam), więc nie ma tu
  statystyk z całego zbioru.
- `mapa_kontrahentow` jest budowana na całym ERP, ale nie korzysta z etykiety. To scalanie duplikatów, a nie uczenie.
- Mediana do uzupełnienia braków w sekcji 2 była liczona na całym zbiorze. Służyła tylko do analizy, model jej nie używa.
- Losowy podział wierszy wpuszcza to samo biuro do części uczącej i testowej. Dla porównywalności z v0 został
  głównym sposobem oceny, ale v2 ma też AUC przy podziale w czasie.

**Wynik:** AUC spada z 0,9999 do **0,812** przy losowym podziale i do **0,799** przy podziale w czasie. v0 przy
podziale w czasie ma nadal 0,9995, więc wynik agencji tworzyły cechy, a nie podział. Żadna cecha v2 nie ma AUC samej
cechy powyżej 0,76.
