# Reguły jakości danych: POS, ERP, e-commerce

Cel: błędy z [`skala_problemu.md`](skala_problemu.md) mają nie wracać co noc. Poniżej 37 reguł, które po każdym ładowaniu sprawdzają nowe dane z POS (11), ERP (14) i e-commerce (12). Każda reguła ma poziom (blokuje albo ostrzega), właściciela i numer pozycji ze `skala_problemu.md`, którą łapie.

- **Kod:** [`api/api/data_platform/reguly/`](../api/api/data_platform/reguly/), po jednym pliku na źródło: `pos.py`, `erp.py`, `ecom.py`. Wspólny kształt reguły jest w `regula.py`, uruchomienie w `uruchom.py`, a raport w Markdown w `raport.py`.
- **Budowa reguły:** zapytanie SQL do `kawosz.duckdb` przygotowuje ramkę (złączenia i agregaty liczy DuckDB), a schemat Pandery (`DataFrameSchema`) ją sprawdza. Poziom, właściciel, jednostka rekordu i pozycje ze skali są w `metadata` schematu.
- **Testy:** [`api/tests/data_platform/reguly/`](../api/tests/data_platform/reguly/). Każda reguła ma co najmniej jeden mały przykład danych, który ją łamie, i test, że go łapie (szczegóły niżej).
- **Raport naruszeń za wrzesień 2026:** [`naruszenia_2026-09.md`](naruszenia_2026-09.md).
- **Wyniki w tym dokumencie** pochodzą z `kawosz.duckdb` (dane do 30.09.2026).

## Jak uruchomić

Co noc, po `load_raw`, dla dnia eksportu:

```bash
PYTHONPATH=api poetry run python -m api.data_platform.reguly.uruchom --dzien 2026-09-30
```

- Kod wyjścia 1 oznacza, że nie przeszła co najmniej jedna reguła blokująca. Orkiestrator nie publikuje wtedy danych z tej nocy.
- Bez `--dzien` runner sprawdza wczorajszy dzień.
- Przegląd okresu: `--od 2026-09-01 --dzien 2026-09-30`. Wybór źródeł: `--zrodlo pos erp`. Wybór reguł: `--regula POS-02 ERP-06`. Inny plik bazy: `--baza ścieżka.duckdb`.
- Dla każdej reguły, która nie przeszła, runner wypisuje naruszone warunki z liczbą wierszy i trzy przykładowe wiersze.
- `--raport plik.md` zapisuje raport naruszeń w Markdown: dla każdej reguły liczbę rekordów, naruszone warunki, 5 przykładów i informację, czy blokuje wsad. Tak powstał [`naruszenia_2026-09.md`](naruszenia_2026-09.md).
- Wszystkie naruszenia są zbierane naraz. Każda reguła sprawdza wszystkie wiersze (Pandera `lazy=True`), a runner uruchamia wszystkie reguły. Jeśli reguły nie da się wykonać (np. brak tabeli), runner zapisuje błąd i przechodzi do następnej. Reguła blokująca, której nie udało się sprawdzić, blokuje wsad.

**Zakres jednej nocy:**
- Reguły biorą dane z dnia eksportu w czasie Europe/Warsaw:
  - POS: dzień z `data_czas`, a dla pozycji z numeru paragonu;
  - ERP: `data` dokumentu;
  - e-commerce: `data_utc` przeliczone na czas polski.
- Kartotekę i kontrahentów sprawdzamy tylko w zakresie, którego dotyczą dokumenty z tej nocy.
- Pusty zakres (np. dzień bez korekt) oznacza, że nie ma czego sprawdzać. Brak całego dnia łapią reguły świeżości.

## Poziomy

- **Blokuje:** dane z nocy dałyby złą liczbę w raporcie przychodu, a potok nie może tego sam obejść. Dotyczy to:
  - duplikatów i braków danych;
  - niespójnego klucza lub złączenia;
  - sumy nagłówka niezgodnej z pozycjami;
  - kwoty, której nie da się przeliczyć (brak kursu);
  - błędnej ceny;
  - sprzedaży bez kategorii;
  - dokumentu na zdublowanego kontrahenta.

  Dane z tej nocy nie trafiają do raportów, dopóki właściciel nie poprawi źródła.
