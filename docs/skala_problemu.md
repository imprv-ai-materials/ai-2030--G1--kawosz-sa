# Skala problemu: lista rzeczy do naprawy

Wszystkie znaleziska z [`profil_danych.md`](profil_danych.md) i [`trzy_przychody.md`](trzy_przychody.md) zebrane w jednej tabeli: co znaleźliśmy, ile rekordów i ile to kosztuje w PLN miesięcznie. Źródło to `kawosz.duckdb` (otwarta `read_only`), dane do 30.09.2026. SQL jest na końcu dokumentu.

## Jak czytać tabelę

- **PLN we wrześniu 2026:** kwota, której problem dotyczy w miesiącu, w którym trzy raporty się rozjeżdżają. Liczona po natywnej kolumnie daty każdej tabeli.
- **PLN średnio na miesiąc:** średnia z 33 miesięcy (I.2024–IX.2026). Pokazuje, czy wrzesień jest typowy, i wycenia problemy jednorazowe z innych miesięcy.
- **Znak kwoty:**
  - `+` problem zawyża przychód;
  - `−` problem zaniża przychód;
  - kwota bez znaku to pieniądze, których problem dotyczy (np. źle przypisane do kategorii lub klienta) przy poprawnej sumie przychodu.
- **Kwoty są takie, jak leżą w tabelach:** POS i e-commerce brutto, ERP netto. W wierszach e-commerce część kwot jest w EUR, dodanych bez przeliczenia (zaznaczone).
- **Kolejność:**
  1. problemy, które występują we wrześniu, od najdroższego;
  2. problemy jednorazowe z innych miesięcy, według średniej;
  3. ryzyka, czyli kwoty potencjalne przy błędnym złączeniu lub nieuwadze;
  4. rzeczy bez wyceny.
- **Wierszy nie należy sumować.** Część się nakłada, np. zwroty e-commerce zawierają VAT, a VAT jest osobnym wierszem.

## Najważniejsze

- **Najdroższe, a przy tym najprostsze do naprawy: brak kategorii w kartotece ERP.** Dotyczy 1,73 mln zł netto we wrześniu, czyli 38% ERP. Wystarczy uzupełnić kategorię przy 24 indeksach.
- **Sumę przychodu za wrzesień najbardziej zmieniają:**
  - VAT wliczony w BI: +386 tys. zł;
  - definicje raportów, których nie da się odtworzyć: do 209 tys. zł;
  - zwroty e-commerce: +88 tys. zł;
  - sprzedaż kart podarunkowych: +77 tys. zł;
  - plan roczny subskrypcji: +60 tys. zł;
  - nieprzeliczone EUR: −37 tys. zł;
  - zdublowane pliki POS: +33 tys. zł.
- **Trzy pozycje są we wrześniu wyraźnie droższe niż zwykle, więc wrzesień nie jest typowym miesiącem:**
  - **zdublowane pliki POS:** tylko we wrześniu;
  - **plan roczny:** wrzesień to szczyt płatności rocznych (315 wobec typowych 120–170);
  - **UTC:** zwykle przesunięcie się znosi (ok. 12 tys. zł wchodzi na początku miesiąca i tyle samo wychodzi na końcu), a we wrześniu nic nie wychodzi, bo eksport kończy się o północy czasu polskiego.

## Tabela

