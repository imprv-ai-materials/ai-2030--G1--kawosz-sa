# Profil danych — POS, e-commerce, karty podarunkowe, ERP

Kontekst: dashboard BI, raport sprzedaży i księgowość podają trzy różne przychody za wrzesień 2026 (8,31 / 8,06 / 7,92 mln zł). Ten dokument **niczego nie naprawia i nie uzgadnia tych liczb**. Opisuje, co jest w tabelach źródłowych: co oznacza jeden wiersz, czy kwoty są brutto czy netto, w jakiej walucie i strefie czasowej, gdzie są braki i co wygląda podejrzanie.

- Źródło: `kawosz.duckdb` (otwarta `read_only`), dane do dnia eksportu 2026-09-30.
- Zakres: `pos_*` i `lokale`, `ecom_*`, `karty_podarunkowe`, `erp_*`. `lokale` dołączyłem, bo to słownik lokali dla POS.
- Metoda: `SUMMARIZE <tabela>` dla każdej tabeli, a następnie zapytania sprawdzające klucze, sieroty, zgodność nagłówków z pozycjami, rozkłady w czasie i wartości skrajne. Najważniejsze zapytania są na końcu każdej sekcji.
- Uwaga do `SUMMARIZE`: `approx_unique` to szacunek (HyperLogLog) i potrafi się mylić o kilkanaście procent (np. `pos_produkty.kod_produktu`: 42 wg szacunku, a naprawdę 47). Dlatego w tabelach jest też dokładna liczba wartości unikalnych.
- Kwoty podaję surowo, bez przeliczania walut i bez poprawek. Format: spacja jako separator tysięcy, przecinek dziesiętny.

## 1. Najważniejsze ustalenia

1. **Każdy system liczy inaczej.** POS i e-commerce podają kwoty brutto, ERP netto (VAT w osobnej kolumnie). E-commerce ma dwie waluty (PLN i EUR), POS i ERP tylko PLN. POS zapisuje czas lokalny, e-commerce czas UTC, a ERP i karty podarunkowe same daty bez godziny.
2. **`ecom_subskrypcje.data_platnosci` jest w UTC, choć nazwa kolumny tego nie mówi** (w `ecom_zamowienia` kolumna nazywa się `data_utc`). Subskrypcje są obciążane w nocy, między 00:00 a 02:59 czasu warszawskiego, więc obciążenia z pierwszej nocy miesiąca w UTC wypadają jeszcze w poprzednim miesiącu. We wrześniu 2026 to 172 obciążenia i 7 428 zł różnicy.
3. **POS ma zdublowane paragony.** Trzy dzienne pliki z lokalu 17 (11–13.09.2026) wczytały się dwa razy, co daje 988 paragonów i +32 684,00 zł we wrześniu. `pos_pozycje` nie ma tych duplikatów, więc suma z nagłówków i suma z pozycji różnią się dokładnie o tę kwotę.
4. **E-commerce ma 595 zamówień testowych**, w tym 73 we wrześniu 2026 (10 782,86 zł i 17,97 EUR). Rozpoznają je trzy niezależne sygnały, które pokrywają się w 100%: testowa notatka, adres e-mail w domenie `@kawosz.pl` i ceny o 17,9% wyższe od cennika.
5. **Flaga `zwrot` w e-commerce nie ma daty ani kwoty.** Stały udział ok. 13% obejmuje nawet zamówienia złożone w dniu eksportu, więc zwrotów nie da się przypisać do okresu i nie wiadomo, czy były pełne czy częściowe.
6. **Kartę podarunkową widać tylko przy sprzedaży i realizacji.** Nie wiadomo, w jakim kanale ją sprzedano i gdzie zrealizowano. Ani POS, ani e-commerce nie mają metody płatności „karta podarunkowa”, więc realizacji nie da się powiązać z transakcjami. Istnieje ryzyko, że ta sama kwota zostanie policzona raz przy sprzedaży karty i drugi raz przy realizacji.
7. **ERP ma zdublowanych kontrahentów (sekcja 10).** Wszystkie 112 rekordów z puli 26xxxx to drugie rekordy starszych klientów. 105 ma ten sam NIP zapisany inaczej, a 7 ma NIP z jedną zgubioną cyfrą. Rzeczywistych kontrahentów aktywnych jest więc 1 400, a nie 1 512. Faktury nie są dublowane (w danym miesiącu tylko jeden z dwóch rekordów dostaje fakturę), ale historia klienta jest rozbita na dwa rekordy.
8. **W `erp_kartoteka` brakuje kategorii przy 24 indeksach (6%).** To jednak indeksy takie jak „Abonament – Plan M” i „Plan XL”, więc **38% netto ERP (55,8 mln z 146,3 mln zł) nie ma kategorii.**
9. **Wartości odstające (sekcja 9):** paragon POS na 48 000,00 zł to niemal na pewno błąd wpisu ceny. Faktura ERP na 330 885,20 zł netto (40 ekspresów z instalacją) jest technicznie poprawna, ale nie potwierdza jej żaden inny system, więc jest oznaczona do weryfikacji. Żadna z nich nie dotyczy września 2026. Reguła IQR oznacza ok. 5% paragonów i 6% faktur, ale są to zwykłe zakupy detaliczne i grupowe oraz duzi klienci, a nie błędy.
10. **Dużo się zgadza i to też jest wynik.** W POS, e-commerce i ERP sumy z nagłówków zgadzają się z sumami pozycji co do grosza (w POS po odjęciu duplikatów). Nie ma sierot, a numery dokumentów są unikalne i zgodne z datami. Płatności ERP to zawsze pełna kwota brutto faktury.

## 2. Konwencje tabel w skrócie

| Tabela | 1 wiersz = | Kwoty | Waluta | Czas | Klucz (sprawdzony) |
|---|---|---|---|---|---|
| `pos_paragony` | paragon (nagłówek) z dziennego pliku kasy | brutto | PLN (brak kolumny) | lokalny, bez strefy (`TIMESTAMP`) | (`lokal`, `nr_paragonu`), z wyjątkiem 988 duplikatów |
| `pos_pozycje` | pozycja paragonu | brutto, cena jednostkowa; `vat` = stawka w % | PLN | brak daty; data zakodowana w `nr_paragonu` (RRMMDD…) | brak (ten sam produkt może być w kilku wierszach) |
| `pos_produkty` | produkt w cenniku POS | brutto | PLN | — | `kod_produktu` |
| `lokale` | lokal | — | — | `data_otwarcia` (data) | `lokal` |
| `ecom_zamowienia` | zamówienie (łącznie z dostawą) | brutto (VAT 23%) | **PLN lub EUR** (`waluta`) | **UTC** (`data_utc`, `TIMESTAMP_NS` bez strefy) | `id` |
| `ecom_pozycje` | pozycja zamówienia, w tym wiersz `DOSTAWA` | brutto, cena jednostkowa | waluta zamówienia | brak daty | brak |
| `ecom_produkty` | SKU w cenniku sklepu | brutto | PLN | — | `sku` |
| `ecom_subskrypcje` | jedno obciążenie subskrypcji | 39 / 399, wg konwencji e-commerce brutto | brak kolumny, wg konwencji PLN | **UTC** (`data_platnosci`, nazwa tego nie mówi) | (`id`, miesiąc) |
| `karty_podarunkowe` | karta podarunkowa (sprzedaż i ewentualna realizacja) | nominał | brak kolumny, wg konwencji PLN | daty bez godziny, strefa nieznana | `kod` |
| `erp_faktury` | faktura lub korekta | **netto** + `vat` jako kwota | PLN (jedyna wartość) | data lokalna bez godziny | `nr_faktury` |
| `erp_pozycje` | pozycja dokumentu | netto, cena jednostkowa | PLN | brak daty | brak |
| `erp_platnosci` | płatność za fakturę | **brutto** (= netto + VAT) | PLN | data | `nr_faktury` (1 płatność na fakturę) |
| `erp_kartoteka` | indeks towarowy | — | — | — | `indeks` |
| `erp_kontrahenci` / `_archiwum` | kontrahent z aktywną / zakończoną umową | — | — | — | `id_kontrahenta` (ale NIP-y się dublują) |

## 3. POS

### `pos_paragony`

**SUMMARIZE `pos_paragony`** — 2 100 602 wierszy

| kolumna | typ | min | max | approx_unique | unikalne (dokładnie) | null % |
|---|---|---|---|---:|---:|---:|
| lokal | INTEGER | 1 | 24 | 24 | 24 | 0,00 |
| nr_paragonu | BIGINT | 2401020001 | 2609300294 | 307 938 | 311 696 | 0,00 |
| data_czas | TIMESTAMP | 2024-01-02 07:00:16 | 2026-09-30 19:56:51 | 2 348 421 | 2 045 898 | 0,00 |
| kwota_brutto | DECIMAL(12,2) | -368,00 | 48 000,00 | 735 | 774 | 0,00 |
| metoda_platnosci | VARCHAR | BLIK | karta | 4 | 4 | 0,01 |
| storno | INTEGER | 0 | 1 | 2 | 2 | 0,00 |
| kanal | VARCHAR | aplikacja | wynos | 3 | 3 | 86,90 |
| plik | VARCHAR | pos_paragony_10_2024-01-02.csv | pos_paragony_9_2026-09-30.csv | 25 390 | 22 844 | 0,00 |

**Jeden wiersz** to nagłówek paragonu z dziennego pliku CSV kasy. `plik` to nazwa źródłowego pliku, a `nr_paragonu` ma format `RRMMDD` + 4-cyfrowy numer kolejny. Data w numerze, data w nazwie pliku i data w `data_czas` zgadzają się w 100% wierszy, a lokal z nazwy pliku zgadza się z kolumną `lokal`.

**Kwoty:** brutto, `DECIMAL(12,2)`, w PLN (tabela nie ma kolumny waluty). Paragon storno ma kwotę ujemną.

**Czas:** `TIMESTAMP` bez strefy, w czasie lokalnym kasy (Europe/Warsaw). Paragony są wystawiane między 07:00 a 19:59 (poza 8 stornami z 20:00–20:02) i w zimie, i w lecie, czyli godziny nie przesuwają się przy zmianie czasu. Gdyby zapis był w UTC, latem przesunąłby się o godzinę.

**Braki:**
- `kanal`: 86,90% NULL. To zmiana formatu, a nie braki danych. Kolumna pojawiła się w plikach od 2026-06-01 i od tego dnia jest wypełniona w 100% (sala / wynos / aplikacja).
- `metoda_platnosci`: 276 NULL (0,01%), rozłożone równomiernie w czasie. We wrześniu 2026 to 14 paragonów na 376,00 zł.
- 8 dni bez żadnego paragonu we wszystkich lokalach naraz: 1.01, Wielkanoc i 25.12. Wygląda to na zamknięcie lokali, a nie na brak plików. Pozostałe dni są kompletne dla każdego lokalu.

**Podejrzane:**
- **Duplikaty plików:** w bazie są 2 100 602 wiersze, ale tylko 2 099 614 unikalnych par (`lokal`, `nr_paragonu`). Różnica to 988 paragonów z trzech plików `pos_paragony_17_2026-09-1{1,2,3} (1).csv`, które są kopiami oryginałów (opisane w `docs/pierwsze_zapytanie.md`). Dają one +32 684,00 zł we wrześniu 2026.
- **48 000,00 zł** (lokal 5, 2025-03-14, karta) to jedna sztuka produktu `P0999` „Kawa ziarnista na wagę”, którego cena w cenniku wynosi 0,00, czyli jest wpisywana ręcznie przy kasie. To jedyna sprzedaż `P0999` w całej historii. Wygląda na błąd ręcznego wpisu. Kolejne największe paragony (2 094 i 1 745 zł) to 6 i 5 sztuk młynka ręcznego za 349 zł, więc są wiarygodne.
- **Zwroty bez flagi storno:** 198 paragonów ma ujemną kwotę i `storno = 0` (łącznie −16 309 zł w 2024–2026, z czego −88 zł we wrześniu 2026). Są to paragony mieszane: zakup napoju (+) i zwrot towaru z półki detalicznej (−1 szt.). Dodatkowo 28 pozycji z ujemną ilością trafiło do paragonów o dodatniej sumie. Zwrot nie ma więc osobnego oznaczenia.
- **Storno:** 4 100 wierszy (4 097 unikalnych paragonów) o łącznej kwocie −129 476 zł. Dla każdego storna istnieje wcześniejszy paragon z tego samego dnia i lokalu na tę samą kwotę dodatnią (w sprawdzonych przykładach kilka minut wcześniej), więc suma `kwota_brutto` sama je znosi. POS nie przechowuje jednak powiązania storna z paragonem pierwotnym, więc to parowanie opiera się tylko na kwocie. Jeśli liczymy liczbę transakcji, paragon i jego storno to dwa wiersze.
- 1 paragon na 0,00 zł (lokal 19, 2024-12-10).
- **Lokal 17** (Warszawa, Dworzec Centralny) ma ok. 313 paragonów dziennie, a pozostałe lokale średnio ok. 78, czyli prawie 4× mniej. Średnia wartość paragonu jest taka sama (31 zł). Na dworcu to możliwe, ale warto to potwierdzić, zwłaszcza że zdublowane pliki też pochodzą z tego lokalu.
- Lokale 23 i 24 otwarto 2025-03-07 i 2025-10-03, a ich paragony zaczynają się w dniu otwarcia. Ma to znaczenie przy porównaniach rok do roku.

### `pos_pozycje`

**SUMMARIZE `pos_pozycje`** — 3 197 403 wierszy