- **Ostrzega:** dane idą dalej, a właściciel dostaje listę wierszy. Dotyczy to sytuacji, w których:
  - błąd dotyczy atrybutu do analiz, a nie kwoty (e-mail, ID z CRM, NIP, nazwa, metoda płatności);
  - wiersz trzeba ocenić ręcznie (faktura 330 tys. zł, stawka VAT, nietypowy wolumen);
  - potok może błąd odfiltrować sam (zamówienia testowe rozpoznają trzy zgodne sygnały);
  - system źródłowy nie ma jeszcze potrzebnego pola (data zwrotu, faktura korygowana, paragon stornowany, płatność kartą podarunkową).

## Właściciele

Właściciel to rola, której trzeba przypisać konkretną osobę.

| Właściciel | Odpowiada za |
|---|---|
| Zespół danych | ładowanie, klucze, złączenia, sumy nagłówków z pozycjami, świeżość i wolumen |
| Operacje lokali (POS) | treść paragonów: ceny, metoda płatności, zwroty, storna |
| E-commerce | treść zamówień, cennik sklepu, subskrypcje, karty podarunkowe |
| Finanse i księgowość | dokumenty ERP, VAT, NIP, korekty, nietypowe faktury |
| Dane podstawowe (kartoteka ERP) | kategorie i nazwy indeksów |
| Sprzedaż B2B (kontrahenci) | rekordy kontrahentów: duplikaty i powiązanie z CRM |

## Spis reguł

Kolumna „IX 2026” podaje, ile jednostek nie przeszło reguły przy sprawdzeniu całego września. Nocne uruchomienie daje te same błędy, tylko rozłożone na dni.

### POS (`pos.py`)

| Reguła | Co sprawdza | Poziom | Właściciel | Pozycja ze `skala_problemu.md` | IX 2026 |
|---|---|---|---|---|---|
| POS-01 | Typy: paragon ma dokładnie oczekiwane kolumny i typy, a storno (0/1), kanał i metoda płatności mają wartości ze słowników | blokuje | Zespół danych | zapobiegawcza: nowa lub zmieniona kolumna w pliku z kasy | 0 |
| POS-02 | Unikalność: para (`lokal`, `nr_paragonu`) występuje raz | blokuje | Zespół danych | #15 zdublowane pliki paragonów | 988 paragonów |
| POS-03 | Spójność: plik ma nazwę `pos_paragony_{lokal}_{dzień}.csv`, data w numerze = data paragonu, numeracja w dniu rośnie z czasem (bez storn) | blokuje | Zespół danych | #15 (pliki „(1)”), #24 (paragon 48 000 zł ma numer poza kolejnością) | 988 paragonów |
| POS-04 | Brutto nagłówka i pozycji: suma `kwota_brutto` lokalu w dniu = Σ `ilosc × cena_brutto`, a liczba paragonów = liczba paragonów w pozycjach | blokuje | Zespół danych | #15, #25 (test sum w potoku) | 3 lokalo-dni |
| POS-05 | Powiązania: paragon ma pozycje, pozycja ma paragon i produkt z `pos_produkty`, lokal jest w `lokale` i był już otwarty | blokuje | Zespół danych | zapobiegawcza (dziś 0 sierot) | 0 |
| POS-06 | Zakresy: cena i stawka VAT pozycji są z cennika, cena ręczna (`P0999`) do 500 zł, ilość niezerowa i najwyżej 20 sztuk | blokuje | Operacje lokali (POS) | #24 paragon 48 000 zł; #3 (stawka VAT pozwala policzyć netto POS) | 0 |
| POS-07 | Paragon ma metodę płatności | ostrzega | Operacje lokali (POS) | #21 paragony bez metody płatności | 14 paragonów |
| POS-08 | Paragon z pozycją o ujemnej ilości albo z ujemną kwotą (zwrot, anulowanie) ma `storno = 1`, a storno ma ujemną kwotę. Łapie też paragon „zakup + zwrot” z dodatnią sumą | ostrzega | Operacje lokali (POS) | #22 zwroty bez flagi storno | 3 paragony |
| POS-09 | Storno wskazuje numer paragonu, który stornuje (kolumna `nr_paragonu_stornowanego`) | ostrzega | Operacje lokali (POS) | #19 storna bez powiązania | 134 storna (brak kolumny) |
| POS-10 | Świeżość: każdy otwarty lokal przysłał paragony za każdy dzień do dnia eksportu, z wyjątkiem 1.01, Wielkanocy i 25.12 | blokuje | Zespół danych | zapobiegawcza: brak pliku zaniża przychód | 0 |
| POS-11 | Liczba wierszy: paragony lokalu w dniu = 0,4–1,8 × mediana tego lokalu z 28 poprzednich dni | ostrzega | Zespół danych | #15 (dzień zdublowany ma ok. 2 ×) | 3 lokalo-dni |

