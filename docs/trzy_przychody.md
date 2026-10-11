# Trzy przychody za wrzesień 2026

Za wrzesień 2026 dashboard BI, raport sprzedaży i księgowość podają trzy różne przychody: 8,31 / 8,06 / 7,92 mln zł. Ten dokument odtwarza każdą z tych liczb w SQL na `kawosz.duckdb` (otwartej `read_only`) według opisu jej definicji z audytu. Każdą liczę dosłownie według opisu, a decyzje, których opis nie rozstrzyga, wypisuję jawnie. Gdy wynik się nie zgadza, podaję różnicę i wpływ pojedynczych zmian interpretacji, każdej osobno. Nie składam zmian w kombinacje, które trafiają w docelową liczbę, bo przy dokładności 0,01 mln trafia w nią wiele różnych kombinacji i takie trafienie niczego nie dowodzi.

Opis tabel, walut i stref czasowych: [`docs/profil_danych.md`](profil_danych.md).

## Podsumowanie: trzy raporty obok siebie

Wyniki dosłowne według opisów z audytu, w zł. Ostatnie trzy kolumny to różnice między raportami.

| Źródło | Dashboard BI | Raport sprzedaży | Księgowość | Sprzedaż − BI | Księgowość − BI | Księgowość − Sprzedaż |
|---|---:|---:|---:|---:|---:|---:|
| POS (`pos_paragony`) | 2 187 234,00 | 2 009 413,93 | 2 009 413,93 | −177 820,07 | −177 820,07 | 0,00 |
| E-commerce: zamówienia | 677 061,42 | 550 456,44 | 677 061,42 | −126 604,98 | 0,00 | +126 604,98 |
| E-commerce: subskrypcje | 437 178,00 | 355 429,27 | 437 178,00 | −81 748,73 | 0,00 | +81 748,73 |
| Karty podarunkowe | 77 100,00 | 77 100,00 | 77 100,00 | 0,00 | 0,00 | 0,00 |
| ERP (`erp_faktury`) | 4 858 331,65 | 4 858 331,65 | 4 858 331,65 | 0,00 | 0,00 | 0,00 |
| **Razem (dosłownie)** | **8 236 905,07** | **7 850 731,29** | **8 059 085,00** | **−386 173,78** | **−177 820,07** | **+208 353,71** |
| Razem [mln] | 8,24 | 7,85 | 8,06 | −0,39 | −0,18 | +0,21 |
| **Liczba z raportu [mln]** | **8,31** | **8,06** | **7,92** | −0,25 | −0,39 | −0,14 |
| Wynik − liczba z raportu [mln] | −0,07 | −0,21 | +0,14 | | | |
| Status | nie odtworzone | nie odtworzone | nie odtworzone | | | |

Najważniejsze wnioski:
- **Żadnej z trzech liczb nie odtworzyłem dosłownie z dokładnością 0,01 mln.**
- **Karty podarunkowe i ERP są takie same we wszystkich trzech definicjach.** Różnice między raportami biorą się wyłącznie z VAT: w POS (177 820,07 zł) i w e-commerce (208 353,71 zł).
- **Według opisów księgowość powinna być wyższa niż raport sprzedaży**, bo zostawia e-commerce w brutto. Według podanych liczb jest o 0,14 mln niższa. Przy tych danych oba opisy nie mogą być jednocześnie kompletne. Najmniej określony element to e-commerce: netto czy brutto, zwroty, waluta i strefa czasowa.
- **Tylko jedna pojedyncza zmiana trafia w liczbę z raportu:** raport sprzedaży z e-commerce zostawionym w brutto daje 8 059 085,00 zł, czyli 8,06 mln. To dokładnie wynik dosłownej definicji księgowości. Wymaga to potwierdzenia u autorów raportu (sekcja 2.5).

## 1. Dashboard BI — 8,31 mln

### 1.1 Definicja

**Z audytu:** analityk BI sumuje kwoty ze wszystkich źródeł (POS, e-commerce, karty podarunkowe, ERP) tak, jak leżą w tabelach, bez żadnych poprawek.

**Słowami, w moim odczytaniu:** dla każdego źródła biorę tabelę dokumentów sprzedaży i sumuję jej kolumnę z kwotą za wiersze z datą od 1 do 30 września 2026 włącznie. Nie przeliczam walut i stref czasowych, nie przechodzę z netto na brutto, niczego nie deduplikuję ani nie wykluczam. Wyniki ze źródeł dodaję do siebie.

Opis zostawia kilka decyzji otwartych. Przyjąłem następujące:

| # | Decyzja | Przyjęte | Dlaczego |
|---:|---|---|---|
| Z1 | Tabela POS | `pos_paragony.kwota_brutto` (nagłówki paragonów) | `pos_pozycje` to szczegóły tych samych paragonów, więc dodanie ich policzyłoby sprzedaż dwa razy |
| Z2 | Tabele e-commerce | `ecom_zamowienia.brutto` + `ecom_subskrypcje.kwota` | obie to sprzedaż sklepu (zamówienia i płatności subskrypcji); `ecom_pozycje` to szczegóły zamówień |
| Z3 | Karty podarunkowe | `karty_podarunkowe.kwota` według `data_sprzedazy` | wiersz karty ma jedną kwotę i dwie daty, a „kwota z tabeli” to nominał sprzedanej karty |
| Z4 | ERP | `erp_faktury.kwota_netto`, faktury i korekty | to kolumna z kwotą dokumentu; `vat` to osobna kolumna, a `erp_platnosci` to wpłaty za te same faktury |
| Z5 | Miesiąc | `>= '2026-09-01' AND < '2026-10-01'` na natywnej kolumnie daty każdej tabeli | „jak leży”: e-commerce i subskrypcje w UTC, POS w czasie lokalnym, ERP i karty jako daty |
| Z6 | Bez poprawek | zostają duplikaty plików POS, storna, zamówienia testowe i zwroty, EUR sumowane z PLN, korekty ERP | zgodnie z opisem |

### 1.2 Wynik