| kolumna | typ | min | max | approx_unique | unikalne (dokładnie) | null % |
|---|---|---|---|---:|---:|---:|
| lokal | BIGINT | 1 | 24 | 24 | 24 | 0,00 |
| nr_paragonu | BIGINT | 2401020001 | 2609300294 | 307 938 | 311 696 | 0,00 |
| kod_produktu | VARCHAR | P0101 | P0999 | 42 | 47 | 0,00 |
| ilosc | BIGINT | -8 | 8 | 18 | 16 | 0,00 |
| cena_brutto | DOUBLE | 8,00 | 48 000,00 | 32 | 29 | 0,00 |
| vat | BIGINT | 8 | 23 | 2 | 2 | 0,00 |

**Jeden wiersz** to pozycja paragonu. `cena_brutto` to cena jednostkowa brutto w PLN, a `vat` to stawka w procentach (8 dla napojów i jedzenia, 23 dla towarów detalicznych). Ujemna `ilosc` oznacza storno albo zwrot. Tabela nie ma daty, więc dzień trzeba odczytać z `nr_paragonu`.

**Zgodność:** dla wszystkich 2 099 614 paragonów `Σ ilosc × cena_brutto` jest równe `kwota_brutto` z nagłówka, bez wyjątku. Nie ma sierot w żadną stronę ani kodów produktów spoza `pos_produkty`. Ceny są równe cenom z cennika z jednym wyjątkiem (`P0999` za 48 000 zł).

**Braki:** brak NULL-i.

**Podejrzane:**
- `pos_pozycje` **nie zawiera** zdublowanych paragonów z lokalu 17. Dlatego sprzedaż z pozycji za wrzesień 2026 (2 154 550,00 zł) różni się od sumy nagłówków (2 187 234,00 zł) dokładnie o 32 684,00 zł duplikatów.
- 38 044 przypadki tego samego produktu w kilku wierszach jednego paragonu, np. dwa osobne wiersze „Latte ×1”. To normalne przy kasowaniu, ale (`lokal`, `nr_paragonu`, `kod_produktu`) nie jest kluczem.

### `pos_produkty`, `lokale`

**SUMMARIZE `pos_produkty`** — 47 wierszy

| kolumna | typ | min | max | approx_unique | unikalne (dokładnie) | null % |
|---|---|---|---|---:|---:|---:|
| kod_produktu | VARCHAR | P0101 | P0999 | 42 | 47 | 0,00 |
| nazwa | VARCHAR | Americano | Woda | 44 | 47 | 0,00 |
| kategoria | VARCHAR | detal | napoje | 3 | 3 | 0,00 |
| cena_brutto | DOUBLE | 0,00 | 349,00 | 33 | 29 | 0,00 |
| vat | BIGINT | 8 | 23 | 2 | 2 | 0,00 |

**SUMMARIZE `lokale`** — 24 wierszy

| kolumna | typ | min | max | approx_unique | unikalne (dokładnie) | null % |
|---|---|---|---|---:|---:|---:|
| lokal | BIGINT | 1 | 24 | 24 | 24 | 0,00 |
| nazwa | VARCHAR | Kawosz Bydgoszcz – ul. Gdańska 30 | Kawosz Łódź – ul. Piotrkowska 98 | 24 | 24 | 0,00 |
| miasto | VARCHAR | Bydgoszcz | Łódź | 10 | 9 | 0,00 |
| adres | VARCHAR | Al. Jerozolimskie 54 (Dworzec Cen… | ul. Zabłocie 23 | 20 | 24 | 0,00 |
| data_otwarcia | DATE | 2012-01-01 | 2025-10-03 | 24 | 24 | 0,00 |

- `pos_produkty`: 47 produktów w 3 kategoriach (napoje, jedzenie, detal), z ceną brutto i stawką VAT. `P0999` „Kawa ziarnista na wagę” ma cenę 0,00, czyli wpisywaną przy kasie. Cennik nie ma historii, a ceny w pozycjach są w całym okresie równe obecnemu cennikowi.
- `lokale`: 24 lokale w 9 miastach (`approx_unique` podaje 10). Brak NULL-i.

```sql
-- Duplikaty paragonów
SELECT count(*), count(DISTINCT (lokal, nr_paragonu)) FROM pos_paragony;   -- 2 100 602 vs 2 099 614

-- Nagłówek vs pozycje (na unikalnych paragonach)
WITH p AS (SELECT lokal, nr_paragonu, sum(ilosc * cena_brutto) s FROM pos_pozycje GROUP BY ALL),
     r AS (SELECT DISTINCT ON (lokal, nr_paragonu) * FROM pos_paragony)
SELECT r.kwota_brutto = p.s AS zgodne, count(*) FROM r JOIN p USING (lokal, nr_paragonu) GROUP BY 1;

-- Zwroty bez flagi storno
SELECT count(*), sum(kwota_brutto) FROM pos_paragony WHERE kwota_brutto < 0 AND storno = 0;

-- Spójność numeru paragonu z datą i nazwą pliku
SELECT strftime(data_czas, '%y%m%d') = (nr_paragonu // 10000)::varchar AS ok, count(*) FROM pos_paragony GROUP BY 1;

-- Czas lokalny: godziny otwarcia takie same zimą i latem
SELECT month(data_czas) IN (1, 12) AS zima, min(hour(data_czas)), max(hour(data_czas)) FILTER (WHERE storno = 0)
FROM pos_paragony GROUP BY 1;
```

## 4. E-commerce

### `ecom_zamowienia`

**SUMMARIZE `ecom_zamowienia`** — 220 896 wierszy

| kolumna | typ | min | max | approx_unique | unikalne (dokładnie) | null % |
|---|---|---|---|---:|---:|---:|
| id | BIGINT | 1000001 | 1220896 | 249 129 | 220 896 | 0,00 |
| data_utc | TIMESTAMP_NS | 2023-12-31 23:00:15 | 2026-09-30 21:54:21 | 288 148 | 220 466 | 0,00 |
| waluta | VARCHAR | EUR | PLN | 2 | 2 | 0,00 |
| brutto | DOUBLE | 12,19 | 1 439,19 | 2 603 | 2 816 | 0,00 |
| email | VARCHAR | aadamczyk@gmail.com | zzielinska@outlook.com | 56 527 | 54 617 | 9,78 |
| notatka | VARCHAR | Bez folii bąbelkowej, dziękuję :) | zamówienie testowe QA | 16 | 17 | 92,72 |
| zwrot | BOOLEAN | false | true | 2 | 2 | 0,00 |
| metoda_platnosci | VARCHAR | BLIK | przelew | 4 | 4 | 0,00 |

**Jeden wiersz** to zamówienie. `id` jest ciągłe (1000001–1220896, bez luk i duplikatów) i rośnie razem z czasem.

**Kwoty:** brutto (VAT 23%) **w walucie zamówienia**, łącznie z dostawą. 207 594 zamówienia są w PLN, a 13 302 (6%) w EUR. W EUR płaci się tylko kartą lub przelewem, a pobranie występuje tylko w PLN. Bez przeliczenia kursem suma miesza złote z euro.

**Czas:** UTC (`TIMESTAMP_NS` bez strefy, więc DuckDB nie wie, że to UTC). Potwierdzenie w danych: dane zaczynają się 2023-12-31 23:00:15 UTC, czyli 2024-01-01 00:00 w Warszawie, i kończą 2026-09-30 21:54 UTC, czyli 23:54 w Warszawie. Eksport jest więc ucięty o północy czasu warszawskiego. W czasie warszawskim najspokojniejsza godzina (04:00) i szczyt zamówień (20:00) są takie same zimą i latem. Wrzesień 2026 liczony w UTC to 7 639 zamówień na 677 061,42, a w czasie warszawskim 7 689 zamówień na 681 348,23 (surowo, PLN i EUR razem).

**Braki:**
- `email`: 9,78% NULL. Braki skupiają się w pobraniach: 19 123 z 20 503 zamówień za pobraniem (93%) nie ma adresu e-mail, a przy innych metodach płatności brakuje go w ok. 1% zamówień. Wygląda to na zakup bez konta przy pobraniu.
- `notatka`: 92,72% NULL. To normalne, bo to wolny tekst klienta. Ma 17 różnych wartości: 10 notatek klientów i 7 notatek testowych.

**Podejrzane:**
- **Zamówienia testowe: 595** zamówień na 64 343,69 (PLN i EUR razem), w tym **73 we wrześniu 2026** (72 w PLN na 10 782,86 i 1 w EUR na 17,97). Wskazują na nie trzy sygnały, które dają **dokładnie ten sam zbiór**:
  - 420 zamówień z notatką testową („zamówienie testowe QA”, „TEST – nie wysyłać”, „test bramki płatności, anulować”, „prosze nie realizowac (test)” itd.);
  - 175 dalszych zamówień z adresu `@kawosz.pl` (`test@`, `qa@`, `qa+NNN@`, `sklep.test@`, `jan.testowy@`) bez notatki;
  - wszystkie 595 i tylko one mają w pozycjach ceny = cennik × 1,179 (PLN) lub × ~0,295 (EUR).

  Żadne z nich nie ma flagi `zwrot`, więc wchodzą do sprzedaży jak zwykłe zamówienia.
- **`zwrot`**: 29 548 zamówień (13,4%) na 2 604 797,49. Flaga nie ma daty zwrotu ani kwoty, więc nie wiadomo, czy zwrot był pełny, ani w którym okresie go ująć. Udział jest stały w każdym miesiącu, walucie i metodzie płatności, a nawet zamówienia złożone 30.09.2026 (w dniu eksportu) mają 12,9% zwrotów. To nie wygląda na zwroty zarejestrowane później. Bardziej wygląda na flagę nadawaną przy zamówieniu albo na stan z innego dnia niż eksport. We wrześniu 2026 to 1 005 zamówień na 87 827,45 (surowo).
- 15 par zamówień ma ten sam znacznik czasu i tę samą kwotę, ale różne adresy e-mail. To zbieg okoliczności, a nie duplikaty.

### `ecom_pozycje`

**SUMMARIZE `ecom_pozycje`** — 518 082 wierszy

| kolumna | typ | min | max | approx_unique | unikalne (dokładnie) | null % |
|---|---|---|---|---:|---:|---:|
| id_zamowienia | BIGINT | 1000001 | 1220896 | 249 129 | 220 896 | 0,00 |
| sku | VARCHAR | DOSTAWA | KW-ZESTAWPR-047 | 60 | 58 | 0,00 |
| ilosc | BIGINT | 1 | 3 | 3 | 3 | 0,00 |
| cena_brutto | DOUBLE | 5,29 | 648,54 | 159 | 164 | 0,00 |

**Jeden wiersz** to pozycja zamówienia: towar albo `DOSTAWA` (14,99 PLN lub 6,90 EUR). Zamówienia, w których towar w PLN kosztuje od 115,65 zł, nie mają wiersza dostawy (darmowa wysyłka). `cena_brutto` jest **w walucie zamówienia**, a nie w PLN.

**Zgodność:** dla każdego zamówienia `Σ ilosc × cena_brutto` = `brutto` (różnice rzędu 1e-13, bo kwoty są w `DOUBLE`). Nie ma sierot w żadną stronę. Jedyny SKU spoza `ecom_produkty` to `DOSTAWA`.

**Podejrzane:**
- **Ceny w EUR nie wynikają z kursu NBP.** Cena w EUR to ok. cena PLN z cennika / 4 (stosunek 0,249–0,253), a kurs NBP w tym okresie wynosił 4,16–4,43. Przeliczenie zamówień EUR kursem NBP da więc kwoty o kilka procent wyższe niż ceny PLN z cennika. Trzeba ustalić, jakiego kursu używa księgowość.
- 923 pozycje w PLN mają cenę inną niż w cenniku. Wszystkie należą do zamówień testowych (patrz wyżej).

### `ecom_produkty`

**SUMMARIZE `ecom_produkty`** — 57 wierszy

| kolumna | typ | min | max | approx_unique | unikalne (dokładnie) | null % |
|---|---|---|---|---:|---:|---:|
| sku | VARCHAR | KW-AEROPRES-052 | KW-ZESTAWPR-047 | 58 | 57 | 0,00 |
| nazwa | VARCHAR | AeroPress Original | Zestaw prezentowy Degustacja 3×10… | 48 | 53 | 0,00 |
| cena_brutto_pln | DOUBLE | 20,92 | 648,54 | 48 | 45 | 0,00 |

- 57 SKU, ale tylko 53 różne nazwy. Cztery nazwy mają po dwa SKU z **różnymi cenami**: „Brazylia Santos – kawa ziarnista 1000 g” (107,49 i 132,02), „Etiopia Yirgacheffe 250 g” (46,17 i 40,40), „Kolumbia Huila 250 g” (41,84 i 38,96) oraz „Kenia AA 250 g” (52,66 i 49,78).
- Cennik ma tylko cenę w PLN, bez historii zmian i bez stawki VAT.

### `ecom_subskrypcje`

**SUMMARIZE `ecom_subskrypcje`** — 209 406 wierszy

| kolumna | typ | min | max | approx_unique | unikalne (dokładnie) | null % |
|---|---|---|---|---:|---:|---:|
| id | VARCHAR | SUB-000003 | SUB-019985 | 18 937 | 17 635 | 0,00 |
| plan | VARCHAR | miesięczny | roczny | 2 | 2 | 0,00 |
| data_platnosci | TIMESTAMP | 2023-12-31 23:06:44 | 2026-09-30 00:45:52 | 217 383 | 206 947 | 0,00 |
| kwota | DOUBLE | 39,00 | 399,00 | 2 | 2 | 0,00 |