| # | Znalezisko | Rekordy (IX 2026) | PLN we wrześniu 2026 | PLN średnio / mies. | Na co wpływa | Co naprawić |
|---:|---|---:|---:|---:|---|---|
| 1 | **Indeksy ERP bez kategorii**: 24 z 398, m.in. abonamenty Plan M i XL ([profil §6](profil_danych.md#6-erp)) | 789 pozycji | 1 729 040,13 | 1 691 979,99 | przychód według kategorii: 38% netto ERP bez kategorii | uzupełnić `kategoria` dla 24 indeksów |
| 2 | **Kontrahenci bez ID z CRM**: 196 aktywnych i 38 z archiwum (§6) | 148 faktur | 536 441,73 | 445 306,09 | przychód według klienta: faktur nie da się powiązać z CRM (opiekun, NPS, plan) | uzupełnić `id_biura_crm` |
| 3 | **BI sumuje brutto (POS, e-commerce) z netto (ERP)** ([trzy przychody](trzy_przychody.md)) | 86 038 wierszy | +386 173,78 | +328 101,21 | suma przychodu: BI zawyżony o VAT względem raportów netto | jedna definicja przychodu na jednej podstawie (netto) |
| 4 | **Zdublowani kontrahenci**: 112 rekordów 26xxxx, w tym 7 z uciętym NIP-em (§6, §10) | 58 dokumentów | 224 529,31 | 96 276,53 | przychód według klienta: historia rozbita na dwa rekordy | scalić według mapy z §10.6, poprawić 7 NIP-ów |
| 5 | **Raporty niezgodne ze swoimi opisami z audytu**: liczba z raportu minus wynik dosłowny, z dokładnością ±5 tys. zł ([trzy przychody](trzy_przychody.md)) | — | BI +73 094,93; sprzedaż +209 268,71; księgowość −139 085,00 | — | suma przychodu: nie wiadomo, skąd biorą się różnice | spisać definicje i SQL trzech raportów |
| 6 | **Zdublowane nazwy produktów w sklepie**: 4 nazwy, każda z 2 SKU w różnych cenach (§4) | 2 960 pozycji | 156 427,52 (PLN+EUR) | 139 702,37 | przychód według produktu | rozróżnić nazwy albo scalić SKU |
| 7 | **Zwroty e-commerce bez daty i kwoty, nieodejmowane** (§4) | 1 005 zamówień | +87 827,45 (PLN+EUR) | +78 921,34 | suma przychodu: zawyżona we wszystkich trzech raportach, o ile zwroty są pełne | dodać datę i kwotę zwrotu, odejmować w miesiącu zwrotu |
| 8 | **Sprzedaż kart podarunkowych liczona jako przychód** (§5) | 562 karty | +77 100,00 | +82 416,67 | suma przychodu: to przedpłata, a nie sprzedaż | ująć jako zobowiązanie, przychód przy realizacji |
| 9 | **Zamówienia bez e-maila**, w 93% za pobraniem (§4) | 757 zamówień | 69 031,87 (PLN+EUR) | 59 897,51 | analizy klientów: brak identyfikatora | wymagać identyfikatora klienta także przy pobraniu |
| 10 | **Płatności z flagą `spor` o nieznanym znaczeniu**, opłacone w całości (§6) | 19 płatności | 63 787,75 | 71 986,96 | należności i spory: nie wiadomo, co flaga oznacza | ustalić znaczenie flagi z działem finansów |
| 11 | **Plan roczny subskrypcji w całości w miesiącu płatności** (§4) | 315 płatności | +60 448,50 | +5 145,83 (I.2025–IX.2026) | suma przychodu: zawyża miesiące szczytu (IX, XII), zaniża pozostałe | rozliczać 1/12 miesięcznie |
| 12 | **VAT 23% na mleko UHT**, które zwykle ma 5% (do weryfikacji, §6) | 991 pozycji | 37 116,66 (różnica VAT) | 32 192,77 | VAT (netto bez zmian): możliwie zawyżony podatek na fakturach | sprawdzić stawki VAT w kartotece z księgowością |
| 13 | **Zamówienia w EUR sumowane z PLN bez przeliczenia** (§4) | 436 zamówień | −36 859,69 | −35 102,90 | suma przychodu: zaniżona (euro liczone jak złote) | przeliczać kursem NBP (w księgowości z dnia poprzedzającego) |
| 14 | **NIP-y bez 10 cyfr**: 15 kontrahentów, w tym 7 duplikatów (§6, §10) | 13 faktur | 36 148,78 | 29 103,70 | faktury z błędnym NIP-em: ryzyko podatkowe | poprawić NIP-y, walidować sumę kontrolną przy wprowadzaniu |
| 15 | **Zdublowane pliki paragonów** z lokalu 17, 11–13.09 (§3) | 988 paragonów | +32 684,00 | +990,42 | suma przychodu: zawyżona | odrzucać pliki „(1)” przy ładowaniu, kontrolować unikalność klucza (lokal, numer) |
| 16 | **Korekty ERP bez wskazania faktury pierwotnej i bez zapisu zwrotu pieniędzy** (§6) | 37 korekt | 13 770,08 | 19 327,92 | śledzenie korekt i zwrotów (suma poprawna) | dodać numer faktury korygowanej i zapis zwrotu w płatnościach |
| 17 | **Miesiąc e-commerce liczony w UTC zamiast czasu polskiego** (zamówienia i subskrypcje, §4) | 50 zamówień + 172 obciążenia | −11 714,81 (PLN+EUR) | 1 690,12 (na każdej granicy przesuwa się ok. 12 tys. zł) | suma przychodu: zaniżona we wrześniu | filtrować po czasie Europe/Warsaw |
| 18 | **Zamówienia testowe w sprzedaży** (§4) | 73 zamówienia | +10 800,83 (PLN+EUR) | +1 949,81 | suma przychodu: zawyżona | flaga testowa, wykluczanie adresów `@kawosz.pl` |
| 19 | **Storna POS bez powiązania z paragonem pierwotnym** (§3) | 134 paragony | 4 330,00 | 3 923,52 | liczba transakcji zawyżona o storna i paragony stornowane (suma poprawna) | zapisywać numer paragonu stornowanego |
| 20 | **Zdublowane nazwy w kartotece ERP**: 22 nazwy pod 2 indeksami (§6) | 3 pozycje | 401,35 | 666,48 | przychód według produktu i kategorii | scalić indeksy |
| 21 | **Paragony bez metody płatności** (§3) | 14 paragonów | 376,00 | 262,27 | raporty według metody płatności | wymusić metodę w kasie |
| 22 | **Zwroty POS bez flagi storno**: pozycja ujemna w paragonie (§3) | 2 paragony | 88,00 | 494,21 | zwrotów nie da się wyróżnić (suma poprawna) | osobny typ dokumentu dla zwrotu |
| 23 | **Faktura na 330 885,20 zł** (40 ekspresów), do weryfikacji (§9) | — | — | 10 026,82 (XI.2025: 330 885,20) | suma przychodu XI.2025, jeśli sprzedaż się nie odbyła | potwierdzić umowę i instalacje, pokazywać osobno od przychodu powtarzalnego |
| 24 | **Paragon na 48 000 zł**: błąd ręcznej ceny `P0999` (§9) | — | — | +1 454,55 (III.2025: +48 000,00) | suma przychodu III.2025: zawyżona | skorygować, ograniczyć ręczną cenę `P0999` |
| 25 | *Ryzyko:* suma kwoty nagłówka po złączeniu z pozycjami (§10.4–10.5) | — | potencjalnie +13 424 754,84 (ERP), +1 720 481,00 (POS), +1 021 663,39 (e-com) | — | suma przychodu, jeśli raport tak policzy | sumować pozycje albo agregować przed złączeniem; test sum w potoku |
| 26 | *Ryzyko:* INNER JOIN faktur z płatnościami (§10.5) | — | potencjalnie −4 853 218,42 | — | suma przychodu: zostają tylko opłacone faktury | LEFT JOIN |
| 27 | *Ryzyko:* łączenie faktur po NIP-ie bez scalenia duplikatów (§10.5) | — | potencjalnie +400 049,68 | — | suma przychodu: 108 faktur policzonych dwa razy | najpierw scalić kontrahentów (wiersz 4) |
| 28 | *Do weryfikacji:* lokal 17 ma 4× więcej paragonów niż średnia lokali (§3) | 10 597 paragonów | narażone 332 704,00 | — | suma przychodu, jeśli ruch nie jest prawdziwy | potwierdzić z rozliczeniami terminali i danymi kasy |
| 29 | *Ryzyko:* faktury przeterminowane bez płatności, stan na 30.09.2026, brutto (§6) | 46 faktur | 172 040,83 | — | należności (przychód poprawny) | windykacja |
| 30 | *Ryzyko:* INNER JOIN pozycji sklepu z `ecom_produkty` (§10.5) | — | potencjalnie −98 284,84 | — | suma przychodu: znika wiersz `DOSTAWA` | LEFT JOIN |
| 31 | *Ryzyko:* realizacja karty podarunkowej niewidoczna w transakcjach (§5) | 396 realizacji | potencjalnie +52 500,00 | potencjalnie +56 703,03 | suma przychodu: ta sama karta przy sprzedaży i drugi raz przy realizacji (np. w POS jako „karta”) | metoda płatności „karta podarunkowa” w POS i e-commerce |
| 32 | *Ryzyko:* złączenie faktur tylko z aktywnymi kontrahentami (§10.5) | — | potencjalnie −10 928,98 | — | suma przychodu: znikają faktury kontrahentów z archiwum | łączyć z aktywnymi i archiwum razem |
| 33 | *Ryzyko:* brak kursu NBP dla 31.12.2023–2.01.2024 (§10.4) | — | 0 | — | do 15 zamówień w EUR bez kursu | uzupełnić kursy z końca 2023 |
| 34 | `pos_pozycje` nie ma klucza wiersza (§10.1) | — | — | — | pozycje można tylko agregować | dodać numer pozycji |
| 35 | Subskrypcje bez powiązania z klientem i bez rezygnacji (§4) | — | — | — | analizy odejść klientów są niemożliwe | dodać e-mail lub ID klienta oraz status |
| 36 | Cenniki bez historii, ceny w EUR ≈ cena PLN / 4 zamiast kursu (§3, §4) | — | — | — | analizy cen i przeliczeń walut | wersjonować cenniki, ustalić politykę cen w EUR |

**Pominięte, bo to nie są błędy:**
- puste pole `kanal` przed 1.06.2026 (zmiana formatu pliku z kasy);
- 8 dni bez paragonów (święta);
- faktury ERP wystawiane zbiorczo na koniec miesiąca i sezonowość kawy dla biur, która tłumaczy wzrost ERP z sierpnia na wrzesień;
- paragony i faktury oznaczone przez regułę IQR (5% i 6%) oraz top faktury #2–#10: to zwykła sprzedaż (§9).

## SQL

Miesięczne serie znalezisk z wierszy 1–24 (wrzesień i średnia za 33 miesiące):

```sql
-- Miesięczne serie znalezisk (I.2024–IX.2026), każda: miesiąc, rekordy, kwota
CREATE OR REPLACE TEMP TABLE mies AS SELECT unnest(generate_series(DATE '2024-01-01', DATE '2026-09-01', INTERVAL 1 MONTH))::DATE AS m;
CREATE OR REPLACE TEMP TABLE pos_netto AS SELECT lokal, nr_paragonu, sum(ilosc * cena_brutto / (1 + vat / 100.0)) AS netto FROM pos_pozycje GROUP BY ALL;
CREATE OR REPLACE TEMP TABLE zw AS SELECT *, timezone('Europe/Warsaw', data_utc::TIMESTAMP AT TIME ZONE 'UTC') AS t_waw FROM ecom_zamowienia;
CREATE OR REPLACE TEMP TABLE sw AS SELECT *, timezone('Europe/Warsaw', data_platnosci AT TIME ZONE 'UTC') AS t_waw FROM ecom_subskrypcje;

CREATE OR REPLACE TEMP TABLE seria AS
-- VAT wliczony w BI (POS + zamówienia + subskrypcje)
SELECT 'vat' AS k, date_trunc('month', r.data_czas)::DATE AS m, count(*) AS n, sum(r.kwota_brutto - n.netto) AS kwota
FROM pos_paragony r JOIN pos_netto n USING (lokal, nr_paragonu) GROUP BY ALL
UNION ALL SELECT 'vat', date_trunc('month', data_utc)::DATE, count(*), sum(brutto - brutto / 1.23) FROM ecom_zamowienia GROUP BY ALL
UNION ALL SELECT 'vat', date_trunc('month', data_platnosci)::DATE, count(*), sum(kwota - kwota / 1.23) FROM ecom_subskrypcje GROUP BY ALL
-- karty podarunkowe liczone jako przychód w dniu sprzedaży
UNION ALL SELECT 'karty_sprzedaz', date_trunc('month', data_sprzedazy)::DATE, count(*), sum(kwota) FROM karty_podarunkowe GROUP BY ALL
UNION ALL SELECT 'karty_realizacja', date_trunc('month', data_realizacji)::DATE, count(*), sum(kwota) FROM karty_podarunkowe WHERE data_realizacji IS NOT NULL GROUP BY ALL
-- zwroty e-commerce nieodejmowane
UNION ALL SELECT 'zwroty_ecom', date_trunc('month', data_utc)::DATE, count(*), sum(brutto) FROM ecom_zamowienia WHERE zwrot GROUP BY ALL
-- EUR bez przeliczenia (niedoszacowanie przy kursie NBP z dnia)
UNION ALL SELECT 'eur', date_trunc('month', z.data_utc)::DATE, count(*), sum(z.brutto * k.eur_pln - z.brutto)
FROM ecom_zamowienia z ASOF LEFT JOIN kursy_nbp k ON z.data_utc::DATE >= k.data WHERE z.waluta = 'EUR' GROUP BY ALL
-- zduplikowane pliki POS
UNION ALL SELECT 'pos_duplikaty', date_trunc('month', data_czas)::DATE, count(*), sum(kwota_brutto) FROM pos_paragony WHERE plik LIKE '%(1)%' GROUP BY ALL
-- zamówienia testowe
UNION ALL SELECT 'testowe', date_trunc('month', data_utc)::DATE, count(*), sum(brutto) FROM ecom_zamowienia
WHERE notatka ILIKE '%test%' OR notatka ILIKE '%nie realiz%' OR notatka ILIKE '%nie wysyłać%' OR email LIKE '%@kawosz.pl' GROUP BY ALL
-- korekty ERP (bez powiązania z fakturą i bez zwrotu pieniędzy)
UNION ALL SELECT 'korekty', date_trunc('month', data)::DATE, count(*), sum(kwota_netto) FROM erp_faktury WHERE typ = 'korekta' GROUP BY ALL
-- storna POS (bez powiązania z paragonem pierwotnym)
UNION ALL SELECT 'storno', date_trunc('month', data_czas)::DATE, count(*), sum(kwota_brutto) FROM pos_paragony WHERE storno = 1 GROUP BY ALL
-- zwroty POS bez flagi storno
UNION ALL SELECT 'pos_zwroty', date_trunc('month', data_czas)::DATE, count(*), sum(kwota_brutto) FROM pos_paragony WHERE kwota_brutto < 0 AND storno = 0 GROUP BY ALL
-- brak metody płatności
UNION ALL SELECT 'pos_bez_metody', date_trunc('month', data_czas)::DATE, count(*), sum(kwota_brutto) FROM pos_paragony WHERE metoda_platnosci IS NULL GROUP BY ALL
-- faktury na zdublowanych kontrahentach 26xxxx
UNION ALL SELECT 'kontrahenci_26', date_trunc('month', data)::DATE, count(*), sum(kwota_netto) FROM erp_faktury WHERE id_kontrahenta >= 260000 GROUP BY ALL
-- paragon 48 000 i faktura 330 885,20
UNION ALL SELECT 'paragon_48000', date_trunc('month', data_czas)::DATE, count(*), sum(kwota_brutto) FROM pos_paragony WHERE lokal = 5 AND nr_paragonu = 2503140076 GROUP BY ALL
UNION ALL SELECT 'faktura_330k', date_trunc('month', data)::DATE, count(*), sum(kwota_netto) FROM erp_faktury WHERE nr_faktury = 'FV/2025/11/00007' GROUP BY ALL
-- netto ERP na indeksach bez kategorii
UNION ALL SELECT 'kategorie_null', date_trunc('month', f.data)::DATE, count(*), sum(p.ilosc * p.cena)
FROM erp_pozycje p JOIN erp_faktury f USING (nr_faktury) JOIN erp_kartoteka k USING (indeks) WHERE k.kategoria IS NULL GROUP BY ALL
-- faktury do kontrahentów bez id_biura_crm (aktywni i archiwum)
UNION ALL SELECT 'crm_null', date_trunc('month', data)::DATE, count(*), sum(kwota_netto) FROM erp_faktury
WHERE id_kontrahenta IN (SELECT id_kontrahenta FROM erp_kontrahenci WHERE id_biura_crm IS NULL
                         UNION ALL SELECT id_kontrahenta FROM erp_kontrahenci_archiwum WHERE id_biura_crm IS NULL) GROUP BY ALL
-- faktury do kontrahentów z NIP-em, który nie ma 10 cyfr
UNION ALL SELECT 'nip_bledny', date_trunc('month', data)::DATE, count(*), sum(kwota_netto) FROM erp_faktury
WHERE id_kontrahenta IN (SELECT id_kontrahenta FROM erp_kontrahenci WHERE length(regexp_replace(nip, '[^0-9]', '', 'g')) <> 10) GROUP BY ALL
-- mleko UHT z VAT 23% zamiast 5%: różnica podatku = 18% netto
UNION ALL SELECT 'mleko_vat', date_trunc('month', f.data)::DATE, count(*), sum(p.ilosc * p.cena) * 0.18
FROM erp_pozycje p JOIN erp_faktury f USING (nr_faktury) WHERE p.indeks = '20.01.0001' GROUP BY ALL
-- płatności z flagą spor
UNION ALL SELECT 'spor', date_trunc('month', data_platnosci)::DATE, count(*), sum(kwota) FROM erp_platnosci WHERE spor GROUP BY ALL
-- zamówienia e-commerce bez e-maila
UNION ALL SELECT 'email_null', date_trunc('month', data_utc)::DATE, count(*), sum(brutto) FROM ecom_zamowienia WHERE email IS NULL GROUP BY ALL
-- sprzedaż SKU, których nazwa powtarza się w ecom_produkty
UNION ALL SELECT 'ecom_dup_nazwy', date_trunc('month', z.data_utc)::DATE, count(*), sum(p.ilosc * p.cena_brutto)
FROM ecom_pozycje p JOIN ecom_zamowienia z ON z.id = p.id_zamowienia
WHERE p.sku IN (SELECT sku FROM ecom_produkty WHERE nazwa IN (SELECT nazwa FROM ecom_produkty GROUP BY 1 HAVING count(*) > 1)) GROUP BY ALL
-- sprzedaż indeksów, których nazwa powtarza się w erp_kartoteka
UNION ALL SELECT 'kartoteka_dup_nazwy', date_trunc('month', f.data)::DATE, count(*), sum(p.ilosc * p.cena)
FROM erp_pozycje p JOIN erp_faktury f USING (nr_faktury)
WHERE p.indeks IN (SELECT indeks FROM erp_kartoteka WHERE nazwa IN (SELECT nazwa FROM erp_kartoteka GROUP BY 1 HAVING count(*) > 1)) GROUP BY ALL
-- przesunięcie granicy miesiąca UTC -> Warszawa (zamówienia + subskrypcje): miesiąc wg Warszawy minus wg UTC
UNION ALL SELECT 'utc', m, NULL, 0 FROM mies
UNION ALL SELECT 'utc', date_trunc('month', t_waw)::DATE, count(*), sum(brutto) FROM zw GROUP BY ALL
UNION ALL SELECT 'utc', date_trunc('month', data_utc)::DATE, -count(*), -sum(brutto) FROM zw GROUP BY ALL
UNION ALL SELECT 'utc', date_trunc('month', t_waw)::DATE, count(*), sum(kwota) FROM sw GROUP BY ALL
UNION ALL SELECT 'utc', date_trunc('month', data_platnosci)::DATE, -count(*), -sum(kwota) FROM sw GROUP BY ALL
-- plan roczny w całości zamiast 1/12 przez 12 miesięcy: gotówka w miesiącu minus część przypadająca na miesiąc
UNION ALL SELECT 'roczne', date_trunc('month', data_platnosci)::DATE, count(*), sum(kwota) FROM ecom_subskrypcje WHERE plan = 'roczny' GROUP BY ALL
UNION ALL SELECT 'roczne', mi.m, NULL, -count(*) * 399 / 12.0
FROM mies mi JOIN ecom_subskrypcje s ON s.plan = 'roczny'
 AND date_trunc('month', s.data_platnosci) > mi.m - INTERVAL 12 MONTH AND date_trunc('month', s.data_platnosci) <= mi.m GROUP BY ALL;

-- Wrzesień 2026 i średnia miesięczna (33 miesiące, dla „utc” średnia z wartości bezwzględnych,
-- dla „roczne” tylko miesiące z pełną 12-miesięczną historią: I.2025–IX.2026)
WITH m AS (SELECT k, m, sum(n) AS n, sum(kwota) AS kwota FROM seria WHERE m BETWEEN '2024-01-01' AND '2026-09-01' GROUP BY ALL)
SELECT k,
       sum(n) FILTER (WHERE m = '2026-09-01') AS rekordy_wrz,
       round(sum(kwota) FILTER (WHERE m = '2026-09-01'), 2) AS kwota_wrz,
       round(CASE k WHEN 'utc' THEN sum(abs(kwota)) / 33
                    WHEN 'roczne' THEN sum(kwota) FILTER (WHERE m >= '2025-01-01') / 21
                    ELSE sum(kwota) / 33 END, 2) AS srednio_mies,
       sum(n) AS rekordy_calosc
FROM m GROUP BY k ORDER BY abs(kwota_wrz) DESC NULLS LAST;
```

Ryzyka i stany z wierszy 25–32 (wrzesień 2026):

```sql
-- Ryzyka (wrzesień 2026): o ile zmieniłaby się suma, gdyby raport użył danego złączenia lub założenia
WITH
pos_wrz AS (SELECT * FROM pos_paragony WHERE data_czas >= '2026-09-01' AND data_czas < '2026-10-01'),
zam_wrz AS (SELECT * FROM ecom_zamowienia WHERE data_utc >= '2026-09-01' AND data_utc < '2026-10-01'),
fv_wrz AS (SELECT * FROM erp_faktury WHERE data >= '2026-09-01' AND data < '2026-10-01'),
kontr AS (SELECT id_kontrahenta, regexp_replace(nip, '[^0-9]', '', 'g') AS n10 FROM erp_kontrahenci
          UNION ALL SELECT id_kontrahenta, regexp_replace(nip, '[^0-9]', '', 'g') FROM erp_kontrahenci_archiwum)
SELECT 'POS: suma nagłówka po złączeniu z pozycjami' AS ryzyko, count(*) AS wiersze, sum(r.kwota_brutto) - (SELECT sum(kwota_brutto) FROM pos_wrz) AS zmiana
FROM pos_wrz r JOIN pos_pozycje USING (lokal, nr_paragonu)
UNION ALL SELECT 'E-commerce: suma nagłówka po złączeniu z pozycjami', count(*), sum(z.brutto) - (SELECT sum(brutto) FROM zam_wrz)
FROM zam_wrz z JOIN ecom_pozycje p ON p.id_zamowienia = z.id
UNION ALL SELECT 'ERP: suma nagłówka po złączeniu z pozycjami', count(*), sum(f.kwota_netto) - (SELECT sum(kwota_netto) FROM fv_wrz)
FROM fv_wrz f JOIN erp_pozycje USING (nr_faktury)
UNION ALL SELECT 'ERP: INNER JOIN z płatnościami', count(*), sum(f.kwota_netto) - (SELECT sum(kwota_netto) FROM fv_wrz)
FROM fv_wrz f JOIN erp_platnosci USING (nr_faktury)
UNION ALL SELECT 'ERP: łączenie po NIP-ie bez scalenia duplikatów', count(*), sum(f.kwota_netto) - (SELECT sum(kwota_netto) FROM fv_wrz)
FROM fv_wrz f JOIN kontr a USING (id_kontrahenta) JOIN kontr b USING (n10)
UNION ALL SELECT 'E-commerce: INNER JOIN z ecom_produkty', count(*),
       sum(p.ilosc * p.cena_brutto) - (SELECT sum(p2.ilosc * p2.cena_brutto) FROM zam_wrz z2 JOIN ecom_pozycje p2 ON p2.id_zamowienia = z2.id)
FROM zam_wrz z JOIN ecom_pozycje p ON p.id_zamowienia = z.id JOIN ecom_produkty USING (sku)
UNION ALL SELECT 'ERP: złączenie tylko z aktywnymi kontrahentami', count(*), sum(f.kwota_netto) - (SELECT sum(kwota_netto) FROM fv_wrz)
FROM fv_wrz f JOIN erp_kontrahenci USING (id_kontrahenta)
UNION ALL SELECT 'Karty: realizacja liczona drugi raz (np. w POS jako „karta”)', count(*), sum(kwota)
FROM karty_podarunkowe WHERE data_realizacji >= '2026-09-01' AND data_realizacji < '2026-10-01'
UNION ALL SELECT 'Lokal 17: sprzedaż we wrześniu (ruch 4× wyższy, niezweryfikowany)', count(*), sum(kwota_brutto)
FROM pos_wrz WHERE lokal = 17
UNION ALL SELECT 'ERP: faktury przeterminowane bez płatności (stan na 30.09.2026, brutto)', count(*), sum(f.kwota_netto + f.vat)
FROM erp_faktury f ANTI JOIN erp_platnosci p USING (nr_faktury) WHERE f.typ = 'faktura' AND f.data < '2026-09-01';
```

Wiersz 5 pochodzi z `docs/trzy_przychody.md`: liczby z raportów (8,31 / 8,06 / 7,92 mln) minus wyniki dosłowne (8 236 905,07 / 7 850 731,29 / 8 059 085,00 zł).