| Źródło | Tabela i kolumna | Kolumna daty | Wiersze | Kwota [zł] |
|---|---|---|---:|---:|
| POS | `pos_paragony.kwota_brutto` | `data_czas` (lokalny) | 70 097 | 2 187 234,00 |
| E-commerce | `ecom_zamowienia.brutto` | `data_utc` (UTC) | 7 639 | 677 061,42 |
| E-commerce | `ecom_subskrypcje.kwota` | `data_platnosci` (UTC) | 8 302 | 437 178,00 |
| Karty podarunkowe | `karty_podarunkowe.kwota` | `data_sprzedazy` | 562 | 77 100,00 |
| ERP | `erp_faktury.kwota_netto` | `data` | 1 445 | 4 858 331,65 |
| **Razem** | | | **88 045** | **8 236 905,07** |

E-commerce łącznie daje 1 114 239,42 zł. W kwocie zamówień jest 11 461,76 EUR (436 zamówień) dodanych do złotych bez przeliczenia, co jest zgodne z opisem „bez poprawek”.

**Wynik dosłowny to 8,24 mln, a nie 8,31 mln.** Różnica wynosi −0,07 mln. Żeby wynik zaokrąglił się do 8,31, suma musiałaby wynosić od 8 305 000 do 8 315 000 zł, czyli brakuje od ok. 68 095 do 78 095 zł. **Nie odtworzyłem liczby z dashboardu z dokładnością 0,01 mln.**

### 1.3 SQL

```sql
-- Przychód BI za wrzesień 2026: suma kwot ze wszystkich źródeł tak, jak leżą w tabelach
WITH zrodla AS (
    SELECT 1 AS lp, 'POS' AS zrodlo, 'pos_paragony.kwota_brutto' AS kolumna,
           count(*) AS wiersze, sum(kwota_brutto)::DECIMAL(14,2) AS kwota
    FROM pos_paragony
    WHERE data_czas >= '2026-09-01' AND data_czas < '2026-10-01'
    UNION ALL
    SELECT 2, 'E-commerce', 'ecom_zamowienia.brutto', count(*), sum(brutto)::DECIMAL(14,2)
    FROM ecom_zamowienia
    WHERE data_utc >= '2026-09-01' AND data_utc < '2026-10-01'
    UNION ALL
    SELECT 3, 'E-commerce', 'ecom_subskrypcje.kwota', count(*), sum(kwota)::DECIMAL(14,2)
    FROM ecom_subskrypcje
    WHERE data_platnosci >= '2026-09-01' AND data_platnosci < '2026-10-01'
    UNION ALL
    SELECT 4, 'Karty podarunkowe', 'karty_podarunkowe.kwota', count(*), sum(kwota)::DECIMAL(14,2)
    FROM karty_podarunkowe
    WHERE data_sprzedazy >= '2026-09-01' AND data_sprzedazy < '2026-10-01'
    UNION ALL
    SELECT 5, 'ERP', 'erp_faktury.kwota_netto', count(*), sum(kwota_netto)::DECIMAL(14,2)
    FROM erp_faktury
    WHERE data >= '2026-09-01' AND data < '2026-10-01'
)
SELECT lp, zrodlo, kolumna, wiersze, kwota FROM zrodla
UNION ALL
SELECT 6, 'RAZEM', NULL, sum(wiersze), sum(kwota) FROM zrodla
ORDER BY lp;
```

### 1.4 Wpływ pojedynczych zmian interpretacji

Każdy wiersz zmienia **jedną** decyzję z 1.1 i niczego poza tym. Wiersze się nie sumują.

| # | Zmiana (zamiast decyzji) | Wpływ [zł] | Wynik [zł] | mln |
|---:|---|---:|---:|---:|
| 1 | Karty według `data_realizacji` zamiast `data_sprzedazy` (Z3) | −24 600,00 | 8 212 305,07 | 8,21 |
| 2 | Karty liczone przy sprzedaży i przy realizacji (Z3) | +52 500,00 | 8 289 405,07 | 8,29 |
| 3 | Bez kart podarunkowych (Z3) | −77 100,00 | 8 159 805,07 | 8,16 |
| 4 | ERP brutto: `kwota_netto + vat` (Z4) | +1 117 416,30 | 9 354 321,37 | 9,35 |
| 5 | ERP: wpływy z `erp_platnosci` zamiast faktur (Z4) | +259 933,56 | 8 496 838,63 | 8,50 |
| 6 | ERP bez korekt (Z4) | +13 770,08 | 8 250 675,15 | 8,25 |
| 7 | POS z `pos_pozycje` zamiast `pos_paragony` (Z1) | −32 684,00 | 8 204 221,07 | 8,20 |
| 8 | E-commerce z `ecom_pozycje` zamiast `ecom_zamowienia` (Z2) | 0,00 | 8 236 905,07 | 8,24 |
| 9 | Zamówienia e-commerce w czasie warszawskim (Z5) | +4 286,81 | 8 241 191,88 | 8,24 |
| 10 | Subskrypcje w czasie warszawskim (Z5) | +7 428,00 | 8 244 333,07 | 8,24 |
| 11 | Zamówienia w EUR przeliczone kursem NBP z dnia zamówienia (Z6) | +36 859,69 | 8 273 764,76 | 8,27 |
| 12 | Filtr `BETWEEN '2026-09-01' AND '2026-09-30'` na znacznikach czasu, który ucina 30.09 po północy (Z5) | −97 527,81 | 8 139 377,26 | 8,14 |
| 13 | Bez subskrypcji, czyli e-commerce = same zamówienia (Z2) | −437 178,00 | 7 799 727,07 | 7,80 |

**Żadna pojedyncza zmiana nie daje 8,31.** Najbliżej są:
- wiersz 2 (karty liczone dwa razy: przy sprzedaży i przy realizacji): 8,29;
- wiersz 11 (przeliczenie EUR, czyli poprawka, której według opisu BI nie robi): 8,27.

Wiersz 8 to kontrola: pozycje e-commerce sumują się do nagłówków zamówień co do grosza, więc wybór tabeli e-commerce nie ma znaczenia.