**Jeden wiersz** to jedno obciążenie subskrypcji „Kawosz co miesiąc”. `id` oznacza subskrybenta. Jest 17 635 subskrybentów: 14 932 w planie miesięcznym (39 zł) i 2 703 w rocznym (399 zł). Każdy `id` ma przez cały czas ten sam plan i dokładnie jedno obciążenie w miesiącu. Odstępy między obciążeniami wynoszą 27–32 dni w planie miesięcznym i 364–367 dni w rocznym. Duplikatów nie ma.

**Kwoty:** 39,00 albo 399,00. Tabela nie ma kolumny waluty ani informacji, czy kwoty są brutto. Według konwencji e-commerce to brutto w PLN, co trzeba potwierdzić. **Plan roczny to 399 zł płacone z góry raz w roku.** Jako przychód odpowiada to 33,25 zł miesięcznie, a jako wpływ gotówki 399 zł w jednym miesiącu. We wrześniu 2026 było 315 obciążeń rocznych na 125 685 zł (miesiąc liczony w UTC).

**Czas:** **UTC**, choć nazwa `data_platnosci` tego nie mówi. Wszystkie obciążenia mają godziny 22–01 UTC, co w Warszawie zawsze daje 00:00–02:59, latem i zimą (nocny batch). Filtrowanie po miesiącu w UTC przenosi więc obciążenia z pierwszej nocy miesiąca do poprzedniego miesiąca. Wrzesień 2026 liczony w UTC to 8 302 obciążenia na 437 178 zł, a w czasie warszawskim 8 474 na 444 606 zł.

**Braki:** brak NULL-i. Brakuje jednak całych informacji: powiązania z klientem (`email`) lub z `ecom_zamowienia`, statusu i daty rezygnacji, a także nieudanych obciążeń.

```sql
-- Zamówienia testowe: trzy sygnały dają ten sam zbiór
WITH t AS (
  SELECT id,
         notatka ILIKE '%test%' OR notatka ILIKE '%nie realiz%' OR notatka ILIKE '%nie wysyłać%' AS test_notatka,
         email LIKE '%@kawosz.pl' AS mail_kawosz
  FROM ecom_zamowienia),
off AS (
  SELECT DISTINCT p.id_zamowienia AS id FROM ecom_pozycje p JOIN ecom_produkty pr USING (sku)
  WHERE round(p.cena_brutto / pr.cena_brutto_pln, 2) IN (1.18, 0.29, 0.30))
SELECT coalesce(test_notatka, false), coalesce(mail_kawosz, false), off.id IS NOT NULL AS cena_poza_cennikiem, count(*)
FROM t LEFT JOIN off USING (id) GROUP BY ALL ORDER BY ALL;

-- Nagłówek vs pozycje (waluta pozycji = waluta zamówienia)
WITH p AS (SELECT id_zamowienia, sum(ilosc * cena_brutto) s FROM ecom_pozycje GROUP BY 1)
SELECT z.waluta, abs(z.brutto - p.s) < 0.005 AS zgodne, count(*)
FROM ecom_zamowienia z JOIN p ON p.id_zamowienia = z.id GROUP BY ALL;

-- Subskrypcje: godzina obciążenia w UTC i w Warszawie
SELECT hour(data_platnosci) AS h_utc,
       hour(timezone('Europe/Warsaw', data_platnosci AT TIME ZONE 'UTC')) AS h_waw, count(*)
FROM ecom_subskrypcje GROUP BY ALL ORDER BY ALL;

-- Wrzesień: UTC vs Europe/Warsaw
SELECT count(*), sum(kwota) FROM ecom_subskrypcje
WHERE timezone('Europe/Warsaw', data_platnosci AT TIME ZONE 'UTC') >= '2026-09-01'
  AND timezone('Europe/Warsaw', data_platnosci AT TIME ZONE 'UTC') <  '2026-10-01';
```

## 5. `karty_podarunkowe`

**SUMMARIZE `karty_podarunkowe`** — 20 398 wierszy

| kolumna | typ | min | max | approx_unique | unikalne (dokładnie) | null % |
|---|---|---|---|---:|---:|---:|
| kod | VARCHAR | KP-223S-FLXU | KP-ZZY2-PRRB | 20 897 | 20 398 | 0,00 |
| data_sprzedazy | DATE | 2024-01-01 | 2026-09-30 | 1 015 | 1 004 | 0,00 |
| data_realizacji | DATE | 2024-01-10 | 2026-09-30 | 1 015 | 993 | 31,07 |
| kwota | BIGINT | 50 | 300 | 5 | 5 | 0,00 |

**Jeden wiersz** to karta podarunkowa. `kod` jest unikalny, a wiersz łączy sprzedaż (`data_sprzedazy`) z ewentualną realizacją (`data_realizacji`). Częściowej realizacji nie ma, karta jest realizowana w całości jednego dnia.

**Kwoty:** nominały 50 / 100 / 150 / 200 / 300. Brak kolumny waluty (domyślnie PLN). Sprzedaż karty to przedpłata, czyli zobowiązanie, a nie sprzedaż towaru.

**Czas:** same daty bez godziny i bez informacji o strefie.

**Braki:**
- `data_realizacji`: 31,07% NULL, czyli karty niezrealizowane. Wśród kart starszych niż pół roku udział jest stały i wynosi ok. 27%, a wśród świeżych (ostatnie 6 miesięcy) 49%. Te 27% to najpewniej karty, które nigdy nie zostaną zrealizowane. Tabela nie ma daty ważności.
- Brakuje kanału sprzedaży (lokal czy sklep internetowy), miejsca realizacji i powiązania z paragonem lub zamówieniem.

**Podejrzane:**
- Karty sprzedawano we wszystkie 1 004 dni, także w 8 dni, w które żaden lokal nie wystawił paragonu (1.01, Wielkanoc, 25.12). Przynajmniej część sprzedaży odbywa się więc poza lokalami. Mimo to ani `pos_produkty`, ani `ecom_produkty` nie mają karty podarunkowej jako produktu, a ani POS, ani e-commerce nie mają takiej metody płatności. **Nie da się ustalić, w której tabeli (jeśli w ogóle) jest sprzedaż karty ani gdzie jest realizacja.** Jeśli realizacja kryje się w POS pod metodą „karta”, a sprzedaż karty też jest liczona jako przychód, ta sama kwota wchodzi dwa razy.
- W grudniu sprzedaż jest ok. 3× wyższa (grudzień 2025: 1 606 kart na 210 400 zł). To sezonowość, a nie błąd.
- We wrześniu 2026 sprzedano 562 karty na 77 100 zł, a zrealizowano 396 kart na 52 500 zł.

```sql
SELECT kwota, count(*), count(data_realizacji) AS zrealizowane FROM karty_podarunkowe GROUP BY 1 ORDER BY 1;

-- Karty sprzedane w dni, w które żaden lokal nie miał paragonu
SELECT k.data_sprzedazy, count(*) FROM karty_podarunkowe k
WHERE k.data_sprzedazy NOT IN (SELECT DISTINCT data_czas::date FROM pos_paragony)
GROUP BY 1 ORDER BY 1;
```

## 6. ERP

### `erp_faktury`

**SUMMARIZE `erp_faktury`** — 47 333 wierszy

| kolumna | typ | min | max | approx_unique | unikalne (dokładnie) | null % |
|---|---|---|---|---:|---:|---:|
| nr_faktury | VARCHAR | FV/2024/01/00001 | KOR/2026/09/0037 | 58 254 | 47 333 | 0,00 |
| id_kontrahenta | BIGINT | 200001 | 260112 | 2 296 | 2 027 | 0,00 |
| data | DATE | 2024-01-15 | 2026-09-30 | 900 | 738 | 0,00 |
| typ | VARCHAR | faktura | korekta | 2 | 2 | 0,00 |
| waluta | VARCHAR | PLN | PLN | 1 | 1 | 0,00 |
| kwota_netto | DOUBLE | -9 348,00 | 330 885,20 | 36 416 | 38 929 | 0,00 |
| vat | DOUBLE | -2 150,04 | 76 103,60 | 29 285 | 34 585 | 0,00 |

**Jeden wiersz** to dokument sprzedaży: faktura (`FV/RRRR/MM/NNNNN`, 46 162 szt.) albo korekta (`KOR/RRRR/MM/NNNN`, 1 171 szt.). Numery są unikalne, a rok i miesiąc w numerze zgadzają się z `data` w 100% dokumentów.

**Kwoty:** `kwota_netto` to **netto**, a `vat` to **kwota** podatku. Waluta jest zawsze PLN (kolumna `waluta` ma jedną wartość). VAT/netto = 0,23 we wszystkich dokumentach poza 14 groszowymi korektami (np. −0,29 netto i −0,07 VAT), gdzie odchylenie wynika z zaokrąglenia. Korekty mają zawsze kwotę ujemną.

**Czas:** `DATE`, data lokalna bez godziny. Faktury są wystawiane hurtowo w ostatni dzień roboczy miesiąca: 31 955 w ostatnim dniu miesiąca i po 6 979 w dniu −1 i −2 (gdy koniec miesiąca wypada w weekend). Pozostałe ok. 250 faktur wystawiono w środku miesiąca. To m.in. faktury końcowe dla klientów, którym kończy się umowa. Dlatego wrzesień w ERP to w praktyce „faktury z 30.09”.

**Braki:** brak NULL-i.

**Podejrzane:**
- **330 885,20 zł netto** (FV/2025/11/00007, kontrahent 200591): 40 × „EKSPRES KAWOSZ PRO X12” po 8 086,66 zł i 40 × instalacja. To 10× więcej niż kolejna faktura (31 375,38 zł). Płatność 406 988,80 zł została zaksięgowana. Jest to jednorazowa sprzedaż sprzętu, która zaburza średnie, a jej indeks nie ma kategorii.
- **Korekty** nie wskazują, którą fakturę korygują (brak kolumny). 324 z nich (28%) mają datę weekendową, podczas gdy faktur z datą weekendową jest 13. W 901 pozycjach korekt ilość jest ułamkowa (np. −0,25 abonamentu, −12,5 l mleka), czyli są to częściowe uznania.
- Wrzesień 2026 ma 4 858 331,65 zł netto, podczas gdy sierpień 4 134 051,18. Różnica pochodzi z kawy dla biur (indeksy `10.01.*`: 837 tys. zł w sierpniu i 1 523 tys. zł we wrześniu), a abonamenty są stabilne. Wygląda to na sezonowość (wakacje), a nie na błąd danych.

### `erp_pozycje`

**SUMMARIZE `erp_pozycje`** — 159 627 wierszy

| kolumna | typ | min | max | approx_unique | unikalne (dokładnie) | null % |
|---|---|---|---|---:|---:|---:|
| nr_faktury | VARCHAR | FV/2024/01/00001 | KOR/2026/09/0037 | 58 254 | 47 333 | 0,00 |
| indeks | VARCHAR | 10.01.0001 | 80.01.0004 | 55 | 53 | 0,00 |
| ilosc | DOUBLE | -229,00 | 945,00 | 773 | 709 | 0,00 |
| cena | DOUBLE | 2,89 | 8 494,70 | 1 835 | 1 797 | 0,00 |

**Jeden wiersz** to pozycja dokumentu. `cena` to cena jednostkowa netto w PLN, a `ilosc` w korektach jest ujemna.

**Zgodność:** dla każdego dokumentu `Σ ilosc × cena` = `kwota_netto`, z dokładnością do pół grosza w korektach. Nie ma sierot ani indeksów spoza kartoteki. Z 398 indeksów kartoteki używanych jest tylko 53.

**Podejrzane:** ceny abonamentów mają setki różnych wartości (np. Plan L: 522 różne ceny, od 84,24 do 4 762,97). Wygląda to na indywidualne cenniki i proporcjonalne naliczanie za niepełne miesiące. Ceny towarów są stałe (jedna cena na indeks w całym okresie).

### `erp_platnosci`

**SUMMARIZE `erp_platnosci`** — 44 712 wierszy

| kolumna | typ | min | max | approx_unique | unikalne (dokładnie) | null % |
|---|---|---|---|---:|---:|---:|
| nr_faktury | VARCHAR | FV/2024/01/00001 | FV/2026/09/00004 | 57 698 | 44 712 | 0,00 |
| data_platnosci | DATE | 2024-02-05 | 2026-09-30 | 702 | 676 | 0,00 |
| kwota | DOUBLE | 32,24 | 406 988,80 | 31 394 | 37 011 | 0,00 |
| spor | BOOLEAN | false | true | 2 | 2 | 0,00 |

**Jeden wiersz** to płatność za fakturę. Każda faktura ma co najwyżej jedną płatność, a **`kwota` to dokładnie brutto faktury** (`kwota_netto + vat`, bez wyjątku). Nie ma płatności częściowych ani nadpłat. Żadna płatność nie jest wcześniejsza niż data faktury. Mediana czasu zapłaty wynosi 14 dni, a maksimum 127 dni.

**Braki i podejrzane:**
- Korekty nie mają płatności (wszystkie płatności dotyczą `FV/`), więc **zwroty pieniędzy dla klientów nie są nigdzie zapisane**.
- 1 450 faktur nie ma płatności: 1 404 z września 2026 (to normalne, bo termin jeszcze nie minął), a 46 z czerwca–sierpnia 2026 jest przeterminowanych.
- `spor = true`: 612 płatności na 2 375 570 zł. Mimo sporu zapłacono pełną kwotę brutto. Znaczenie flagi jest niejasne.

### `erp_kartoteka`

**SUMMARIZE `erp_kartoteka`** — 398 wierszy