### ERP (`erp.py`)

| Reguła | Co sprawdza | Poziom | Właściciel | Pozycja ze `skala_problemu.md` | IX 2026 |
|---|---|---|---|---|---|
| ERP-01 | Typy i unikalność: oczekiwane kolumny i typy, unikalny `nr_faktury` w formacie `FV/RRRR/MM/NNNNN` lub `KOR/RRRR/MM/NNNN` zgodnym z datą i typem, waluta PLN, faktura > 0, korekta < 0 | blokuje | Finanse i księgowość | zapobiegawcza | 0 |
| ERP-02 | Netto i brutto: VAT ma znak netto i nie przekracza 23%, płatność = netto + VAT, najwyżej jedna płatność, nie wcześniej niż faktura | blokuje | Finanse i księgowość | #3 (pilnuje, że brutto ERP = netto + VAT) | 0 |
| ERP-03 | VAT dokumentu = Σ netto pozycji × stawka indeksu; stawki inne niż 23% wpisuje księgowość w `STAWKI_VAT_INDEKSOW` (dziś: mleko UHT `20.01.0001` → 5%) | ostrzega | Finanse i księgowość | #12 VAT 23% na mleko UHT | 991 dokumentów |
| ERP-04 | Netto nagłówka i pozycji: `kwota_netto` = Σ `ilosc × cena` (±1 gr) | blokuje | Zespół danych | #25 (test sum w potoku) | 0 |
| ERP-05 | Powiązania: dokument ma pozycje, indeksy pozycji są w kartotece, kontrahent jest w dokładnie jednej z tabel (aktywni albo archiwum), pozycje i płatności mają dokument | blokuje | Zespół danych | #32 (kontrahenta trzeba szukać w obu tabelach) | 0 |
| ERP-06 | Indeks sprzedany na dokumencie ma kategorię w kartotece | blokuje | Dane podstawowe (kartoteka ERP) | #1 indeksy bez kategorii | 789 pozycji, 1 729 040,13 zł netto |
| ERP-07 | Nazwa sprzedanego indeksu nie powtarza się pod innym indeksem | ostrzega | Dane podstawowe (kartoteka ERP) | #20 zdublowane nazwy w kartotece | 3 pozycje |
| ERP-08 | Dokument trafia na główny (najstarszy) rekord kontrahenta, a nie na drugi rekord tej samej firmy o tym samym NIP-ie (cyfry) lub adresie z kodem | blokuje | Sprzedaż B2B (kontrahenci) | #4 zdublowani kontrahenci; #27 (bez duplikatów złączenie po NIP-ie nie dubluje faktur) | 58 dokumentów, 224 529,31 zł netto |
| ERP-09 | NIP kontrahenta ma 10 cyfr i poprawną sumę kontrolną | ostrzega | Finanse i księgowość | #14 NIP-y bez 10 cyfr | 13 dokumentów |
| ERP-10 | Kontrahent ma `id_biura_crm` i jest jedynym kontrahentem z tym ID | ostrzega | Sprzedaż B2B (kontrahenci) | #2 kontrahenci bez ID z CRM; #4 (ID z CRM przy dwóch rekordach) | 164 dokumenty (148 bez ID, 16 z ID przy dwóch rekordach) |
| ERP-11 | Zakres: faktura nie przekracza 8 × mediany faktur klienta z poprzednich 365 dni (przy co najmniej 3 fakturach) | ostrzega | Finanse i księgowość | #23 faktura na 330 885,20 zł | 0 (w historii 1: ta faktura) |
| ERP-12 | Korekta wskazuje fakturę, którą koryguje (kolumna `nr_faktury_korygowanej`) | ostrzega | Finanse i księgowość | #16 korekty bez faktury pierwotnej | 37 korekt (brak kolumny) |
| ERP-13 | Świeżość: ostatnia płatność nie starsza niż 5 dni, ostatni dokument nie starszy niż 35 dni | blokuje | Zespół danych | zapobiegawcza | 0 |
| ERP-14 | Liczba wierszy: po ostatnim dniu roboczym miesiąca liczba faktur = 0,9–1,1 × mediana z 3 poprzednich miesięcy | ostrzega | Finanse i księgowość | zapobiegawcza: brak hurtowych faktur z końca miesiąca | 0 |