```sql
-- Wpływ pojedynczych zmian interpretacji (każda osobno, względem wyniku dosłownego)
WITH
waw_zam AS (SELECT *, timezone('Europe/Warsaw', data_utc::TIMESTAMP AT TIME ZONE 'UTC') AS t FROM ecom_zamowienia),
waw_sub AS (SELECT *, timezone('Europe/Warsaw', data_platnosci AT TIME ZONE 'UTC') AS t FROM ecom_subskrypcje),
w(lp, zmiana, wplyw) AS (
    SELECT 1, 'Karty po data_realizacji zamiast data_sprzedazy',
           (SELECT sum(kwota) FROM karty_podarunkowe WHERE data_realizacji >= '2026-09-01' AND data_realizacji < '2026-10-01')
         - (SELECT sum(kwota) FROM karty_podarunkowe WHERE data_sprzedazy  >= '2026-09-01' AND data_sprzedazy  < '2026-10-01')
    UNION ALL SELECT 2, 'Karty liczone przy sprzedaży i przy realizacji',
           (SELECT sum(kwota) FROM karty_podarunkowe WHERE data_realizacji >= '2026-09-01' AND data_realizacji < '2026-10-01')
    UNION ALL SELECT 3, 'Bez kart podarunkowych',
         - (SELECT sum(kwota) FROM karty_podarunkowe WHERE data_sprzedazy >= '2026-09-01' AND data_sprzedazy < '2026-10-01')
    UNION ALL SELECT 4, 'ERP brutto (kwota_netto + vat)',
           (SELECT sum(vat) FROM erp_faktury WHERE data >= '2026-09-01' AND data < '2026-10-01')
    UNION ALL SELECT 5, 'ERP: wpływy z erp_platnosci zamiast faktur',
           (SELECT sum(kwota) FROM erp_platnosci WHERE data_platnosci >= '2026-09-01' AND data_platnosci < '2026-10-01')
         - (SELECT sum(kwota_netto) FROM erp_faktury WHERE data >= '2026-09-01' AND data < '2026-10-01')
    UNION ALL SELECT 6, 'ERP bez korekt',
         - (SELECT sum(kwota_netto) FROM erp_faktury WHERE data >= '2026-09-01' AND data < '2026-10-01' AND typ = 'korekta')
    UNION ALL SELECT 7, 'POS z pos_pozycje zamiast pos_paragony',
           (SELECT sum(ilosc * cena_brutto) FROM pos_pozycje WHERE nr_paragonu BETWEEN 2609010000 AND 2609309999)
         - (SELECT sum(kwota_brutto) FROM pos_paragony WHERE data_czas >= '2026-09-01' AND data_czas < '2026-10-01')
    UNION ALL SELECT 8, 'E-commerce z ecom_pozycje zamiast ecom_zamowienia',
           (SELECT sum(p.ilosc * p.cena_brutto) FROM ecom_pozycje p JOIN ecom_zamowienia z ON z.id = p.id_zamowienia
            WHERE z.data_utc >= '2026-09-01' AND z.data_utc < '2026-10-01')
         - (SELECT sum(brutto) FROM ecom_zamowienia WHERE data_utc >= '2026-09-01' AND data_utc < '2026-10-01')
    UNION ALL SELECT 9, 'Zamówienia e-com w czasie warszawskim',
           (SELECT sum(brutto) FROM waw_zam WHERE t >= '2026-09-01' AND t < '2026-10-01')
         - (SELECT sum(brutto) FROM ecom_zamowienia WHERE data_utc >= '2026-09-01' AND data_utc < '2026-10-01')
    UNION ALL SELECT 10, 'Subskrypcje w czasie warszawskim',
           (SELECT sum(kwota) FROM waw_sub WHERE t >= '2026-09-01' AND t < '2026-10-01')
         - (SELECT sum(kwota) FROM ecom_subskrypcje WHERE data_platnosci >= '2026-09-01' AND data_platnosci < '2026-10-01')
    UNION ALL SELECT 11, 'Zamówienia w EUR przeliczone kursem NBP z dnia zamówienia',
           (SELECT sum(z.brutto * k.eur_pln - z.brutto)
            FROM ecom_zamowienia z ASOF LEFT JOIN kursy_nbp k ON z.data_utc::DATE >= k.data
            WHERE z.waluta = 'EUR' AND z.data_utc >= '2026-09-01' AND z.data_utc < '2026-10-01')
    UNION ALL SELECT 12, 'Filtr BETWEEN 2026-09-01 AND 2026-09-30 na znacznikach czasu',
           (SELECT sum(kwota_brutto) FROM pos_paragony WHERE data_czas BETWEEN '2026-09-01' AND '2026-09-30')
         - (SELECT sum(kwota_brutto) FROM pos_paragony WHERE data_czas >= '2026-09-01' AND data_czas < '2026-10-01')
         + (SELECT sum(brutto) FROM ecom_zamowienia WHERE data_utc BETWEEN '2026-09-01' AND '2026-09-30')
         - (SELECT sum(brutto) FROM ecom_zamowienia WHERE data_utc >= '2026-09-01' AND data_utc < '2026-10-01')
         + (SELECT sum(kwota) FROM ecom_subskrypcje WHERE data_platnosci BETWEEN '2026-09-01' AND '2026-09-30')
         - (SELECT sum(kwota) FROM ecom_subskrypcje WHERE data_platnosci >= '2026-09-01' AND data_platnosci < '2026-10-01')
    UNION ALL SELECT 13, 'Bez subskrypcji (e-commerce = tylko zamówienia)',
         - (SELECT sum(kwota) FROM ecom_subskrypcje WHERE data_platnosci >= '2026-09-01' AND data_platnosci < '2026-10-01')
)
SELECT lp, zmiana,
       round(wplyw, 2) AS wplyw,
       round(8236905.07 + wplyw, 2) AS wynik,
       round((8236905.07 + wplyw) / 1e6, 2) AS wynik_mln
FROM w ORDER BY lp;
```