| kolumna | typ | min | max | approx_unique | unikalne (dokładnie) | null % |
|---|---|---|---|---:|---:|---:|
| indeks | VARCHAR | 10.01.0001 | 80.01.0004 | 470 | 398 | 0,00 |
| nazwa | VARCHAR | ABONAMENT KAWOSZ DLA BIUR – PLAN L | ŻEL CZYSZCZĄCY 1L | 349 | 376 | 0,00 |
| kategoria | VARCHAR | Abonamenty | Środki czystości | 12 | 13 | 6,03 |

- 398 indeksów, ale tylko 376 różnych nazw. 22 nazwy występują pod dwoma indeksami, czasem w różnych kategoriach. Na przykład „KAWA ZIARN. BRAZYLIA SANTOS 1KG” ma kategorię „Kawa ziarnista” i NULL, a „KAWA ZIARN. KOLUMBIA HUILA 250G” kategorię „Kawa ziarnista” i „Detal”.
- **`kategoria` NULL: 24 indeksy (6,03%)**. Dotyczy to m.in. „ABONAMENT KAWOSZ DLA BIUR – PLAN M” i „– PLAN XL”, „KAWA ZIARN. BIURO STRONG 1KG” i „ORGANIC 1KG” oraz „EKSPRES KAWOSZ PRO X12”. **Pozycje bez kategorii to 26 164 wiersze i 55,8 mln zł netto, czyli 38% całego netto ERP.** Każdy raport według kategorii, który pomija NULL-e, zaniża sprzedaż o ponad jedną trzecią.

### `erp_kontrahenci` i `erp_kontrahenci_archiwum`

**SUMMARIZE `erp_kontrahenci`** — 1 512 wierszy

| kolumna | typ | min | max | approx_unique | unikalne (dokładnie) | null % |
|---|---|---|---|---:|---:|---:|
| id_kontrahenta | BIGINT | 200001 | 260112 | 1 733 | 1 512 | 0,00 |
| nazwa | VARCHAR | ADAMCZYK I WSPÓLNICY SP. Z O.O. | Śródka Sp. k. | 1 060 | 1 509 | 0,00 |
| nip | VARCHAR | 100-110-42-97 | 9986693608 | 1 323 | 1 492 | 0,00 |
| adres | VARCHAR | ul. Abpa. Baraniaka 104 | ul. Św. Marcin 99 | 1 883 | 1 292 | 0,00 |
| kod_pocztowy | VARCHAR | 00-001 | 94-907 | 1 149 | 1 356 | 0,00 |
| id_biura_crm | VARCHAR | 10001 | 11917 | 1 502 | 1 301 | 12,96 |

**SUMMARIZE `erp_kontrahenci_archiwum`** — 517 wierszy

| kolumna | typ | min | max | approx_unique | unikalne (dokładnie) | null % |
|---|---|---|---|---:|---:|---:|
| id_kontrahenta | BIGINT | 200002 | 201835 | 437 | 517 | 0,00 |
| nazwa | VARCHAR | AGENCJA CYBINA SP. Z O.O. SP. K. | Śródka Solutions Sp. j. | 522 | 517 | 0,00 |
| nip | VARCHAR | 1004523623 | 9936277144 | 454 | 517 | 0,00 |
| adres | VARCHAR | ul. Abpa. Baraniaka 124 | ul. Św. Marcin 99 | 469 | 497 | 0,00 |
| kod_pocztowy | VARCHAR | 00-028 | 94-856 | 556 | 506 | 0,00 |
| id_biura_crm | VARCHAR | 10002 | 11835 | 541 | 479 | 7,35 |

**Jeden wiersz** to kontrahent: z aktywną umową (1 512) albo z zakończoną (517, archiwum). Zbiory ID i NIP-ów obu tabel są rozłączne. Każda faktura wskazuje kontrahenta z jednej z tych dwóch tabel.

**Braki:** `id_biura_crm` jest NULL w 12,96% kontrahentów aktywnych (196) i w 7,35% archiwalnych (38).

**Podejrzane:**
- **Duplikaty kontrahentów:** 112 aktywnych ma ID z puli 26xxxx i **wszystkie są drugimi rekordami starszych klientów** (szczegóły w sekcji 10). **105 z nich ma ten sam NIP (po usunięciu myślników) co starszy rekord** (ID 200xxx–201xxx), a 7 ma NIP starszego rekordu bez jednej cyfry, ten sam adres i tę samą nazwę po ujednoliceniu. Nazwa jest zapisana inaczej, np. „GRUPA BRDA S.A.” i „BRDA SA” albo „Instytut Garbary Sp. z o.o.” i „INSTYTUT GARBARY SP Z OO”. Większość z nich nie ma ID z CRM. 15 identyfikatorów CRM jest przypiętych do dwóch kontrahentów ERP. Faktury trafiają do obu rekordów, ale nigdy do obu w tym samym miesiącu, więc nie ma podwójnego fakturowania. Historia klienta jest jednak rozbita. We wrześniu 2026 kontrahenci z puli 26xxxx dostali 58 dokumentów (57 faktur i 1 korektę) na 224 529,31 zł netto.
- **NIP w różnych formatach:** 981 jako 10 cyfr, 368 jako `XXX-XXX-XX-XX`, 148 jako `XXX-XX-XX-XXX` i **15 z 9 cyframi**. Te 15 nie przechodzi kontroli sumy kontrolnej NIP. Po dopisaniu wiodącego zera poprawne są tylko 2, więc pozostałe są błędne. 7 z nich to rekordy 26xxxx z NIP-em starszego rekordu bez jednej cyfry (duplikaty), a 8 to starsze rekordy z błędnym NIP-em i bez duplikatu. Archiwum ma wszystkie NIP-y poprawne i w formacie 10 cyfr.
- Kontrahenci z archiwum mają faktury nawet z 2026-09-25 (8 faktur we wrześniu, wystawione w środku miesiąca). Wygląda to na faktury końcowe przy zakończeniu umowy, a nie na błąd.

```sql
-- Nagłówek vs pozycje ERP
WITH p AS (SELECT nr_faktury, sum(ilosc * cena) s FROM erp_pozycje GROUP BY 1)
SELECT f.typ, abs(f.kwota_netto - p.s) < 0.01 AS zgodne, count(*) FROM erp_faktury f JOIN p USING (nr_faktury) GROUP BY ALL;

-- Płatność = brutto faktury
SELECT round(p.kwota - (f.kwota_netto + f.vat), 2) = 0 AS pelne_brutto, count(*)
FROM erp_platnosci p JOIN erp_faktury f USING (nr_faktury) GROUP BY 1;

-- Netto bez kategorii
SELECT k.kategoria IS NULL AS brak_kategorii, sum(p.ilosc * p.cena) FROM erp_pozycje p JOIN erp_kartoteka k USING (indeks) GROUP BY 1;

-- Duplikaty kontrahentów po znormalizowanym NIP-ie
WITH k AS (SELECT *, regexp_replace(nip, '[^0-9]', '', 'g') AS nip10 FROM erp_kontrahenci)
SELECT nip10, list(id_kontrahenta), list(nazwa) FROM k GROUP BY 1 HAVING count(*) > 1;

-- Kontrola sumy NIP (wagi 6,5,7,2,3,4,5,6,7)
WITH d AS (SELECT regexp_replace(nip, '[^0-9]', '', 'g') AS n FROM erp_kontrahenci)
SELECT length(n) AS dl,
       CASE WHEN length(n) = 10 THEN (
         (substr(n,1,1)::int*6 + substr(n,2,1)::int*5 + substr(n,3,1)::int*7 + substr(n,4,1)::int*2
        + substr(n,5,1)::int*3 + substr(n,6,1)::int*4 + substr(n,7,1)::int*5 + substr(n,8,1)::int*6
        + substr(n,9,1)::int*7) % 11) = substr(n,10,1)::int ELSE false END AS poprawny,
       count(*)
FROM d GROUP BY ALL;
```

## 7. Co z tego dotyczy września 2026

Poniżej skala każdego zjawiska we wrześniu 2026, liczona surowo po natywnej kolumnie daty każdej tabeli. Nie próbuję tu dojść do żadnej z trzech liczb (8,31 / 8,06 / 7,92 mln). Ta tabela to lista rzeczy, które trzeba rozstrzygnąć przed uzgodnieniem.

| Zjawisko | Tabela | Skala we wrześniu 2026 |
|---|---|---|
| Zdublowane pliki paragonów (lokal 17, 11–13.09) | `pos_paragony` | +988 paragonów, +32 684,00 zł brutto |
| Storna (ujemne, znoszą się z paragonem pierwotnym) | `pos_paragony` | 134 paragony, −4 330,00 zł |
| Zwroty bez flagi storno | `pos_paragony` | 2 paragony, −88,00 zł |
| Brak metody płatności | `pos_paragony` | 14 paragonów, 376,00 zł |
| Granica miesiąca UTC vs Warszawa | `ecom_zamowienia` | +50 zamówień, +4 286,81 (surowo, PLN i EUR razem) po przejściu na czas warszawski |
| Granica miesiąca UTC vs Warszawa | `ecom_subskrypcje` | +172 obciążenia, +7 428 zł po przejściu na czas warszawski |
| Zamówienia w EUR | `ecom_zamowienia` | 436 zamówień, 11 461,76 EUR (bez przeliczenia) |
| Zamówienia testowe | `ecom_zamowienia` | 73 zamówienia: 10 782,86 PLN + 17,97 EUR |
| Zamówienia z flagą `zwrot` | `ecom_zamowienia` | 1 005 zamówień, 87 827,45 (PLN i EUR razem) |
| Plan roczny płacony z góry | `ecom_subskrypcje` | 315 obciążeń, 125 685 zł (UTC) |
| Sprzedaż / realizacja kart podarunkowych | `karty_podarunkowe` | sprzedaż 562 szt. na 77 100 zł, realizacja 396 szt. na 52 500 zł |
| VAT (ERP netto vs reszta brutto) | `erp_faktury` | 1 117 416,30 zł VAT przy 4 858 331,65 zł netto |
| Korekty | `erp_faktury` | 37 dokumentów, −13 770,08 zł netto |
| Faktury do kontrahentów z puli 26xxxx (wszystkie 112 to duplikaty) | `erp_faktury` | 58 dokumentów, 224 529,31 zł netto (bez podwójnego fakturowania, ale z rozbitą historią klientów) |
| Faktury niezapłacone | `erp_platnosci` | 1 404 z 1 408 wrześniowych faktur (termin jeszcze nie minął) |

## 8. Pytania do właścicieli danych

1. **POS:** czy paragon na 48 000 zł (`P0999`, lokal 5, 2025-03-14) to błąd wpisu? Potwierdzi to rozliczenie terminala kartowego lokalu 5 z tego dnia. Jak w kasie rejestruje się zwrot towaru, skoro nie ma osobnej flagi i pojawia się jako pozycja ujemna w paragonie? Czy ruch w lokalu 17 (4× średnia) jest prawdziwy?
2. **E-commerce:** czy dashboard i raport sprzedaży wykluczają zamówienia testowe? Kiedy ustawiana jest flaga `zwrot`, czy zwrot jest zawsze pełny i gdzie jest data zwrotu? Jakim kursem EUR/PLN przelicza księgowość: NBP z dnia zamówienia, z dnia poprzedzającego czy innym?
3. **Subskrypcje:** czy plan roczny jest rozliczany jako przychód jednorazowo czy rozkładany na 12 miesięcy? Czy kwoty 39 i 399 są brutto?
4. **Karty podarunkowe:** gdzie są sprzedawane (lokale, sklep, oba kanały)? Gdzie zapisuje się realizację, skoro w POS i e-commerce nie ma takiej metody płatności? Czy sprzedaż karty jest wliczana do przychodu w którymkolwiek raporcie?
5. **ERP:** co oznaczają kontrahenci z ID 26xxxx (migracja, nowe umowy?) i który rekord jest właściwy? Co oznacza `spor` przy płatnościach opłaconych w całości? Dlaczego cała faktura ma VAT 23%, także przy pozycjach typu mleko UHT? Czy to uproszczenie danych, czy błąd stawek? Czy sprzedaż 40 ekspresów Kawosz Pro X12 Grupie Cytadela (FV/2025/11/00007, 330 885,20 zł netto) rzeczywiście się odbyła? Potwierdzą to umowa lub zamówienie, protokoły instalacji i wyciąg bankowy. Czy `iot_ekspresy` obejmuje ekspresy sprzedane, czy tylko te w abonamencie?
6. **Kartoteka:** kto uzupełni kategorie dla 24 indeksów, w tym abonamentów Plan M i XL?

## 9. Wartości odstające w kwotach paragonów i faktur

Badane kwoty to `pos_paragony.kwota_brutto` i `erp_faktury.kwota_netto`. Dla każdej policzyłem kwartyle, medianę, 99. percentyl i granice reguły IQR (Q1 − 1,5·IQR, Q3 + 1,5·IQR, `quantile_cont`). Potem zebrałem kontekst dla 10 największych kwot w każdej tabeli. **Niczego nie usuwam ani nie zmieniam w bazie.** Ocena każdej kwoty jest w tabelach poniżej, a zapytanie w 9.5 odtwarza te oznaczenia w SQL.

Oceny:
- **Błąd** oznacza, że kwoty nie da się wyjaśnić sprzedażą, a kilka niezależnych sygnałów wskazuje na pomyłkę.
- **Do weryfikacji** oznacza, że dane są wewnętrznie spójne, ale sprzedaż jest nietypowa i nie potwierdza jej inny system.
- **Prawdziwa sprzedaż** oznacza, że kwotę wyjaśniają pozycje po cenach z cennika i ma ona uzasadnienie w historii lokalu lub klienta.

### 9.1 Statystyki rozkładu