### E-commerce (`ecom.py`)

| Reguła | Co sprawdza | Poziom | Właściciel | Pozycja ze `skala_problemu.md` | IX 2026 |
|---|---|---|---|---|---|
| ECOM-01 | Typy i unikalność: oczekiwane kolumny i typy, unikalne `id`, brutto > 0, waluta PLN/EUR, metoda płatności ze słownika, pobranie tylko w PLN | blokuje | Zespół danych | zapobiegawcza | 0 |
| ECOM-02 | Brutto nagłówka i pozycji: `brutto` = Σ `ilosc × cena_brutto` (z dostawą) | blokuje | Zespół danych | #25 (test sum w potoku) | 0 |
| ECOM-03 | Powiązania: zamówienie ma pozycje, pozycja ma zamówienie, SKU jest w `ecom_produkty` (wyjątek: najwyżej jeden wiersz `DOSTAWA`) | blokuje | Zespół danych | #30 (`DOSTAWA` jest poza cennikiem, więc złączenie z cennikiem musi być LEFT JOIN) | 0 |
| ECOM-04 | Zamówienie w EUR ma kurs NBP z poprzedniego dnia roboczego, nie starszy niż 7 dni, w zakresie 3,5–5,5 | blokuje | Zespół danych | #13 EUR bez przeliczenia; #33 brak kursu z przełomu 2023/2024 | 0 (w historii 15 zamówień) |
| ECOM-05 | Zamówienie nie jest testowe: e-mail spoza `@kawosz.pl`, bez notatki testowej, ceny PLN z cennika | ostrzega | E-commerce | #18 zamówienia testowe | 74 zamówienia |
| ECOM-06 | Zamówienie ma poprawny e-mail klienta, także przy pobraniu | ostrzega | E-commerce | #9 zamówienia bez e-maila | 761 zamówień |
| ECOM-07 | Zamówienie ze zwrotem ma datę i kwotę zwrotu (kolumny `data_zwrotu`, `kwota_zwrotu`) | ostrzega | E-commerce | #7 zwroty bez daty i kwoty | 1 014 zamówień (brak kolumn) |
| ECOM-08 | Sprzedany produkt ma nazwę, której nie nosi inny SKU | ostrzega | E-commerce | #6 zdublowane nazwy produktów | 2 974 pozycje |
| ECOM-09 | Subskrypcje: kwota = cena planu (39 / 399), jedno obciążenie na subskrybenta w miesiącu, czas zapisu w UTC (godziny 22–01 nocnego batcha) | blokuje | E-commerce | #17 (pilnuje, że `data_platnosci` jest w UTC, więc przeliczenie na czas polski jest poprawne) | 0 |
| ECOM-10 | Każda realizacja karty podarunkowej ma tego dnia płatność „karta podarunkowa” w POS lub w sklepie | ostrzega | E-commerce | #31 realizacja karty niewidoczna w transakcjach | 30 dni, 396 realizacji |
| ECOM-11 | Świeżość: każdy dzień do dnia eksportu ma zamówienia do co najmniej 22:00 czasu polskiego i obciążenia subskrypcji | blokuje | Zespół danych | #17 (dzień ucięty na granicy UTC) | 0 |
| ECOM-12 | Liczba wierszy: zamówienia w dniu = 0,3–3,5 × mediana z 28 poprzednich dni | ostrzega | Zespół danych | zapobiegawcza | 0 |