### 1.5 Co dalej: pytania do analityka BI

Do zamknięcia różnicy potrzebna jest definicja miary z narzędzia BI (SQL albo konfiguracja), a nie dalsze zgadywanie. Konkretnie:

1. **Źródła i kolumny:** które tabele i kolumny wchodzą do miary? Czy e-commerce obejmuje subskrypcje? Czy ERP to `kwota_netto` z faktur, czy płatności? Czy dashboard ma źródła spoza tych czterech?
2. **Karty podarunkowe:** po której dacie są filtrowane: sprzedaży, realizacji czy obu? Czy karty trafiają do dashboardu tylko z `karty_podarunkowe`, czy także z innego miejsca?
3. **Filtr miesiąca:** jak zdefiniowano wrzesień (granice, strefa czasowa, `BETWEEN` czy `<`)?
4. **Waluta:** czy zamówienia w EUR są przeliczane, a jeśli tak, to jakim kursem?
5. **Stan danych:** z którego dnia i z którego ładowania pochodzi liczba 8,31? Jeśli dashboard liczono na innym eksporcie niż ten w `kawosz.duckdb` (eksport z 2026-09-30), różnica może wynikać z samych danych, a nie z definicji.

## 2. Raport sprzedaży — 8,06 mln

### 2.1 Definicja

**Z audytu:** kwoty netto, bez odejmowania zwrotów, bez łączenia zduplikowanych rekordów.

**Słowami, w moim odczytaniu:** te same źródła i ten sam miesiąc co w BI, ale każda kwota jest przeliczona na netto. Zwroty nie są odejmowane, a zduplikowane rekordy zostają.

Decyzje, których opis nie rozstrzyga:

| # | Decyzja | Przyjęte | Dlaczego |
|---:|---|---|---|
| S1 | Źródła | jak w BI: POS, e-commerce (zamówienia + subskrypcje), karty podarunkowe, ERP | opis nie wymienia źródeł, a raport sprzedaży obejmuje całą sprzedaż |
| S2 | POS netto | `Σ ilosc × cena_brutto / (1 + vat/100)` z `pos_pozycje`, przypisane do **każdego wiersza** `pos_paragony` | stawki 8% i 23% są w pozycjach; przypisanie do nagłówków zachowuje 988 zduplikowanych paragonów, których w `pos_pozycje` nie ma |
| S3 | E-commerce netto | `brutto / 1,23` dla zamówień, `kwota / 1,23` dla subskrypcji | e-commerce ma VAT 23% (konwencja w `data/README.md`), również na wiersz `DOSTAWA` |
| S4 | Karty podarunkowe | nominał, bez przeliczenia | tabela nie ma VAT; przy sprzedaży karty wielocelowej VAT nie jest naliczany |
| S5 | ERP | `kwota_netto`, faktury i korekty | kwoty są już netto |
| S6 | Zwroty | zamówienia z `zwrot = true` zostają; ujemne paragony POS (storna, zwroty) i korekty ERP zostają tak, jak leżą | „bez odejmowania” rozumiem jako brak osobnego odejmowania zwrotów; wariant z pominięciem ujemnych paragonów jest w 2.4 |
| S7 | Duplikaty | zostają (988 paragonów z lokalu 17, 29 998,74 zł netto) | wprost z opisu |
| S8 | Miesiąc, strefa, waluta | jak w BI: natywne kolumny dat, e-commerce w UTC, EUR bez przeliczenia | opis o tym nie mówi |

### 2.2 Wynik

| Źródło | Tabela | Wiersze | Netto [zł] |
|---|---|---:|---:|
| POS | `pos_paragony` × netto z `pos_pozycje` | 70 097 | 2 009 413,93 |
| E-commerce | `ecom_zamowienia.brutto / 1,23` | 7 639 | 550 456,44 |
| E-commerce | `ecom_subskrypcje.kwota / 1,23` | 8 302 | 355 429,27 |
| Karty podarunkowe | `karty_podarunkowe.kwota` | 562 | 77 100,00 |
| ERP | `erp_faktury.kwota_netto` | 1 445 | 4 858 331,65 |
| **Razem** | | **88 045** | **7 850 731,29** |

**Wynik dosłowny to 7,85 mln, a nie 8,06 mln.** Różnica wynosi −0,21 mln. Żeby wynik zaokrąglił się do 8,06, brakuje od ok. 204 269 do 214 269 zł. **Nie odtworzyłem liczby z raportu sprzedaży z dokładnością 0,01 mln.**

### 2.3 SQL

```sql
-- Raport sprzedaży za wrzesień 2026: kwoty netto, bez odejmowania zwrotów, bez łączenia duplikatów
WITH
-- netto paragonu = suma pozycji przeliczonych stawką VAT pozycji (vat to stawka w %)
pos_netto AS (
    SELECT lokal, nr_paragonu, sum(ilosc * cena_brutto / (1 + vat / 100.0)) AS netto
    FROM pos_pozycje GROUP BY ALL
),
zrodla AS (
    -- JOIN do każdego wiersza nagłówka: zduplikowane paragony liczą się dwa razy
    SELECT 1 AS lp, 'POS' AS zrodlo, count(*) AS wiersze, sum(n.netto) AS kwota
    FROM pos_paragony r JOIN pos_netto n USING (lokal, nr_paragonu)
    WHERE r.data_czas >= '2026-09-01' AND r.data_czas < '2026-10-01'
    UNION ALL
    -- e-commerce: brutto z VAT 23%; zamówienia ze zwrotem zostają, EUR bez przeliczenia
    SELECT 2, 'E-commerce: zamówienia', count(*), sum(brutto / 1.23)
    FROM ecom_zamowienia
    WHERE data_utc >= '2026-09-01' AND data_utc < '2026-10-01'
    UNION ALL
    SELECT 3, 'E-commerce: subskrypcje', count(*), sum(kwota / 1.23)
    FROM ecom_subskrypcje
    WHERE data_platnosci >= '2026-09-01' AND data_platnosci < '2026-10-01'
    UNION ALL
    -- karta podarunkowa: nominał, tabela nie ma VAT (bon wielocelowy jest bez VAT przy sprzedaży)
    SELECT 4, 'Karty podarunkowe', count(*), sum(kwota)
    FROM karty_podarunkowe
    WHERE data_sprzedazy >= '2026-09-01' AND data_sprzedazy < '2026-10-01'
    UNION ALL
    SELECT 5, 'ERP', count(*), sum(kwota_netto)
    FROM erp_faktury
    WHERE data >= '2026-09-01' AND data < '2026-10-01'
)
SELECT lp, zrodlo, wiersze, round(kwota, 2) AS kwota FROM zrodla
UNION ALL
SELECT 6, 'RAZEM', sum(wiersze), round(sum(kwota), 2) FROM zrodla
ORDER BY lp;
```