| Tabela / zakres | n | Q1 | Mediana | Q3 | IQR | Dolna granica | Górna granica | P99 | Max | Powyżej górnej | Poniżej dolnej |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `pos_paragony`, unikalne paragony (bez 988 duplikatów) | 2 099 614 | 18,00 | 24,00 | 38,00 | 20,00 | −12,00 | 68,00 | 145,00 | 48 000,00 | 109 860 (5,2%) | 4 024 (0,2%) |
| `pos_paragony`, wszystkie wiersze | 2 100 602 | 18,00 | 24,00 | 38,00 | 20,00 | −12,00 | 68,00 | 145,00 | 48 000,00 | 109 931 | 4 027 |
| `erp_faktury`, tylko faktury | 46 162 | 1 616,62 | 2 496,96 | 3 923,71 | 2 307,09 | −1 844,02 | 7 384,35 | 11 944,73 | 330 885,20 | 2 762 (6,0%) | 0 |
| `erp_faktury`, wszystkie dokumenty | 47 333 | 1 558,65 | 2 425,89 | 3 864,54 | 2 305,89 | −1 900,19 | 7 323,38 | 11 851,20 | 330 885,20 | 2 829 | 61 (same korekty) |
| `erp_faktury`, tylko korekty | 1 171 | −693,67 | −252,24 | −37,43 | 656,24 | −1 678,03 | 946,93 | — | −0,29 | 0 | 90 |

Duplikaty z lokalu 17 nie zmieniają kwartyli ani percentyli POS. Dalej używam unikalnych paragonów. 99,9. percentyl paragonów to 238 zł, a w całej historii tylko jeden paragon przekracza 2 094 zł.

### 9.2 Co reguła IQR oznacza w tych danych

**POS.** Rozkład jest mocno prawoskośny: mediana wynosi 24 zł, a górna granica 68 zł, czyli tyle co dwie kawy i ciastko dla dwóch osób. Reguła oznacza więc 109 860 paragonów, ale **nie jest to lista błędów**:
- 30 573 z nich zawiera towar detaliczny (ziarno za 49–169 zł, młynek za 349 zł);
- pozostałe 79 287 to zamówienia grupowe z co najmniej 3 napojami lub daniami;
- nawet granica 3·IQR (98 zł) oznacza 49 865 paragonów;
- IQR liczone na logarytmie kwoty, lepiej dopasowane do rozkładu prawoskośnego, daje granicę 116,56 zł (35 188 paragonów), a w wariancie 3·IQR 357,53 zł (800 paragonów). To nadal zwykłe zakupy.

Właściwym testem dla POS jest pytanie, czy pozycje po cenach z cennika wyjaśniają kwotę. Kwota paragonu zawsze równa się sumie pozycji (sekcja 3), ceny pozycji są równe cennikowi, a ilość nigdy nie przekracza 8. Test nie przechodzi tylko jeden paragon: ten na 48 000 zł.

Poniżej dolnej granicy (−12 zł) są 4 024 paragony: 3 840 storn i 184 zwroty bez flagi storno, opisane w sekcji 3.

**ERP.** Kwota faktury zależy głównie od planu abonamentu, więc reguła IQR na całej tabeli oznacza dużych klientów:
- z 2 762 faktur powyżej 7 384 zł aż 2 014 dotyczy planu XL (mediana faktury XL, 7 970,91 zł, sama przekracza górną granicę);
- 735 dotyczy planu L, a 12 planu M;
- 1 faktura nie ma abonamentu: to faktura na 330 885,20 zł.

Lepszym testem jest porównanie faktury z medianą faktur tego samego klienta. 89 faktur przekracza 3× medianę swojego klienta. Faktura na 330 885,20 zł ma 21,8×, a żadna inna nie przekracza 6×. Tych 89 faktur poza pierwszą szczegółowo nie przeglądałem.

Poniżej dolnej granicy jest 61 dokumentów i wszystkie to korekty. Najniższa, −9 348,00 zł (KOR/2025/06/0017), to zwrot 150 kg kawy Crema. Pięć kolejnych to uznania za pełny miesiąc abonamentu XL (od −5 853,55 do −6 588,03 zł) i wyglądają wiarygodnie.

### 9.3 Top 10 paragonów (`pos_paragony`)

| # | Lokal | Data i godzina | Kwota | Pozycje (cena = cennik, chyba że zaznaczono) | Płatność | Ocena |
|---:|---|---|---:|---|---|---|
| 1 | 5 – Poznań, ul. Dąbrowskiego 77 | 2025-03-14 11:42 (pt) | 48 000,00 | 1 × P0999 „Kawa ziarnista na wagę” po 48 000,00 (**w cenniku 0,00**) | karta | **Błąd** |
| 2 | 7 – Warszawa, ul. Mokotowska 45 | 2025-07-12 08:43 (sob) | 2 094,00 | 6 × Młynek ręczny po 349,00 | karta | Prawdziwa sprzedaż (nietypowa ilość) |
| 3 | 17 – Warszawa, Al. Jerozolimskie 54 | 2025-06-20 13:11 (pt) | 1 745,00 | 5 × Młynek ręczny po 349,00 | karta | Prawdziwa sprzedaż (nietypowa ilość) |
| 4 | 11 – Wrocław, Rynek 12 | 2026-08-27 16:46 (czw) | 1 373,00 | 8 × Espresso Blend 1 kg po 169,00 + Kawa przelewowa V60 | karta, sala | Prawdziwa sprzedaż |
| 5 | 15 – Gdańsk, ul. Długa 22 | 2025-01-22 15:14 (śr) | 1 371,00 | 8 × Espresso Blend 1 kg + Flat white | karta | Prawdziwa sprzedaż |
| 6 | 22 – Wrocław, ul. Powstańców Śląskich 95 | 2025-07-26 17:33 (sob) | 1 371,00 | 8 × Espresso Blend 1 kg + Latte | gotówka | Prawdziwa sprzedaż |
| 7 | 21 – Bydgoszcz, ul. Gdańska 30 | 2026-05-24 13:54 (nd) | 1 371,00 | 8 × Espresso Blend 1 kg + Flat white | karta | Prawdziwa sprzedaż |
| 8 | 22 – Wrocław, ul. Powstańców Śląskich 95 | 2026-07-19 17:20 (nd) | 1 371,00 | 8 × Espresso Blend 1 kg + Latte | aplikacja, wynos | Prawdziwa sprzedaż |
| 9 | 4 – Poznań, ul. Głogowska 108 | 2024-05-02 10:57 (czw) | 1 370,00 | 8 × Espresso Blend 1 kg + Ciasto dnia | gotówka | Prawdziwa sprzedaż |
| 10 | 2 – Poznań, ul. Półwiejska 32 | 2025-08-11 17:28 (pon) | 1 369,00 | 8 × Espresso Blend 1 kg + Cappuccino | karta | Prawdziwa sprzedaż |

Żaden z tych paragonów nie pochodzi ze zdublowanych plików i żaden nie ma storna. Kolejność przy równych kwotach ustala data.

**#1 – 48 000,00 zł: błąd (niemal pewny).** Wskazuje na to pięć niezależnych sygnałów:
- `P0999` ma w cenniku cenę 0,00, czyli cenę wpisuje sprzedawca. To jedyna sprzedaż tego produktu w całej historii.
- Za 1 sztukę „kawy na wagę” zapłacono 48 000 zł. Przy cenach ziarna z tego samego cennika (149–169 zł/kg) odpowiadałoby to ok. 285–320 kg kawy.
- Obrót lokalu 5 tego dnia wyniósł 50 307 zł, a jego dzienna mediana to 2 643 zł (najlepszy inny dzień: 4 908 zł).
- **Numer paragonu jest poza kolejnością.** Paragon 2503140076 jest ostatni w dniu, choć ma godzinę 11:42, a paragony 0073–0074 są z 18:34–18:36. Wśród 2 095 318 zwykłych paragonów sprzedaży to jedyny taki przypadek. Poza kolejnością są tylko storna (4 038 z 4 097), które kasa dopisuje na końcu dnia. Paragon został więc dopisany poza normalnym obiegiem.
- Nie ma storna ani korekty, więc kwota nadal zawyża sprzedaż lokalu 5 w marcu 2025 o 48 000 zł brutto.

Błąd potwierdzi rozliczenie terminala kartowego lokalu 5 z 14.03.2025. Przyczyny (np. przesunięty przecinek albo wpisana waga zamiast ceny) z danych nie da się ustalić.

**#2–#3 – młynki: prawdziwa sprzedaż o nietypowej ilości.** Ceny są zgodne z cennikiem, numery paragonów w kolejności, płatność kartą. Zakup 5 lub więcej młynków zdarzył się tylko w tych dwóch paragonach (rozkład ilości młynka w historii: 1 szt. 364 razy, 2 szt. 10 razy, 3 szt. raz, 5 i 6 szt. po razie). Wygląda to na zakup prezentowy albo firmowy, a kwoty są małe. Można to potwierdzić, ale nie ma powodu uznawać tych paragonów za błąd.

**#4–#10 – 8 × Espresso Blend 1 kg: prawdziwa sprzedaż.** To jeden powtarzalny wzór: 8 kg ziarna po cenie z cennika i jeden napój lub ciastko. Występuje 13 razy w 9 lokalach od maja 2024 do sierpnia 2026, z różnymi metodami płatności, a numery są w kolejności. Ilość 8 to maksimum w całej tabeli `pos_pozycje` dla każdej kategorii (ilość 9 i więcej nie występuje nigdy). Może to być ograniczenie kasy, ale nie wskazuje na błąd pojedynczego paragonu.

### 9.4 Top 10 faktur (`erp_faktury`)

| # | Faktura | Kontrahent (CRM: plan, pracownicy) | Data | Netto | Główne pozycje | Kontekst klienta | Ocena |
|---:|---|---|---|---:|---|---|---|
| 1 | FV/2025/11/00007 | 200591 Grupa Cytadela Sp. z o.o. Sp. k. (XL, 498) | 2025-11-20 (czw, środek miesiąca) | 330 885,20 | 40 × EKSPRES KAWOSZ PRO X12 po 8 086,66 + 40 × instalacja po 185,47 | mediana faktur klienta 15 177; zwykła faktura za listopad osobno (28.11, 7 353,98) | **Do weryfikacji** |
| 2 | FV/2025/01/01250 | 201452 Kappa Tech S.A. (XL, 665) | 2025-01-31 | 31 375,38 | 66 × Crema 6 kg (396 kg) + Plan XL 7 930,86 | 12.2024: 8 075 zł, bez kawy | Prawdziwa sprzedaż |
| 3 | FV/2025/09/01104 | 201452 Kappa Tech S.A. | 2025-09-30 | 30 090,92 | 61 × Crema 6 kg (366 kg) + Plan XL 8 249,87 | 08.2025: 8 250 zł, bez kawy | Prawdziwa sprzedaż |
| 4 | FV/2026/09/00959 | 201452 Kappa Tech S.A. | 2026-09-30 | 29 596,38 | 59 × Crema 6 kg (354 kg) + Plan XL 8 494,70 (= `cena_mies` w CRM) | 08.2026: 8 495 zł, bez kawy; jeszcze niezapłacona | Prawdziwa sprzedaż (**wrzesień 2026**) |
| 5 | FV/2026/01/01058 | 201452 Kappa Tech S.A. | 2026-01-30 | 29 351,55 | 59 × Crema 6 kg (354 kg) + Plan XL 8 249,87 | 12.2025: 8 394 zł, bez kawy | Prawdziwa sprzedaż |
| 6 | FV/2024/01/00590 | 200591 Grupa Cytadela (XL, 498) | 2024-01-31 | 27 971,15 | 354 × Classic 1 kg (354 kg) + Plan XL 5 415,83 + 597 l mleka + serwis | pierwszy miesiąc danych (12.2023 poza zakresem) | Prawdziwa sprzedaż (prawdopodobnie) |
| 7 | FV/2024/08/01339 | 201452 Kappa Tech S.A. | 2024-08-30 | 27 823,18 | 56 × Crema 6 kg (336 kg) + Plan XL 7 930,86 | 07.2024: 5 628 zł, sam abonament (umowa od 10.07.2024) | Prawdziwa sprzedaż |
| 8 | FV/2025/03/01146 | 201394 Biuro Morasko Sp. z o.o. (XL, 655) | 2025-03-31 | 27 638,30 | 348 × Strong 1 kg (348 kg) + Plan XL 4 748,13 + 635 l mleka | 02.2025: 6 534 zł, bez kawy | Prawdziwa sprzedaż |
| 9 | FV/2024/01/00847 | 200848 Wielkopolska s.c. (XL, 970) | 2024-01-31 | 27 062,17 | 330 × Strong 1 kg (330 kg) + Plan XL 4 903,93 + 756 l mleka | pierwszy miesiąc danych | Prawdziwa sprzedaż (prawdopodobnie) |
| 10 | FV/2024/06/01319 | 201394 Biuro Morasko Sp. z o.o. | 2024-06-28 | 25 843,16 | 56 × Strong 6 kg (336 kg) + Plan XL 4 748,13 + 628 l mleka | 05.2024: 5 979 zł, bez kawy | Prawdziwa sprzedaż |

Wszyscy kontrahenci są aktywni i mają ID z CRM. Wszystkie faktury poza #4 są opłacone w pełnej kwocie brutto, a #4 jest z 30.09.2026, więc termin jeszcze nie minął. Ceny towarów są zgodne z kartoteką, a VAT wynosi 23%.

**#1 – 330 885,20 zł: do weryfikacji.** To nie jest błąd techniczny, ale jednorazowa sprzedaż sprzętu, której nie potwierdza żaden inny system.