## Co reguły znajdują dziś

### Noc 30.09.2026

Runner kończy się kodem 1. Blokują dwie reguły:
- **ERP-06:** 776 pozycji z faktur z 30.09 bez kategorii;
- **ERP-08:** 57 dokumentów wystawionych na zdublowanych kontrahentów.

Ostrzega 11 reguł: POS-08, POS-09, ERP-03, ERP-07, ERP-09, ERP-10, ERP-12, ECOM-06, ECOM-07, ECOM-08, ECOM-10.

### Każda noc września

Reguły uruchomione osobno dla każdego dnia września zablokowałyby 14 z 30 nocy:
- **ERP-06:** 12 nocy, bo faktury ze środka miesiąca też mają indeksy bez kategorii;
- **POS-02, POS-03, POS-04:** 11–13.09, zdublowane pliki z lokalu 17;
- **ERP-08:** 25.09 i 30.09.

**Zanim ERP-06 i ERP-08 zaczną blokować, trzeba uzupełnić 24 kategorie i scalić 112 kontrahentów.** W przeciwnym razie ERP będzie zablokowany prawie każdej nocy. Do tego czasu można je traktować jak ostrzeżenia (decyzja w ostatniej sekcji).

### Zgodność z liczbami ze `skala_problemu.md`

Wrzesień 2026, kolumna „Rekordy (IX 2026)” ze skali:

| Pozycja | Skala | Reguła | Wynik reguły | Uwagi |
|---|---:|---|---:|---|
| #1 | 789 pozycji, 1 729 040,13 zł | ERP-06 | 789 pozycji, 1 729 040,13 zł | zgodne |
| #2 | 148 faktur | ERP-10 | 148 bez ID (+16 z ID przy dwóch rekordach) | zgodne |
| #4 | 58 dokumentów, 224 529,31 zł | ERP-08 | 58 dokumentów, 224 529,31 zł | zgodne; wszystkie na rekordach 26xxxx |
| #6 | 2 960 pozycji | ECOM-08 | 2 974 pozycje | inna granica dnia, patrz niżej |
| #7 | 1 005 zamówień | ECOM-07 | 1 014 zamówień | inna granica dnia |
| #9 | 757 zamówień | ECOM-06 | 761 zamówień | inna granica dnia |
| #12 | 991 pozycji | ERP-03 | 991 dokumentów | zgodne (każdy ma jedną pozycję mleka) |
| #14 | 13 faktur | ERP-09 | 13 dokumentów | zgodne |
| #15 | 988 paragonów | POS-02, POS-03 | 988 paragonów | zgodne; POS-04 i POS-11 wskazują 3 lokalo-dni (lokal 17, 11–13.09) |
| #16 | 37 korekt | ERP-12 | 37 korekt | zgodne |
| #18 | 73 zamówienia | ECOM-05 | 74 zamówienia | inna granica dnia |
| #19 | 134 paragony | POS-09 | 134 storna | zgodne |
| #20 | 3 pozycje | ERP-07 | 3 pozycje | zgodne |
| #21 | 14 paragonów | POS-07 | 14 paragonów | zgodne |
| #22 | 2 paragony | POS-08 | 3 paragony | skala liczy paragony z ujemną sumą; POS-08 łapie też paragon z ujemną pozycją przy dodatniej sumie (lokal 17, 21.09, +55 zł) |
| #31 | 396 realizacji, 52 500 zł | ECOM-10 | 396 realizacji, 52 500 zł (30 dni) | zgodne |