### 2.4 Wpływ pojedynczych zmian interpretacji

Każdy wiersz zmienia **jedną** decyzję z 2.1. Wiersze się nie sumują.

| # | Zmiana (zamiast decyzji) | Wpływ [zł] | Wynik [zł] | mln |
|---:|---|---:|---:|---:|
| 1 | POS netto z samych pozycji, czyli bez duplikatów z lokalu 17 (S2, S7) | −29 998,74 | 7 820 732,55 | 7,82 |
| 2 | POS netto jedną stawką 23% od kwoty paragonu (S2) | −231 174,91 | 7 619 556,38 | 7,62 |
| 3 | POS bez paragonów ujemnych: storna i zwroty pominięte zamiast odjęte (S6) | +4 033,83 | 7 854 765,12 | 7,85 |
| 4 | Zamówienia e-commerce brutto, bez przeliczenia na netto (S3) | +126 604,98 | 7 977 336,27 | 7,98 |
| 5 | Subskrypcje brutto, bez przeliczenia na netto (S3) | +81 748,73 | 7 932 480,02 | 7,93 |
| 6 | **Całe e-commerce brutto: zamówienia i subskrypcje (S3)** | **+208 353,71** | **8 059 085,00** | **8,06** |
| 7 | Karty podarunkowe netto: nominał / 1,23 (S4) | −14 417,07 | 7 836 314,22 | 7,84 |
| 8 | Bez kart podarunkowych (S1) | −77 100,00 | 7 773 631,29 | 7,77 |
| 9 | ERP bez korekt (S6) | +13 770,08 | 7 864 501,37 | 7,86 |
| 10 | E-commerce (zamówienia i subskrypcje) w czasie warszawskim (S8) | +9 524,24 | 7 860 255,53 | 7,86 |
| 11 | Zamówienia w EUR przeliczone kursem NBP z dnia zamówienia (S8) | +29 967,23 | 7 880 698,52 | 7,88 |
| 12 | Zwroty e-commerce odjęte, czyli bez zamówień z `zwrot = true` (S6) | −71 404,43 | 7 779 326,86 | 7,78 |

```sql
-- Raport sprzedaży: wpływ pojedynczych zmian (każda osobno, względem wyniku dosłownego 7 850 731,29)
WITH
pos_netto AS (SELECT lokal, nr_paragonu, sum(ilosc * cena_brutto / (1 + vat / 100.0)) AS netto FROM pos_pozycje GROUP BY ALL),
pos_wrz AS (SELECT r.*, n.netto FROM pos_paragony r JOIN pos_netto n USING (lokal, nr_paragonu)
            WHERE r.data_czas >= '2026-09-01' AND r.data_czas < '2026-10-01'),
zam_wrz AS (SELECT * FROM ecom_zamowienia WHERE data_utc >= '2026-09-01' AND data_utc < '2026-10-01'),
sub_wrz AS (SELECT * FROM ecom_subskrypcje WHERE data_platnosci >= '2026-09-01' AND data_platnosci < '2026-10-01'),
w(lp, zmiana, wplyw) AS (
    SELECT 1, 'POS netto z samych pozycji (bez duplikatów z lokalu 17)',
           (SELECT sum(netto) FROM pos_netto WHERE nr_paragonu BETWEEN 2609010000 AND 2609309999) - (SELECT sum(netto) FROM pos_wrz)
    UNION ALL SELECT 2, 'POS netto jedną stawką 23% od kwoty paragonu',
           (SELECT sum(kwota_brutto) / 1.23 FROM pos_wrz) - (SELECT sum(netto) FROM pos_wrz)
    UNION ALL SELECT 3, 'POS bez paragonów ujemnych (storna i zwroty pominięte, a nie odjęte)',
         - (SELECT sum(netto) FROM pos_wrz WHERE kwota_brutto < 0)
    UNION ALL SELECT 4, 'Zamówienia e-commerce brutto (bez przeliczenia na netto)',
           (SELECT sum(brutto) - sum(brutto / 1.23) FROM zam_wrz)
    UNION ALL SELECT 5, 'Subskrypcje brutto (bez przeliczenia na netto)',
           (SELECT sum(kwota) - sum(kwota / 1.23) FROM sub_wrz)
    UNION ALL SELECT 6, 'Całe e-commerce brutto (zamówienia i subskrypcje)',
           (SELECT sum(brutto) - sum(brutto / 1.23) FROM zam_wrz) + (SELECT sum(kwota) - sum(kwota / 1.23) FROM sub_wrz)
    UNION ALL SELECT 7, 'Karty podarunkowe netto (nominał / 1,23)',
           (SELECT sum(kwota / 1.23) - sum(kwota) FROM karty_podarunkowe WHERE data_sprzedazy >= '2026-09-01' AND data_sprzedazy < '2026-10-01')
    UNION ALL SELECT 8, 'Bez kart podarunkowych',
         - (SELECT sum(kwota) FROM karty_podarunkowe WHERE data_sprzedazy >= '2026-09-01' AND data_sprzedazy < '2026-10-01')
    UNION ALL SELECT 9, 'ERP bez korekt',
         - (SELECT sum(kwota_netto) FROM erp_faktury WHERE data >= '2026-09-01' AND data < '2026-10-01' AND typ = 'korekta')
    UNION ALL SELECT 10, 'E-commerce (zamówienia i subskrypcje) w czasie warszawskim',
           (SELECT sum(brutto / 1.23) FROM ecom_zamowienia
            WHERE timezone('Europe/Warsaw', data_utc::TIMESTAMP AT TIME ZONE 'UTC') >= '2026-09-01'
              AND timezone('Europe/Warsaw', data_utc::TIMESTAMP AT TIME ZONE 'UTC') <  '2026-10-01')
         - (SELECT sum(brutto / 1.23) FROM zam_wrz)
         + (SELECT sum(kwota / 1.23) FROM ecom_subskrypcje
            WHERE timezone('Europe/Warsaw', data_platnosci AT TIME ZONE 'UTC') >= '2026-09-01'
              AND timezone('Europe/Warsaw', data_platnosci AT TIME ZONE 'UTC') <  '2026-10-01')
         - (SELECT sum(kwota / 1.23) FROM sub_wrz)
    UNION ALL SELECT 11, 'Zamówienia w EUR przeliczone kursem NBP z dnia zamówienia',
           (SELECT sum((z.brutto * k.eur_pln - z.brutto) / 1.23)
            FROM zam_wrz z ASOF LEFT JOIN kursy_nbp k ON z.data_utc::DATE >= k.data WHERE z.waluta = 'EUR')
    UNION ALL SELECT 12, 'Zwroty e-commerce odjęte (bez zamówień z zwrot = true)',
         - (SELECT sum(brutto / 1.23) FROM zam_wrz WHERE zwrot)
)
SELECT lp, zmiana, round(wplyw, 2) AS wplyw,
       round(7850731.29 + wplyw, 2) AS wynik, round((7850731.29 + wplyw) / 1e6, 2) AS wynik_mln
FROM w ORDER BY lp;
```