Za tym, że to prawdziwa sprzedaż, przemawia:
- kontrahent jest aktywnym klientem XL od 2019 roku;
- numer faktury jest w kolejności (00006 z 19.11, 00008 z 24.11), a w całym ERP żadna faktura nie łamie kolejności numeracji;
- pozycje sumują się do nagłówka, a VAT wynosi 23%;
- 2025-12-08 zaksięgowano płatność 406 988,80 zł, bez korekty.

Przeciw, albo przynajmniej nietypowe:
- to jedyna sprzedaż ekspresu (`50.01.0006`) i jedyna usługa instalacji (`70.01.0004`) w 33 miesiącach ERP;
- kwota to 21,8× mediana faktur tego klienta i 10,5× kolejna największa faktura w ERP;
- według `iot_ekspresy` klient ma 3 ekspresy zainstalowane w 2019 roku i żadnej nowej instalacji, a w całej firmie w okresie XI.2025–I.2026 zainstalowano 4 ekspresy Pro X12, a nie 40;
- indeks ekspresu nie ma kategorii;
- płatność nie jest niezależnym potwierdzeniem, bo każda płatność w ERP równa się dokładnie brutto faktury.

Jeśli `iot_ekspresy` obejmuje tylko ekspresy w abonamencie, brak instalacji niczego nie przesądza. Dlatego jest to „do weryfikacji”, a nie „błąd”. Sprzedaż potwierdzą umowa lub zamówienie, protokoły instalacji i wyciąg bankowy. Do tego czasu fakturę trzeba pokazywać osobno od przychodu powtarzalnego, bo zawyża listopad 2025 o 330 885,20 zł netto i średnią wartość faktury. Września 2026 nie dotyczy.