**Inna granica dnia:** skala liczy e-commerce po `data_utc`, czyli po miesiącu UTC, a reguły po dniu polskim, zgodnie z poprawką z #17. Wrzesień w czasie polskim ma 7 689 zamówień, a w UTC 7 639.

**Pozycje jednorazowe z innych miesięcy:** przebieg na całej historii (I.2024–IX.2026) łapie także:
- **#24:** paragon na 48 000 zł z 14.03.2025, przez POS-03 (numer poza kolejnością) i POS-06 (cena ręczna ponad 500 zł);
- **#23:** fakturę FV/2025/11/00007 na 330 885,20 zł, przez ERP-11 (22 × mediana klienta). To jedyna faktura w historii powyżej 8 ×; następna ma 5,6 ×;
- **#33:** 15 zamówień w EUR z 1–2.01.2024 bez kursu NBP, przez ECOM-04.

### Reguły zapobiegawcze

15 reguł nie znajduje nic w całej historii: POS-01, POS-05, POS-10, ERP-01, ERP-02, ERP-04, ERP-05, ERP-13, ERP-14, ECOM-01, ECOM-02, ECOM-03, ECOM-09, ECOM-11 i ECOM-12. Pilnują rzeczy, które dziś są w porządku, a od których zależą raporty (patrz [profil danych](profil_danych.md#1-najważniejsze-ustalenia), §1 pkt 10).

Każdą sprawdziłem na celowo zepsutych danych i każda złapała błąd. Przykłady:
- dodatkowa kolumna w pliku z kasy (POS-01);
- miesiąc w numerze faktury inny niż data (ERP-01);
- płatność o 5 gr różna od netto + VAT (ERP-02);
- zapis subskrypcji w czasie lokalnym zamiast UTC (ECOM-09);
- 250 zamiast 1 400 faktur w miesiącu (ERP-14).

Na dniu bez eksportu (5.10.2026) blokują POS-10 i ECOM-11, a na 6.10 także ERP-13.

**Progi** (0,4–1,8; 0,3–3,5; 0,9–1,1; 8 ×; 500 zł; 20 sztuk; 5 i 35 dni) dobrałem na historii I.2024–IX.2026 tak, żeby poza znanymi błędami ze skali nie było alarmów. Najbliżej granic były:
- POS-11: lokale 8 i 9 w spokojne dni, 0,43 ×;
- ECOM-12: 6.01.2026 (0,37 ×) i 1.12.2024, weekend Black Friday (3,14 ×);
- ERP-11: 5,6 ×.

## Testy

Testy leżą w [`api/tests/data_platform/reguly/`](../api/tests/data_platform/reguly/) i działają bez `kawosz.duckdb`.

- `conftest.py` buduje w pamięci małą bazę DuckDB o tych samych tabelach i typach co `kawosz.duckdb`: jeden lokal, dwa paragony, dwie faktury, dwa zamówienia, dwie subskrypcje, jedna karta. Czyste dane przechodzą wszystkie 37 reguł.
- `test_reguly_pos.py`, `test_reguly_erp.py` i `test_reguly_ecom.py` mają listę `PRZYKLADY`: zapytanie SQL, które psuje czyste dane w jeden sposób, oczekiwane naruszenie i liczbę rekordów, które reguła ma oznaczyć. Dla 37 reguł są 44 przykłady. Przykład: paragon z zakupem ziarna (+169 zł) i zwrotem latte (−1 szt.), z dodatnią sumą i `storno = 0`, musi wpaść do POS-08.
- Test `test_kazda_regula_ma_zly_przyklad` pilnuje, że nowa reguła nie przejdzie bez przykładu.
- Dla POS-09, ERP-12 i ECOM-07 jest też test odwrotny: gdy źródło doda wymagane pole, reguła przechodzi, a reguła typów (POS-01, ERP-01, ECOM-01) go nie odrzuca.
- `test_uruchom.py` sprawdza runner:
  - wszystkie naruszenia są zbierane naraz;
  - błąd jednej reguły nie przerywa pozostałych;
  - przykłady w raporcie obejmują każdy rodzaj naruszenia;
  - treść raportu jest poprawna;
  - kod wyjścia to 1 przy regule blokującej.

Uruchomienie: `pypyr test` albo `poetry run pytest api/tests`. Wynik: 95 testów przechodzi.

Celowo zepsułem kod sześć razy i za każdym razem testy to wykryły:
- POS-08 cofnięta do starej wersji, która sprawdzała tylko ujemną sumę;
- walidacja bez `lazy=True`;
- błąd SQL przerywający przebieg;
- próg ceny ręcznej podniesiony do 50 000 zł;
- ERP-08 bez sprawdzania NIP-u;
- ECOM-04 z kursem z dnia zamówienia zamiast z dnia poprzedzającego.

## Pozycje ze `skala_problemu.md` bez własnej reguły

| Pozycja | Dlaczego nie ma reguły na danych źródłowych |
|---|---|
| #3 BI sumuje brutto z netto | To definicja raportu. Reguły ERP-02 i POS-06 pilnują tylko, że netto da się policzyć. |
| #5 raporty niezgodne z opisami | To definicje i SQL raportów, a nie dane. |
| #8 sprzedaż kart jako przychód | To zasada księgowa (karta to zobowiązanie). Dane kart są poprawne. |
| #10 flaga `spor` | Najpierw trzeba ustalić z finansami, co oznacza. Dopiero wtedy wiadomo, co sprawdzać. |
| #11 plan roczny w miesiącu płatności | To sposób ujęcia przychodu (1/12). ECOM-09 pilnuje tylko, że kwota pasuje do planu. |
| #25, #26, #30, #32 złączenia w raportach | Błąd powstaje w zapytaniu raportu. Reguły POS-04, ERP-04, ERP-05, ECOM-02 i ECOM-03 pilnują tylko danych, na których złączenia są bezpieczne. Samo zapytanie wymaga testu raportu. |
| #27 łączenie po NIP-ie | Przyczynę (duplikaty) łapie ERP-08. Sam sposób łączenia to sprawa raportu. |
| #28 ruch lokalu 17 | Wymaga weryfikacji z rozliczeniami terminali. POS-11 porównuje lokal z jego własną historią, więc stałego poziomu nie oznaczy. |
| #29 faktury przeterminowane | To windykacja, a nie jakość danych. |
| #34, #35 brak numeru pozycji POS, subskrypcje bez klienta | Wymagają nowych pól w źródle i nie mają wyceny. Reguły warto dodać razem z polami, tak jak POS-09, ERP-12 i ECOM-07. |
| #36 cenniki bez historii, EUR ≈ PLN / 4 | To polityka cenowa. Nie wiadomo jeszcze, co uznać za błąd. |

## Do decyzji

1. **ERP-06 i ERP-08 jako blokujące.** Można najpierw usunąć zaległość (24 kategorie, 112 kontrahentów), a do tego czasu obniżyć je do „ostrzega”. W obecnym ustawieniu ERP byłby zablokowany prawie każdej nocy.
2. **Osoby dla ról właścicieli.**
3. **Stawka 5% dla `20.01.0001` (mleko UHT) w ERP-03.** To założenie do potwierdzenia przez księgowość, tak jak w skali (#12 „do weryfikacji”). Kartoteka nie ma kolumny ze stawką VAT. Docelowo stawka powinna być w kartotece, a nie w kodzie reguły.
4. **Reguły wymagające nowych pól:** POS-09, ERP-12, ECOM-07 i ECOM-10. Będą ostrzegać każdej nocy, dopóki dostawcy POS, ERP i sklepu nie dodadzą pól: numeru paragonu stornowanego, numeru faktury korygowanej, daty i kwoty zwrotu oraz metody „karta podarunkowa”.
5. **Wykluczanie zamówień testowych w potoku.** ECOM-05 tylko je wskazuje i nie usuwa ich ze sprzedaży.