### 2.5 Co może tłumaczyć różnicę

- **Jedyna pojedyncza zmiana, która daje 8,06, to wiersz 6: e-commerce zostawione w brutto.** Oznaczałoby to, że raport sprzedaży bierze POS w netto i ERP w netto, ale kwoty ze sklepu internetowego zostawia w brutto, tak jak wychodzą z systemu sklepu. To przeczy słowom „kwoty netto” z opisu, chyba że opis dotyczy tylko POS i ERP. Zmiana obejmuje obie tabele jednego źródła. Każda z nich osobno nie wystarcza (wiersze 4 i 5 dają 7,98 i 7,93).
- **Wiersz 6 daje co do grosza ten sam wynik co dosłowna definicja księgowości** (8 059 085,00 zł, sekcja 3). Przy e-commerce w brutto oba raporty liczą dokładnie to samo. Możliwe, że opisy raportów w audycie się pomieszały. Zamiana opisów nie tłumaczy jednak 7,92, bo dosłowny raport sprzedaży daje 7,85. Dlatego nie przyjmuję tego wyjaśnienia.
- Pozostałe zmiany przesuwają wynik w złą stronę albo nie wystarczają. Najbliżej z nich jest wiersz 4 (7,98).
- Trafienie w 8,06 przy dokładności 0,01 mln samo niczego nie dowodzi. Rozstrzygnie to dopiero definicja z raportu.

Pytania do autora raportu sprzedaży:
1. Czy kwoty e-commerce (zamówienia i subskrypcje) są przeliczane na netto? Jeśli tak, jaką stawką?
2. Jak liczone jest netto POS: z pozycji według stawek 8% i 23%, z raportów fiskalnych czy jedną stawką?
3. Czy raport obejmuje karty podarunkowe i subskrypcje?
4. Czy zamówienia w EUR są przeliczane? Jaki filtr miesiąca i jaka strefa czasowa?

## 3. Księgowość — 7,92 mln

### 3.1 Definicja

**Z audytu:** ERP i POS netto, subskrypcje roczne w całości w miesiącu sprzedaży, karty podarunkowe w dniu sprzedaży.

**Słowami, w moim odczytaniu:** ERP i POS w netto. Subskrypcje, także roczne, w pełnej kwocie w miesiącu płatności, bez rozkładania na 12 miesięcy. Karty podarunkowe w dniu sprzedaży. Wszystko, czego opis nie dotyczy, tak jak w BI.

Decyzje, których opis nie rozstrzyga:

| # | Decyzja | Przyjęte | Dlaczego |
|---:|---|---|---|
| K1 | ERP | `kwota_netto`, faktury i korekty | wprost z opisu |
| K2 | POS netto | jak w raporcie sprzedaży (S2), duplikaty zostają | opis nie mówi o łączeniu duplikatów |
| K3 | Subskrypcje | `kwota` tak, jak leży, w miesiącu `data_platnosci` (UTC) | opis mówi tylko, w którym miesiącu ująć plan roczny; netto wymienia tylko dla ERP i POS |
| K4 | Karty podarunkowe | `kwota` według `data_sprzedazy` | wprost z opisu |
| K5 | Zamówienia e-commerce | **opis ich nie wymienia.** Biorę je tak, jak leżą (brutto, UTC, EUR bez przeliczenia, zwroty zostają) | to sprzedaż firmy, a cztery źródła są wspólne dla trzech raportów; wariant bez nich jest w 3.4 |
| K6 | Miesiąc | natywne kolumny dat, `>= '2026-09-01' AND < '2026-10-01'` | jak w BI |

### 3.2 Wynik

| Źródło | Tabela | Wiersze | Kwota [zł] |
|---|---|---:|---:|
| POS | `pos_paragony` × netto z `pos_pozycje` | 70 097 | 2 009 413,93 |
| E-commerce | `ecom_zamowienia.brutto` | 7 639 | 677 061,42 |
| E-commerce | `ecom_subskrypcje.kwota` (w tym 315 planów rocznych: 125 685,00) | 8 302 | 437 178,00 |
| Karty podarunkowe | `karty_podarunkowe.kwota` | 562 | 77 100,00 |
| ERP | `erp_faktury.kwota_netto` | 1 445 | 4 858 331,65 |
| **Razem** | | **88 045** | **8 059 085,00** |