**#2–#10 – skumulowana dostawa kawy: prawdziwa sprzedaż.** Wszystkie dziewięć faktur ma ten sam wzór:
- to klient XL z miesięczną fakturą wystawioną na koniec miesiąca;
- ilość kawy jest 1,6–2,3× większa niż mediana tego klienta (np. Kappa Tech: 336–396 kg wobec mediany 210 kg);
- w poprzednim miesiącu klient dostał fakturę za sam abonament, bez kawy (przy #6 i #9 poprzedni miesiąc jest poza zakresem danych).

Wygląda to na dostawę za dwa miesiące wystawioną na jednej fakturze, często po miesiącu wakacyjnym albo świątecznym. U Kappa Tech wzór „sierpień lub grudzień bez kawy, potem faktura ok. 1,5× wyższa” powtarza się co roku. To ten sam mechanizm, przez który ERP we wrześniu 2026 jest wyższy niż w sierpniu (sekcja 6). Cena abonamentu w #4 równa się `cena_mies` w CRM (8 494,70 zł), a w #6 cenie startowej z historii umowy (5 415,83 zł).

### 9.5 Oznaczenia w SQL (bez usuwania)

```sql
-- Statystyki i granice IQR (wzorzec, dla ERP podstaw erp_faktury.kwota_netto i filtr typ)
WITH r AS (SELECT DISTINCT ON (lokal, nr_paragonu) kwota_brutto::double AS k FROM pos_paragony),
s AS (SELECT quantile_cont(k, 0.25) q1, median(k) med, quantile_cont(k, 0.75) q3, quantile_cont(k, 0.99) p99 FROM r)
SELECT s.*, q3 - q1 AS iqr, q1 - 1.5 * (q3 - q1) AS dolna, q3 + 1.5 * (q3 - q1) AS gorna,
       (SELECT count(*) FROM r WHERE k > q3 + 1.5 * (q3 - q1)) AS powyzej,
       (SELECT count(*) FROM r WHERE k < q1 - 1.5 * (q3 - q1)) AS ponizej
FROM s;

-- POS: oznaczenie paragonów (nic nie jest usuwane)
WITH r AS (SELECT DISTINCT ON (lokal, nr_paragonu) * FROM pos_paragony),
g AS (SELECT quantile_cont(kwota_brutto, 0.75) + 1.5 * (quantile_cont(kwota_brutto, 0.75) - quantile_cont(kwota_brutto, 0.25)) AS gorna FROM r)
SELECT r.*,
       r.kwota_brutto > g.gorna AS powyzej_iqr,
       CASE
         WHEN r.lokal = 5 AND r.nr_paragonu = 2503140076 THEN 'błąd: ręczna cena P0999, numer poza kolejnością'
         WHEN r.kwota_brutto > g.gorna THEN 'powyżej IQR: sprzedaż zgodna z cennikiem'
       END AS ocena
FROM r, g;

-- ERP: oznaczenie faktur
WITH f AS (SELECT * FROM erp_faktury WHERE typ = 'faktura'),
g AS (SELECT quantile_cont(kwota_netto, 0.75) + 1.5 * (quantile_cont(kwota_netto, 0.75) - quantile_cont(kwota_netto, 0.25)) AS gorna FROM f)
SELECT f.*,
       f.kwota_netto > g.gorna AS powyzej_iqr,
       f.kwota_netto / median(f.kwota_netto) OVER (PARTITION BY f.id_kontrahenta) AS x_mediany_klienta,
       CASE
         WHEN f.nr_faktury = 'FV/2025/11/00007' THEN 'do weryfikacji: jednorazowa sprzedaż 40 ekspresów'
         WHEN f.nr_faktury IN ('FV/2025/01/01250', 'FV/2025/09/01104', 'FV/2026/09/00959', 'FV/2026/01/01058',
                               'FV/2024/01/00590', 'FV/2024/08/01339', 'FV/2025/03/01146', 'FV/2024/01/00847',
                               'FV/2024/06/01319') THEN 'prawdziwa: skumulowana dostawa kawy (2 miesiące)'
         WHEN f.kwota_netto > g.gorna THEN 'powyżej IQR: duży klient (plan XL/L)'
       END AS ocena
FROM f, g;

-- Paragon dopisany poza kolejnością numeracji (zwykłe paragony: 0 przypadków poza #1)
WITH r AS (SELECT DISTINCT ON (lokal, nr_paragonu) * FROM pos_paragony),
o AS (SELECT *, max(data_czas) OVER (PARTITION BY lokal, nr_paragonu // 10000 ORDER BY nr_paragonu
                                     ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS max_wczesniej
      FROM r)
SELECT CASE WHEN storno = 1 THEN 'storno' WHEN kwota_brutto < 0 THEN 'zwrot bez storno' ELSE 'sprzedaż' END AS typ,
       count(*), count(*) FILTER (WHERE data_czas < max_wczesniej) AS poza_kolejnoscia
FROM o GROUP BY 1;

-- Kawa w kg na fakturze vs mediana klienta (miesiące z dostawą) i poprzednia faktura (także bez kawy)
WITH kg AS (SELECT indeks, CASE WHEN nazwa ILIKE '%6KG%' THEN 6 WHEN nazwa ILIKE '%1KG%' THEN 1
                                WHEN nazwa ILIKE '%500G%' THEN 0.5 WHEN nazwa ILIKE '%250G%' THEN 0.25 END AS kg
            FROM erp_kartoteka WHERE indeks LIKE '10.%'),
inv AS (SELECT f.nr_faktury, f.id_kontrahenta, f.data, coalesce(sum(p.ilosc * kg.kg), 0) AS kg
        FROM erp_faktury f JOIN erp_pozycje p USING (nr_faktury) LEFT JOIN kg USING (indeks)
        WHERE f.typ = 'faktura' GROUP BY ALL)
SELECT * FROM (
  SELECT nr_faktury, id_kontrahenta, data, kg,
         median(kg) FILTER (WHERE kg > 0) OVER (PARTITION BY id_kontrahenta) AS mediana_kg_klienta,
         lag(kg) OVER (PARTITION BY id_kontrahenta ORDER BY data) AS kg_poprzednia_faktura
  FROM inv)
WHERE nr_faktury IN ('FV/2025/01/01250', 'FV/2026/09/00959', 'FV/2025/03/01146');
```

## 10. Unikalność kluczy i wpływ złączeń

Sprawdziłem trzy rzeczy:
- klucz paragonu w POS: (lokal, numer, data);
- numer faktury w ERP;
- kontrahentów w `erp_kontrahenci`, także po ujednoliceniu NIP i nazwy.

Potem dla każdego złączenia, którego używają raporty, porównałem liczbę wierszy i sumę kwot przed złączeniem i po nim. Złączenia z `docs/trzy_przychody.md` liczyłem na wrześniu 2026, a złączenia z analiz w tym dokumencie na całym okresie, bo na takim zakresie działały. Niczego nie zmieniałem w bazie.

### 10.1 POS: klucz paragonu (lokal, numer, data)

| Kandydat na klucz | Wiersze | Unikalne | Grupy powtórzeń | Nadmiarowe wiersze |
|---|---:|---:|---:|---:|
| (`lokal`, `nr_paragonu`, data z `data_czas`) | 2 100 602 | 2 099 614 | 988 | 988 |
| (`lokal`, `nr_paragonu`) | 2 100 602 | 2 099 614 | 988 | 988 |
| sam `nr_paragonu` | 2 100 602 | 311 696 | — | — |
| `pos_pozycje`: (`lokal`, `nr_paragonu`, `kod_produktu`) | 3 197 403 | 3 159 093 | — | — |

- **Klucz (lokal, numer, data) nie jest unikalny.** Jest 988 grup, każda składa się z dokładnie 2 wierszy, identycznych we wszystkich kolumnach poza `plik`. To trzy zdublowane pliki `pos_paragony_17_2026-09-1{1,2,3} (1).csv` z sekcji 3. Po ich pominięciu klucz jest unikalny.
- **Data niczego nie dodaje do klucza**, bo jest już zakodowana w numerze (`RRMMDD` + numer kolejny, zgodność 100%). Wystarczy klucz (`lokal`, `nr_paragonu`).
- **Sam numer nie jest kluczem:** 117 743 numery występują w więcej niż jednym lokalu. Każde złączenie paragonów musi zawierać `lokal`.
- `pos_pozycje` nie ma klucza wiersza (nie ma kolumny z numerem pozycji). Nawet (`lokal`, `nr_paragonu`, `kod_produktu`, `ilosc`, `cena_brutto`) się powtarza. Pozycje można więc tylko agregować do paragonu, a nie łączyć jeden do jednego.

### 10.2 ERP: numer faktury

- `erp_faktury.nr_faktury` jest **unikalny**: 47 333 wiersze i 47 333 numery, także po ujednoliceniu (wielkie litery, bez spacji).
- Format jest w 100% jednolity: `FV/RRRR/MM/NNNNN` i `KOR/RRRR/MM/NNNN`.
- Numeracja jest ciągła, od 1 i bez luk, w każdym z 33 miesięcy faktur i 32 miesięcy korekt.
- Nie ma też duplikatów treści, czyli tego samego kontrahenta, daty i kwoty pod różnymi numerami.
- W tabelach podrzędnych numery mają ten sam format. `erp_pozycje` wskazuje wszystkie 47 333 dokumenty, a `erp_platnosci` ma 44 712 wierszy i 44 712 różnych numerów, czyli najwyżej jedną płatność na fakturę.

**To jedyny w pełni czysty klucz wśród sprawdzanych.**

### 10.3 Kontrahenci: ID, NIP i nazwa

Poziomy ujednolicenia:
- **NIP (cyfry):** usunięte wszystkie znaki poza cyframi.
- **Nazwa N1:** wielkie litery i pojedyncze spacje.
- **Nazwa N2:** N1 bez kropek i przecinków, z jedną formą prawną: „Sp. z o.o.”, „SP Z OO” i „spółka z o.o.” → `SP Z OO`; „S.A.” i „Spółka Akcyjna” → `SA`; podobnie `SPK`, `SC`, `SPJ`.
- **Nazwa N3:** N2 bez pierwszego słowa opisowego (`BIURO`, `BIUROWIEC`, `STUDIO`, `HUB`, `PARK`, `CENTRUM`, `GRUPA`), które rekordy 26xxxx opuszczają.

| Klucz (1 512 kontrahentów aktywnych) | Unikalne | Grupy powtórzeń | w tym ten sam NIP (cyfry) | w tym różne NIP-y |
|---|---:|---:|---:|---:|
| `id_kontrahenta` | 1 512 | 0 | — | — |
| NIP surowy | 1 492 | 20 | 20 | 0 |
| NIP (cyfry) | 1 407 | 105 | 105 | 0 |
| nazwa surowa | 1 509 | 3 | 3 | 0 |
| nazwa N1 | 1 505 | 7 | 7 | 0 |
| nazwa N2 | 1 410 | 101 | 83 | 18 |
| nazwa N3 | 1 223 | 204 | 84 | 120 |
| NIP (cyfry) + nazwa N2 | 1 428 | 84 | 84 | 0 |
| NIP (cyfry) + nazwa N3 | 1 407 | 105 | 105 | 0 |
| adres + kod pocztowy | **1 400** | 112 | 105 | 7 |
| `id_biura_crm` (1 316 niepustych) | 1 301 | 15 | 15 | 0 |

**Pary z tym samym NIP-em (cyframi): 105.** Nazwa zgadza się w 3 parach na surowo, w 7 po N1, w 84 po N2 i we wszystkich 105 po N3. Adres zgadza się we wszystkich 105. W każdej parze drugi rekord ma ID z puli 26xxxx.

**Pary różnych NIP-ów o tej samej nazwie:** po N1 jest ich 0, po N2 19, a po N3 aż 303. Sprawdziłem wszystkie 19 par z N2:
- **7 par to ta sama firma z uszkodzonym NIP-em.** Mają ten sam adres i tę samą nazwę, a NIP rekordu 26xxxx ma 9 cyfr i jest NIP-em starszego rekordu bez jednej cyfry, np. „Kancelaria Aleja Sp. z o.o.” `739-031-90-19` i „KANCELARIA ALEJA SP Z OO” `739039019`. Są to dokładnie te same 7 grup, które łączy adres przy różnych NIP-ach. Pozostałe 8 z 15 dziewięciocyfrowych NIP-ów to starsze rekordy z błędnym NIP-em, bez duplikatu.
- **12 par to różne firmy o tej samej nazwie.** Oba NIP-y są poprawne, a adresy różne, np. „ODRA SP. Z O.O.” `3712144122` i „Odra spółka z o.o.” `547-004-83-72`. Łączenie po nazwie scaliłoby je błędnie.

Wnioski:
- **Wszystkie 112 rekordów z puli 26xxxx to duplikaty starszych klientów:** 105 wykrywa NIP (cyfry), a pozostałe 7 wykrywa dopiero adres albo naprawa NIP-u. Rzeczywistych kontrahentów aktywnych jest **1 400**. Tyle samo daje adres z kodem pocztowym: każda grupa adresowa to jeden starszy rekord i jeden rekord 26xxxx, a żadne inne rekordy nie dzielą adresu.
- **Nazwa nie jest kluczem na żadnym poziomie.** N1 nie łączy prawie niczego (7 ze 105 par). N2 łączy 84 duplikaty, ale też 12 par różnych firm. N3 łączy wszystkie duplikaty kosztem 303 fałszywych par. Nazwa nadaje się tylko do potwierdzenia dopasowania po NIP-ie lub adresie.
- **Właściwy klucz firmy** to NIP (cyfry) z naprawionymi 7 NIP-ami, potwierdzony adresem. `id_kontrahenta` jest unikalny, ale tylko technicznie. Mapa „rekord 26xxxx → rekord główny” jest w 10.6.
- Na rekordy 26xxxx wystawiono 975 dokumentów na 3 177 125,47 zł netto. W żadnym miesiącu faktura nie trafia do obu rekordów pary. Przy 100 parach faktury trafiają na zmianę raz do jednego, raz do drugiego rekordu (mediana 9 przeskoków, od 2 do 19). Przy 9 parach rekord 26xxxx przejmuje fakturowanie po ostatniej fakturze starszego rekordu, a przy 1 jest odwrotnie. W 1 parze rekord 26xxxx nie ma żadnej faktury, a w 1 nie ma ich starszy rekord.
- Archiwum nie ma wspólnych NIP-ów z aktywnymi. Nazwa N2 pokrywa się z aktywnym kontrahentem w 2 przypadkach, ale przy różnych NIP-ach.

### 10.4 Złączenia w raportach przychodu (wrzesień 2026)

| # | Złączenie | Gdzie | Wiersze przed → po | Suma przed → po | Ocena |
|---|---|---|---|---|---|
| A1 | `pos_paragony` ⋈ agregat `pos_pozycje` po (`lokal`, `nr_paragonu`) | raport sprzedaży, księgowość (POS netto) | 70 097 → 70 097 | 2 187 234,00 → 2 187 234,00 | **bezpieczne**: agregat ma jeden wiersz na paragon, nic nie ginie ani się nie mnoży; zduplikowane nagłówki zostają zgodnie z definicją |
| A1′ | to samo bez agregacji pozycji | (pułapka) | 70 097 → 106 907 | 2 187 234,00 → 3 907 715,00 | **mnoży kwotę paragonu przez liczbę pozycji** |
| A2 | `ecom_zamowienia` ⋈ `ecom_pozycje` po `id`, suma pozycji | BI, wariant 8 | 7 639 → 17 928 | 677 061,42 → 677 061,42 | **bezpieczne**, bo sumowane są pozycje |
| A2′ | to samo, ale suma `brutto` z nagłówka | (pułapka) | 7 639 → 17 928 | 677 061,42 → 1 698 724,81 | **mnoży ×2,5** |
| A3 | zamówienia EUR `ASOF LEFT JOIN kursy_nbp`, kurs z dnia | BI i sprzedaż, wariant 11 | 436 → 436 (wszystkie z kursem) | 11 461,76 EUR → 11 461,76 EUR | **bezpieczne we wrześniu**; w całym okresie 8 zamówień z 31.12.2023–1.01.2024 nie ma kursu (tabela NBP zaczyna się 2.01.2024) |
| A4 | to samo, kurs z poprzedniego dnia roboczego | księgowość, wariant 9 | 436 → 436 | 11 461,76 EUR → 11 461,76 EUR | **bezpieczne we wrześniu**; w całym okresie 15 zamówień z 31.12.2023–2.01.2024 bez kursu |

**Żadne złączenie użyte w `docs/trzy_przychody.md` nie gubi ani nie mnoży wierszy, więc liczby w tamtym dokumencie się nie zmieniają.** Główne zapytania BI i obu raportów nie mają innych złączeń: każde źródło jest sumowane osobno.

### 10.5 Złączenia w analizach tego dokumentu (cały okres, z wpływem na wrzesień)

| # | Złączenie | Gdzie | Wiersze przed → po | Suma przed → po | Wrzesień 2026 | Ocena |
|---|---|---|---|---|---|---|
| B1 | `pos_pozycje` ⋈ `pos_produkty` po `kod_produktu` | sekcje 3, 9 | 3 197 403 → 3 197 403 | 65 639 500,00 → bez zmian | bez zmian | bezpieczne |
| B2 | `pos_paragony` ⋈ `lokale` po `lokal` | sekcje 3, 9 | 2 100 602 → 2 100 602 | 65 672 184,00 → bez zmian | bez zmian | bezpieczne |
| B3 | `erp_faktury` ⋈ `erp_pozycje`, suma pozycji | sekcje 6, 9 | 47 333 → 159 627 | 146 334 539,98 → 146 334 539,91 | — | bezpieczne (0,07 zł to zaokrąglenia korekt) |
| B3′ | to samo, suma `kwota_netto` z nagłówka | (pułapka) | 47 333 → 159 627 | → 541 310 097,51 | — | **mnoży ×3,7** |
| B4 | `erp_pozycje` ⋈ `erp_kartoteka` po `indeks` | sekcje 6, 9 | 159 627 → 159 627 | 146 334 539,91 → bez zmian | — | bezpieczne, ale 38% netto ma kategorię NULL (sekcja 6) |
| B5 | `erp_platnosci` ⋈ `erp_faktury` po `nr_faktury` | sekcja 6 | 44 712 → 44 712 | 174 617 568,43 → bez zmian | — | bezpieczne |
| B5′ | `erp_faktury` ⋈ `erp_platnosci`, INNER | (pułapka) | 47 333 → 44 712 | → 141 965 502,13 (−4 369 037,85) | 1 445 → 4 dokumenty; 4 858 331,65 → 5 113,23 | **gubi korekty i faktury niezapłacone**; potrzebny LEFT JOIN |
| B6 | `erp_faktury` ⋈ `erp_kontrahenci` (tylko aktywni) | (pułapka) | 47 333 → 38 929 | → 123 167 372,11 (−23 167 167,87) | 1 445 → 1 437; −10 928,98 | **gubi 8 404 faktury kontrahentów z archiwum** |
| B6+ | `erp_faktury` ⋈ (aktywni ∪ archiwum) | sekcja 9 | 47 333 → 47 333 | bez zmian | bez zmian | bezpieczne |
| B7 | `erp_faktury` → NIP (cyfry) → wszyscy kontrahenci z tym NIP-em | (pułapka, np. łączenie z CRM lub rejestrem po NIP-ie) | 47 333 → 50 108 | → 155 345 843,91 (+9 011 303,93) | 1 445 → 1 553; +400 049,68 | **dubluje 2 775 faktur 105 par duplikatów** |
| B8 | `ecom_pozycje` ⋈ `ecom_produkty` po `sku`, INNER | sekcja 4 (analiza cen) | 518 082 → 320 212 | 19 448 220,80 → 16 589 762,68 | −98 284,84 | **gubi 197 870 wierszy `DOSTAWA`** (−2 858 458,12); w sekcji 4 było to zamierzone, ale do sum potrzebny LEFT JOIN |

Wnioski z obu tabel:
- **Złączenia bezpieczne** to te, w których klucz po stronie dołączanej jest unikalny: słowniki (`pos_produkty`, `lokale`, `erp_kartoteka`, kursy NBP przez `ASOF`) oraz agregat pozycji po kluczu dokumentu.
- **Ryzykowne są cztery wzorce:**
  - suma kwoty nagłówka po złączeniu z pozycjami (A1′, A2′, B3′);
  - złączenie INNER z tabelą, która nie pokrywa wszystkich dokumentów (B5′, B8);
  - złączenie faktur z samymi aktywnymi kontrahentami (B6);
  - łączenie po NIP-ie bez wcześniejszego scalenia duplikatów (B7). We wrześniu zawyżyłoby to ERP o 0,40 mln.

### 10.6 SQL

```sql
-- POS: kandydaci na klucz paragonu
SELECT count(*) AS wiersze,
       count(DISTINCT (lokal, nr_paragonu, data_czas::DATE)) AS lokal_nr_data,
       count(DISTINCT (lokal, nr_paragonu)) AS lokal_nr,
       count(DISTINCT nr_paragonu) AS sam_nr
FROM pos_paragony;

-- POS: powtórzone paragony różnią się tylko nazwą pliku (wynik: 0)
SELECT count(*) FROM (
  SELECT lokal, nr_paragonu, data_czas::DATE,
         count(DISTINCT (data_czas, kwota_brutto, coalesce(metoda_platnosci, ''), storno, coalesce(kanal, ''))) AS warianty
  FROM pos_paragony GROUP BY ALL HAVING count(*) > 1)
WHERE warianty > 1;

-- ERP: numer faktury (surowy, ujednolicony, format) i ciągłość numeracji
SELECT count(*) AS wiersze, count(DISTINCT nr_faktury) AS unikalne,
       count(DISTINCT upper(regexp_replace(nr_faktury, '\s', '', 'g'))) AS unikalne_po_ujednoliceniu,
       count(*) FILTER (WHERE NOT regexp_full_match(nr_faktury, '(FV/\d{4}/\d{2}/\d{5}|KOR/\d{4}/\d{2}/\d{4})')) AS zly_format
FROM erp_faktury;

WITH f AS (SELECT split_part(nr_faktury, '/', 1) AS typ, substr(nr_faktury, strpos(nr_faktury, '/') + 1, 7) AS mies,
                  regexp_extract(nr_faktury, '(\d+)$', 1)::INT AS nr FROM erp_faktury)
SELECT typ, count(DISTINCT mies) AS miesiace, sum(mx - n) AS luki
FROM (SELECT typ, mies, count(*) AS n, max(nr) AS mx FROM f GROUP BY ALL) GROUP BY 1;

-- Kontrahenci: ujednolicenie NIP i nazwy
CREATE OR REPLACE TEMP MACRO nip10(x) AS regexp_replace(x, '[^0-9]', '', 'g');
CREATE OR REPLACE TEMP MACRO nazwa_n1(x) AS trim(regexp_replace(upper(x), '\s+', ' ', 'g'));
CREATE OR REPLACE TEMP MACRO nazwa_n2(x) AS trim(regexp_replace(
    regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(
      regexp_replace(nazwa_n1(x), '[.,]', '', 'g'),
      'SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ|SPÓŁKA Z OO|SP Z OO', 'SP Z OO', 'g'),
      'SPÓŁKA AKCYJNA|\bSA\b', 'SA', 'g'),
      '\bSP K\b|\bSPK\b|SPÓŁKA KOMANDYTOWA', 'SPK', 'g'),
      '\bS C\b|\bSC\b|SPÓŁKA CYWILNA', 'SC', 'g'),
      '\bSP J\b|\bSPJ\b|SPÓŁKA JAWNA', 'SPJ', 'g'),
    '\s+', ' ', 'g'));
CREATE OR REPLACE TEMP MACRO nazwa_n3(x) AS regexp_replace(nazwa_n2(x), '^(BIURO|BIUROWIEC|STUDIO|HUB|PARK|CENTRUM|GRUPA) ', '');

-- Unikalność kontrahentów na kolejnych poziomach ujednolicenia
WITH k AS (SELECT *, nip10(nip) AS n10 FROM erp_kontrahenci),
lv AS (
    SELECT 1 AS lp, 'id_kontrahenta' AS klucz, id_kontrahenta::VARCHAR AS v, n10 FROM k
    UNION ALL SELECT 2, 'NIP surowy', nip, n10 FROM k
    UNION ALL SELECT 3, 'NIP (cyfry)', n10, n10 FROM k
    UNION ALL SELECT 4, 'nazwa surowa', nazwa, n10 FROM k
    UNION ALL SELECT 5, 'nazwa N1', nazwa_n1(nazwa), n10 FROM k
    UNION ALL SELECT 6, 'nazwa N2', nazwa_n2(nazwa), n10 FROM k
    UNION ALL SELECT 7, 'nazwa N3', nazwa_n3(nazwa), n10 FROM k
    UNION ALL SELECT 8, 'NIP + nazwa N2', n10 || '|' || nazwa_n2(nazwa), n10 FROM k
    UNION ALL SELECT 9, 'NIP + nazwa N3', n10 || '|' || nazwa_n3(nazwa), n10 FROM k
    UNION ALL SELECT 10, 'adres + kod', nazwa_n1(adres) || '|' || kod_pocztowy, n10 FROM k
    UNION ALL SELECT 11, 'id_biura_crm', id_biura_crm, n10 FROM k WHERE id_biura_crm IS NOT NULL
),
g AS (SELECT lp, klucz, v, count(*) AS c, count(DISTINCT n10) AS nipy FROM lv GROUP BY ALL)
SELECT klucz, count(*) AS unikalne, count(*) FILTER (WHERE c > 1) AS grupy_powtorzen,
       count(*) FILTER (WHERE c > 1 AND nipy = 1) AS ten_sam_nip, count(*) FILTER (WHERE c > 1 AND nipy > 1) AS rozne_nipy
FROM g GROUP BY lp, klucz ORDER BY lp;

-- Pary różnych NIP-ów o tej samej nazwie N2: uszkodzony NIP (brak jednej cyfry) czy różne firmy
WITH k AS (SELECT *, nip10(nip) AS n10, nazwa_n2(nazwa) AS n2, nazwa_n1(adres) || '|' || kod_pocztowy AS adr FROM erp_kontrahenci)
SELECT a.id_kontrahenta, a.nazwa, a.nip, b.id_kontrahenta AS id_2, b.nazwa AS nazwa_2, b.nip AS nip_2,
       a.adr = b.adr AS ten_sam_adres,
       EXISTS (SELECT 1 FROM range(1, 11) r(i)
               WHERE length(a.n10) + length(b.n10) = 19
                 AND (substr(a.n10, 1, i - 1) || substr(a.n10, i + 1) = b.n10
                   OR substr(b.n10, 1, i - 1) || substr(b.n10, i + 1) = a.n10)) AS nip_bez_jednej_cyfry
FROM k a JOIN k b ON a.n2 = b.n2 AND a.n10 < b.n10
ORDER BY nip_bez_jednej_cyfry DESC, 1;

-- Pary rekordów z tym samym NIP-em: na którym poziomie zgadza się nazwa i adres
WITH k AS (SELECT *, nip10(nip) AS n10, nazwa_n1(nazwa) AS n1, nazwa_n2(nazwa) AS n2, nazwa_n3(nazwa) AS n3,
                  nazwa_n1(adres) || '|' || kod_pocztowy AS adr FROM erp_kontrahenci)
SELECT count(*) AS pary,
       count(*) FILTER (WHERE a.nazwa = b.nazwa) AS nazwa_surowa, count(*) FILTER (WHERE a.n1 = b.n1) AS n1,
       count(*) FILTER (WHERE a.n2 = b.n2) AS n2, count(*) FILTER (WHERE a.n3 = b.n3) AS n3,
       count(*) FILTER (WHERE a.adr = b.adr) AS adres
FROM k a JOIN k b ON a.n10 = b.n10 AND a.id_kontrahenta < b.id_kontrahenta;

-- Mapa duplikatów: rekord 26xxxx -> starszy rekord pod tym samym adresem (112 par, 1:1)
WITH k AS (SELECT *, nip10(nip) AS n10, nazwa_n1(adres) || '|' || kod_pocztowy AS adr FROM erp_kontrahenci)
SELECT b.id_kontrahenta AS id_duplikatu, a.id_kontrahenta AS id_glowny,
       a.n10 = b.n10 AS ten_sam_nip, nazwa_n3(a.nazwa) = nazwa_n3(b.nazwa) AS ta_sama_nazwa_n3
FROM k a JOIN k b ON a.adr = b.adr AND a.id_kontrahenta < 260000 AND b.id_kontrahenta >= 260000
ORDER BY ten_sam_nip, 1;
```

```sql
-- A. Złączenia używane w docs/trzy_przychody.md (wrzesień 2026)
WITH
pos_wrz AS (SELECT * FROM pos_paragony WHERE data_czas >= '2026-09-01' AND data_czas < '2026-10-01'),
pos_netto AS (SELECT lokal, nr_paragonu, sum(ilosc * cena_brutto / (1 + vat / 100.0)) AS netto FROM pos_pozycje GROUP BY ALL),
zam_wrz AS (SELECT * FROM ecom_zamowienia WHERE data_utc >= '2026-09-01' AND data_utc < '2026-10-01')
SELECT 'A1 pos_paragony ⋈ pos_netto (agregat pos_pozycje) USING (lokal, nr_paragonu)' AS zlaczenie,
       (SELECT count(*) FROM pos_wrz) AS wiersze_przed, (SELECT sum(kwota_brutto) FROM pos_wrz)::DOUBLE AS suma_przed,
       count(*) AS wiersze_po, sum(r.kwota_brutto)::DOUBLE AS suma_po
FROM pos_wrz r JOIN pos_netto n USING (lokal, nr_paragonu)
UNION ALL
SELECT 'A1-pułapka: pos_paragony ⋈ pos_pozycje (bez agregacji)',
       (SELECT count(*) FROM pos_wrz), (SELECT sum(kwota_brutto) FROM pos_wrz)::DOUBLE, count(*), sum(r.kwota_brutto)::DOUBLE
FROM pos_wrz r JOIN pos_pozycje p USING (lokal, nr_paragonu)
UNION ALL
SELECT 'A2 ecom_pozycje ⋈ ecom_zamowienia ON id (suma pozycji)',
       (SELECT count(*) FROM zam_wrz), (SELECT sum(brutto) FROM zam_wrz), count(*), sum(p.ilosc * p.cena_brutto)
FROM zam_wrz z JOIN ecom_pozycje p ON p.id_zamowienia = z.id
UNION ALL
SELECT 'A2-pułapka: ta sama, ale suma brutto z nagłówka',
       (SELECT count(*) FROM zam_wrz), (SELECT sum(brutto) FROM zam_wrz), count(*), sum(z.brutto)
FROM zam_wrz z JOIN ecom_pozycje p ON p.id_zamowienia = z.id
UNION ALL
SELECT 'A3 ecom_zamowienia (EUR) ASOF LEFT JOIN kursy_nbp, kurs z dnia',
       (SELECT count(*) FROM zam_wrz WHERE waluta = 'EUR'), (SELECT sum(brutto) FROM zam_wrz WHERE waluta = 'EUR'),
       count(*) FILTER (WHERE k.eur_pln IS NOT NULL), sum(z.brutto) FILTER (WHERE k.eur_pln IS NOT NULL)
FROM zam_wrz z ASOF LEFT JOIN kursy_nbp k ON z.data_utc::DATE >= k.data WHERE z.waluta = 'EUR'
UNION ALL
SELECT 'A4 ecom_zamowienia (EUR) ASOF LEFT JOIN kursy_nbp, kurs z poprzedniego dnia roboczego',
       (SELECT count(*) FROM zam_wrz WHERE waluta = 'EUR'), (SELECT sum(brutto) FROM zam_wrz WHERE waluta = 'EUR'),
       count(*) FILTER (WHERE k.eur_pln IS NOT NULL), sum(z.brutto) FILTER (WHERE k.eur_pln IS NOT NULL)
FROM zam_wrz z ASOF LEFT JOIN kursy_nbp k ON z.data_utc::DATE > k.data WHERE z.waluta = 'EUR';
```

```sql
-- B. Złączenia używane w analizach docs/profil_danych.md (cały okres)
SELECT 'B1 pos_pozycje ⋈ pos_produkty USING (kod_produktu)' AS zlaczenie,
       (SELECT count(*) FROM pos_pozycje) AS wiersze_przed, (SELECT sum(ilosc * cena_brutto) FROM pos_pozycje) AS suma_przed,
       count(*) AS wiersze_po, sum(p.ilosc * p.cena_brutto) AS suma_po
FROM pos_pozycje p JOIN pos_produkty USING (kod_produktu)
UNION ALL
SELECT 'B2 pos_paragony ⋈ lokale USING (lokal)',
       (SELECT count(*) FROM pos_paragony), (SELECT sum(kwota_brutto) FROM pos_paragony)::DOUBLE, count(*), sum(r.kwota_brutto)::DOUBLE
FROM pos_paragony r JOIN lokale USING (lokal)
UNION ALL
SELECT 'B3 erp_faktury ⋈ erp_pozycje USING (nr_faktury), suma pozycji',
       (SELECT count(*) FROM erp_faktury), (SELECT sum(kwota_netto) FROM erp_faktury), count(*), sum(p.ilosc * p.cena)
FROM erp_faktury f JOIN erp_pozycje p USING (nr_faktury)
UNION ALL
SELECT 'B3-pułapka: ta sama, ale suma kwota_netto z nagłówka',
       (SELECT count(*) FROM erp_faktury), (SELECT sum(kwota_netto) FROM erp_faktury), count(*), sum(f.kwota_netto)
FROM erp_faktury f JOIN erp_pozycje p USING (nr_faktury)
UNION ALL
SELECT 'B4 erp_pozycje ⋈ erp_kartoteka USING (indeks)',
       (SELECT count(*) FROM erp_pozycje), (SELECT sum(ilosc * cena) FROM erp_pozycje), count(*), sum(p.ilosc * p.cena)
FROM erp_pozycje p JOIN erp_kartoteka USING (indeks)
UNION ALL
SELECT 'B5 erp_platnosci ⋈ erp_faktury USING (nr_faktury)',
       (SELECT count(*) FROM erp_platnosci), (SELECT sum(kwota) FROM erp_platnosci), count(*), sum(p.kwota)
FROM erp_platnosci p JOIN erp_faktury USING (nr_faktury)
UNION ALL
SELECT 'B5-odwrotnie: erp_faktury ⋈ erp_platnosci (INNER), suma netto faktur',
       (SELECT count(*) FROM erp_faktury), (SELECT sum(kwota_netto) FROM erp_faktury), count(*), sum(f.kwota_netto)
FROM erp_faktury f JOIN erp_platnosci USING (nr_faktury)
UNION ALL
SELECT 'B6 erp_faktury ⋈ erp_kontrahenci (tylko aktywni) USING (id_kontrahenta)',
       (SELECT count(*) FROM erp_faktury), (SELECT sum(kwota_netto) FROM erp_faktury), count(*), sum(f.kwota_netto)
FROM erp_faktury f JOIN erp_kontrahenci USING (id_kontrahenta)
UNION ALL
SELECT 'B6+ erp_faktury ⋈ (aktywni ∪ archiwum) USING (id_kontrahenta)',
       (SELECT count(*) FROM erp_faktury), (SELECT sum(kwota_netto) FROM erp_faktury), count(*), sum(f.kwota_netto)
FROM erp_faktury f JOIN (SELECT id_kontrahenta FROM erp_kontrahenci UNION ALL SELECT id_kontrahenta FROM erp_kontrahenci_archiwum) k USING (id_kontrahenta)
UNION ALL
SELECT 'B7 erp_faktury → NIP kontrahenta → wszyscy kontrahenci z tym NIP (cyfry)',
       (SELECT count(*) FROM erp_faktury), (SELECT sum(kwota_netto) FROM erp_faktury), count(*), sum(f.kwota_netto)
FROM erp_faktury f
JOIN (SELECT id_kontrahenta, regexp_replace(nip, '[^0-9]', '', 'g') AS n10 FROM erp_kontrahenci
      UNION ALL SELECT id_kontrahenta, regexp_replace(nip, '[^0-9]', '', 'g') FROM erp_kontrahenci_archiwum) a USING (id_kontrahenta)
JOIN (SELECT regexp_replace(nip, '[^0-9]', '', 'g') AS n10 FROM erp_kontrahenci
      UNION ALL SELECT regexp_replace(nip, '[^0-9]', '', 'g') FROM erp_kontrahenci_archiwum) b USING (n10)
UNION ALL
SELECT 'B8 ecom_pozycje ⋈ ecom_produkty USING (sku), INNER',
       (SELECT count(*) FROM ecom_pozycje), (SELECT sum(ilosc * cena_brutto) FROM ecom_pozycje), count(*), sum(p.ilosc * p.cena_brutto)
FROM ecom_pozycje p JOIN ecom_produkty USING (sku);
```

```sql
-- C. Te same złączenia ERP i e-commerce, zawężone do września 2026
WITH
fv AS (SELECT * FROM erp_faktury WHERE data >= '2026-09-01' AND data < '2026-10-01'),
kontr AS (SELECT id_kontrahenta, regexp_replace(nip, '[^0-9]', '', 'g') AS n10 FROM erp_kontrahenci
          UNION ALL SELECT id_kontrahenta, regexp_replace(nip, '[^0-9]', '', 'g') FROM erp_kontrahenci_archiwum),
poz AS (SELECT p.* FROM ecom_pozycje p JOIN ecom_zamowienia z ON z.id = p.id_zamowienia
        WHERE z.data_utc >= '2026-09-01' AND z.data_utc < '2026-10-01')
SELECT 'C1 erp_faktury ⋈ erp_kontrahenci (tylko aktywni)' AS zlaczenie,
       (SELECT count(*) FROM fv) AS wiersze_przed, (SELECT sum(kwota_netto) FROM fv) AS suma_przed, count(*) AS wiersze_po, sum(f.kwota_netto) AS suma_po
FROM fv f JOIN erp_kontrahenci USING (id_kontrahenta)
UNION ALL
SELECT 'C2 erp_faktury → NIP → wszyscy kontrahenci z tym NIP',
       (SELECT count(*) FROM fv), (SELECT sum(kwota_netto) FROM fv), count(*), sum(f.kwota_netto)
FROM fv f JOIN kontr a USING (id_kontrahenta) JOIN kontr b USING (n10)
UNION ALL
SELECT 'C3 erp_faktury ⋈ erp_platnosci (INNER)',
       (SELECT count(*) FROM fv), (SELECT sum(kwota_netto) FROM fv), count(*), sum(f.kwota_netto)
FROM fv f JOIN erp_platnosci USING (nr_faktury)
UNION ALL
SELECT 'C4 ecom_pozycje ⋈ ecom_produkty (INNER)',
       (SELECT count(*) FROM poz), (SELECT sum(ilosc * cena_brutto) FROM poz), count(*), sum(p.ilosc * p.cena_brutto)
FROM poz p JOIN ecom_produkty USING (sku);
```