**Wynik dosłowny to 8,06 mln, a nie 7,92 mln.** Różnica wynosi +0,14 mln. Żeby wynik zaokrąglił się do 7,92, trzeba by odjąć od ok. 134 085 do 144 085 zł. **Nie odtworzyłem liczby księgowości z dokładnością 0,01 mln.**

### 3.3 SQL

```sql
-- Księgowość za wrzesień 2026: ERP i POS netto, subskrypcje roczne w całości w miesiącu sprzedaży,
-- karty podarunkowe w dniu sprzedaży; reszta tak, jak leży w tabelach
WITH
pos_netto AS (
    SELECT lokal, nr_paragonu, sum(ilosc * cena_brutto / (1 + vat / 100.0)) AS netto
    FROM pos_pozycje GROUP BY ALL
),
zrodla AS (
    SELECT 1 AS lp, 'POS' AS zrodlo, count(*) AS wiersze, sum(n.netto) AS kwota
    FROM pos_paragony r JOIN pos_netto n USING (lokal, nr_paragonu)
    WHERE r.data_czas >= '2026-09-01' AND r.data_czas < '2026-10-01'
    UNION ALL
    -- zamówień e-commerce opis nie wymienia: biorę je tak, jak leżą (brutto, UTC, EUR bez przeliczenia)
    SELECT 2, 'E-commerce: zamówienia', count(*), sum(brutto)
    FROM ecom_zamowienia
    WHERE data_utc >= '2026-09-01' AND data_utc < '2026-10-01'
    UNION ALL
    -- plan roczny: całe 399 zł w miesiącu płatności (bez rozkładania na 12 miesięcy)
    SELECT 3, 'E-commerce: subskrypcje', count(*), sum(kwota)
    FROM ecom_subskrypcje
    WHERE data_platnosci >= '2026-09-01' AND data_platnosci < '2026-10-01'
    UNION ALL
    SELECT 4, 'Karty podarunkowe', count(*), sum(kwota)
    FROM karty_podarunkowe
    WHERE data_sprzedazy >= '2026-09-01' AND data_sprzedazy < '2026-10-01'
    UNION ALL
    SELECT 5, 'ERP', count(*), sum(kwota_netto)
    FROM erp_faktury
    WHERE data >= '2026-09-01' AND data < '2026-10-01'
)
SELECT lp, zrodlo, wiersze, round(kwota, 2) AS kwota FROM zrodla
UNION ALL
SELECT 6, 'RAZEM', sum(wiersze), round(sum(kwota), 2) FROM zrodla
ORDER BY lp;
```

### 3.4 Wpływ pojedynczych zmian interpretacji

Każdy wiersz zmienia **jedną** decyzję z 3.1. Wiersze się nie sumują.

| # | Zmiana (zamiast decyzji) | Wpływ [zł] | Wynik [zł] | mln |
|---:|---|---:|---:|---:|
| 1 | Bez zamówień e-commerce, czyli tylko źródła wymienione w opisie (K5) | −677 061,42 | 7 382 023,58 | 7,38 |
| 2 | Zamówienia e-commerce netto: brutto / 1,23 (K5) | −126 604,98 | 7 932 480,02 | 7,93 |
| 3 | Subskrypcje netto: kwota / 1,23 (K3) | −81 748,73 | 7 977 336,27 | 7,98 |
| 4 | Subskrypcje roczne rozłożone na 12 miesięcy, odwrotnie niż w opisie (K3) | −60 448,50 | 7 998 636,50 | 8,00 |
| 5 | Karty podarunkowe w dniu realizacji zamiast sprzedaży, odwrotnie niż w opisie (K4) | −24 600,00 | 8 034 485,00 | 8,03 |
| 6 | POS bez duplikatów z lokalu 17 (K2) | −29 998,74 | 8 029 086,26 | 8,03 |
| 7 | Zwroty e-commerce odjęte, czyli bez zamówień z `zwrot = true` (K5) | −87 827,45 | 7 971 257,55 | 7,97 |
| 8 | Bez zamówień testowych (K5) | −10 800,83 | 8 048 284,17 | 8,05 |
| 9 | Zamówienia w EUR przeliczone kursem NBP z poprzedniego dnia roboczego (K5) | +36 849,14 | 8 095 934,14 | 8,10 |
| 10 | E-commerce (zamówienia i subskrypcje) w czasie warszawskim (K6) | +11 714,81 | 8 070 799,81 | 8,07 |
| 11 | ERP bez korekt (K1) | +13 770,08 | 8 072 855,08 | 8,07 |
| 12 | POS netto jedną stawką 23% od kwoty paragonu (K2) | −231 174,91 | 7 827 910,09 | 7,83 |

```sql
-- Księgowość: wpływ pojedynczych zmian (każda osobno, względem wyniku dosłownego 8 059 085,00)
WITH
pos_netto AS (SELECT lokal, nr_paragonu, sum(ilosc * cena_brutto / (1 + vat / 100.0)) AS netto FROM pos_pozycje GROUP BY ALL),
pos_wrz AS (SELECT r.*, n.netto FROM pos_paragony r JOIN pos_netto n USING (lokal, nr_paragonu)
            WHERE r.data_czas >= '2026-09-01' AND r.data_czas < '2026-10-01'),
zam_wrz AS (SELECT * FROM ecom_zamowienia WHERE data_utc >= '2026-09-01' AND data_utc < '2026-10-01'),
sub_wrz AS (SELECT * FROM ecom_subskrypcje WHERE data_platnosci >= '2026-09-01' AND data_platnosci < '2026-10-01'),
w(lp, zmiana, wplyw) AS (
    SELECT 1, 'Bez zamówień e-commerce (tylko źródła wymienione w opisie)',
         - (SELECT sum(brutto) FROM zam_wrz)
    UNION ALL SELECT 2, 'Zamówienia e-commerce netto (brutto / 1,23)',
         - (SELECT sum(brutto) - sum(brutto / 1.23) FROM zam_wrz)
    UNION ALL SELECT 3, 'Subskrypcje netto (kwota / 1,23)',
         - (SELECT sum(kwota) - sum(kwota / 1.23) FROM sub_wrz)
    UNION ALL SELECT 4, 'Subskrypcje roczne rozłożone na 12 miesięcy (odwrotnie niż w opisie)',
         - (SELECT sum(kwota) FROM sub_wrz WHERE plan = 'roczny')
         + (SELECT count(*) * 399 / 12.0 FROM ecom_subskrypcje
            WHERE plan = 'roczny' AND data_platnosci >= '2025-10-01' AND data_platnosci < '2026-10-01')
    UNION ALL SELECT 5, 'Karty podarunkowe w dniu realizacji zamiast sprzedaży',
           (SELECT sum(kwota) FROM karty_podarunkowe WHERE data_realizacji >= '2026-09-01' AND data_realizacji < '2026-10-01')
         - (SELECT sum(kwota) FROM karty_podarunkowe WHERE data_sprzedazy  >= '2026-09-01' AND data_sprzedazy  < '2026-10-01')
    UNION ALL SELECT 6, 'POS bez duplikatów z lokalu 17',
         - (SELECT sum(netto) FROM pos_wrz WHERE plik LIKE '%(1)%')
    UNION ALL SELECT 7, 'Zwroty e-commerce odjęte (bez zamówień z zwrot = true)',
         - (SELECT sum(brutto) FROM zam_wrz WHERE zwrot)
    UNION ALL SELECT 8, 'Bez zamówień testowych',
         - (SELECT sum(brutto) FROM zam_wrz
            WHERE notatka ILIKE '%test%' OR notatka ILIKE '%nie realiz%' OR notatka ILIKE '%nie wysyłać%' OR email LIKE '%@kawosz.pl')
    UNION ALL SELECT 9, 'Zamówienia w EUR przeliczone kursem NBP z poprzedniego dnia roboczego',
           (SELECT sum(z.brutto * k.eur_pln - z.brutto)
            FROM zam_wrz z ASOF LEFT JOIN kursy_nbp k ON z.data_utc::DATE > k.data WHERE z.waluta = 'EUR')
    UNION ALL SELECT 10, 'E-commerce (zamówienia i subskrypcje) w czasie warszawskim',
           (SELECT sum(brutto) FROM ecom_zamowienia
            WHERE timezone('Europe/Warsaw', data_utc::TIMESTAMP AT TIME ZONE 'UTC') >= '2026-09-01'
              AND timezone('Europe/Warsaw', data_utc::TIMESTAMP AT TIME ZONE 'UTC') <  '2026-10-01')
         - (SELECT sum(brutto) FROM zam_wrz)
         + (SELECT sum(kwota) FROM ecom_subskrypcje
            WHERE timezone('Europe/Warsaw', data_platnosci AT TIME ZONE 'UTC') >= '2026-09-01'
              AND timezone('Europe/Warsaw', data_platnosci AT TIME ZONE 'UTC') <  '2026-10-01')
         - (SELECT sum(kwota) FROM sub_wrz)
    UNION ALL SELECT 11, 'ERP bez korekt',
         - (SELECT sum(kwota_netto) FROM erp_faktury WHERE data >= '2026-09-01' AND data < '2026-10-01' AND typ = 'korekta')
    UNION ALL SELECT 12, 'POS netto jedną stawką 23% od kwoty paragonu',
           (SELECT sum(kwota_brutto) / 1.23 FROM pos_wrz) - (SELECT sum(netto) FROM pos_wrz)
)
SELECT lp, zmiana, round(wplyw, 2) AS wplyw,
       round(8059085.00 + wplyw, 2) AS wynik, round((8059085.00 + wplyw) / 1e6, 2) AS wynik_mln
FROM w ORDER BY lp;
```

### 3.5 Co może tłumaczyć różnicę

- **Żadna pojedyncza zmiana nie daje 7,92.** Najbliżej jest wiersz 2, czyli zamówienia e-commerce w netto. Daje 7 932 480,02 zł, o ok. 7 500 zł powyżej górnej granicy zaokrąglenia do 7,92.
- **Opis księgowości jest niepełny i najpewniej brakuje w nim zasad dla e-commerce.** Z zamówieniami e-commerce „jak leżą” wychodzi za dużo (8,06), a bez nich za mało (7,38). Księgowość musi więc ujmować e-commerce jakoś inaczej. Pasuje to do wniosku z podsumowania: według opisów księgowość powinna być wyższa niż raport sprzedaży, a w rzeczywistości jest niższa.
- W stronę 7,92 przesuwają wynik, każdy osobno:
  - e-commerce netto: −126 605 zł;
  - odjęcie zwrotów e-commerce: −87 827 zł;
  - subskrypcje netto: −81 749 zł;
  - POS bez zdublowanych plików: −29 999 zł (księgowość, która księguje z raportów fiskalnych kas, nie miałaby tych duplikatów);
  - wyłączenie zamówień testowych: −10 801 zł.

  Kursu EUR (+36 849 zł) i czasu warszawskiego (+11 715 zł) księgowość zgodnie z przepisami raczej nie pomija, a działają one w przeciwną stronę.
- Rozłożenie subskrypcji rocznych dałoby −60 448,50 zł, ale opis mówi wprost, że księgowość tego nie robi. Wiersz 4 pokazuje tylko skalę tej zasady.
- Nie składam tych zmian w kombinację. Przy kilkunastu zmianach różnej wielkości łatwo ułożyć zestaw, który trafi w 7,92, i takie trafienie nie byłoby dowodem.

Pytania do księgowości:
1. Jak księgowane są zamówienia ze sklepu internetowego: netto czy brutto? Czy zwroty są odejmowane (korekty, data zwrotu)? Jakim kursem przeliczane jest EUR? Czy obowiązuje czas polski?
2. Czy sprzedaż POS jest księgowana z raportów fiskalnych kas, czyli bez zdublowanych plików z lokalu 17?
3. Czy subskrypcje są księgowane netto?
4. Czy zamówienia testowe są wyłączane?
