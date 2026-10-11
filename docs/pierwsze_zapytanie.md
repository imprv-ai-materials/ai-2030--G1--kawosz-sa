# Pierwsze zapytanie — inwentaryzacja danych i surowy przychód 09.2026

Źródło: `kawosz.duckdb` (25 tabel, otwarta w trybie `read_only`). Data eksportu danych: 2026-09-30.
Wszystkie liczby poniżej to **surowe** wartości z bazy, bez czyszczenia, deduplikacji, przeliczania walut ani stref czasowych.

## 1. Liczba wierszy i zakres dat w tabelach

Dla tabel z kilkoma kolumnami dat podano zakres każdej z nich. `—` oznacza, że tabela nie ma kolumny daty.

| Tabela | Wiersze | Kolumna daty | Od | Do |
|---|---:|---|---|---|
| agencja_features | 12 351 | data_migawki | 2024-04-01 | 2026-04-01 |
| ankiety_nps | 14 936 | data_wysylki | 2024-02-13 | 2026-08-11 |
| | | data_odpowiedzi | 2024-02-14 | 2026-08-25 |
| crm_biura | 1 917 | data_startu | 2012-04-10 | 2026-09-28 |
| | | data_konca_umowy | 2024-01-15 | 2027-09-29 |
| crm_kontakty_am | 15 362 | data | 2024-01-02 | 2026-09-30 |
| crm_opiekunowie | 6 | — | — | — |
| crm_umowy_historia | 6 244 | data_zdarzenia | 2012-04-10 | 2026-09-30 |
| ecom_pozycje | 518 082 | — | — | — |
| ecom_produkty | 57 | — | — | — |
| ecom_subskrypcje | 209 406 | data_platnosci | 2023-12-31 23:06:44 | 2026-09-30 00:45:52 |
| ecom_zamowienia | 220 896 | data_utc | 2023-12-31 23:00:15 | 2026-09-30 21:54:21 |
| erp_faktury | 47 333 | data | 2024-01-15 | 2026-09-30 |
| erp_kartoteka | 398 | — | — | — |
| erp_kontrahenci | 1 512 | — | — | — |
| erp_kontrahenci_archiwum | 517 | — | — | — |
| erp_platnosci | 44 712 | data_platnosci | 2024-02-05 | 2026-09-30 |
| erp_pozycje | 159 627 | — | — | — |
| helpdesk_zgloszenia | 23 945 | utworzono | 2024-01-01 08:13 | 2026-09-30 17:06 |
| | | rozwiazano | 2024-01-02 00:09 | 2026-09-30 13:16 |
| iot_ekspresy | 2 568 | data_instalacji | 2012-04-30 | **2026-11-24** |
| iot_telemetria | 1 863 414 | data | 2024-01-01 | 2026-09-30 |
| | | data_dostarczenia | 2024-01-03 | **2026-10-02** |
| karty_podarunkowe | 20 398 | data_sprzedazy | 2024-01-01 | 2026-09-30 |
| | | data_realizacji | 2024-01-10 | 2026-09-30 |
| kursy_nbp | 693 | data | 2024-01-02 | 2026-09-30 |
| lokale | 24 | data_otwarcia | 2012-01-01 | 2025-10-03 |
| pos_paragony | 2 100 602 | data_czas | 2024-01-02 07:00:16 | 2026-09-30 19:56:51 |
| pos_pozycje | 3 197 403 | — | — | — |
| pos_produkty | 47 | — | — | — |

Obserwacje (niepoprawiane):
- `iot_ekspresy.data_instalacji` sięga 2026-11-24, czyli jest późniejsza niż data eksportu.
- `iot_telemetria.data_dostarczenia` sięga 2026-10-02, czyli dane dotarły po dniu eksportu.
- `ecom_*` zaczynają się 2023-12-31 23:xx, bo zapis jest w UTC (w Warszawie to już 2024-01-01).

```sql
-- Wzorzec dla każdej tabeli i każdej kolumny daty (pełne zapytanie to UNION ALL takich bloków):
SELECT 'erp_faktury' AS tabela,
       (SELECT count(*) FROM erp_faktury) AS wiersze,
       'data' AS kolumna_daty,
       min(data)::varchar AS od,
       max(data)::varchar AS do_
FROM erp_faktury
UNION ALL
SELECT 'ankiety_nps', (SELECT count(*) FROM ankiety_nps), 'data_wysylki',
       min(data_wysylki)::varchar, max(data_wysylki)::varchar FROM ankiety_nps
UNION ALL
SELECT 'ankiety_nps', (SELECT count(*) FROM ankiety_nps), 'data_odpowiedzi',
       min(data_odpowiedzi)::varchar, max(data_odpowiedzi)::varchar FROM ankiety_nps
-- ... tak samo dla pozostałych tabel z datami
UNION ALL
SELECT 'crm_opiekunowie', (SELECT count(*) FROM crm_opiekunowie), NULL, NULL, NULL  -- tabele bez dat
ORDER BY 1, 3;
```

## 2. Czy pliki paragonów się powtarzają?

**Tak.** Tabela `pos_paragony` ma kolumnę `plik`, czyli nazwę dziennego pliku CSV z kasy (22 844 pliki). Trzy pliki z lokalu 17 występują podwójnie, jako kopie z dopiskiem ` (1)`:

| Oryginał | Kopia | Wiersze | Suma kwota_brutto |
|---|---|---:|---:|
| pos_paragony_17_2026-09-11.csv | pos_paragony_17_2026-09-11 (1).csv | 351 | 11 580,00 |
| pos_paragony_17_2026-09-12.csv | pos_paragony_17_2026-09-12 (1).csv | 299 | 9 882,00 |
| pos_paragony_17_2026-09-13.csv | pos_paragony_17_2026-09-13 (1).csv | 338 | 11 222,00 |

- Kopie są identyczne z oryginałami: suma MD5 plików w zipie jest ta sama, a liczba wierszy, suma, zakres numerów i zakres czasu też się zgadzają.
- Para (`lokal`, `nr_paragonu`) powtarza się w **988** przypadkach (351 + 299 + 338). Wszystkie pochodzą z tych trzech kopii. Poza nimi nie ma powtórzonych paragonów.
- Wszystkie kopie dotyczą **września 2026**, więc w surowej sumie POS za ten miesiąc jest podwojone **32 684,00 zł** (988 paragonów).
- Przy okazji: w części plików jest dodatkowa kolumna `kanal` (sala / wynos / aplikacja). W pozostałych 1 825 381 wierszach ma wartość NULL.

```sql
-- Pliki o identycznym "odcisku" (liczba wierszy, suma, zakres numerów i czasu)
WITH f AS (
  SELECT plik, count(*) n, sum(kwota_brutto) s,
         min(nr_paragonu) mn, max(nr_paragonu) mx,
         min(data_czas) t0, max(data_czas) t1
  FROM pos_paragony GROUP BY plik
)
SELECT a.plik, b.plik, a.n, a.s
FROM f a JOIN f b
  ON a.plik < b.plik AND a.n = b.n AND a.s = b.s
 AND a.mn = b.mn AND a.mx = b.mx AND a.t0 = b.t0 AND a.t1 = b.t1;

-- Powtórzone paragony (lokal + nr_paragonu): 988
SELECT count(*) FROM (
  SELECT lokal, nr_paragonu FROM pos_paragony
  GROUP BY ALL HAVING count(*) > 1
);

-- Czy są duplikaty spoza plików "(1)"? -> 0 wierszy
SELECT lokal, nr_paragonu, count(*), list(DISTINCT plik)
FROM pos_paragony
GROUP BY ALL
HAVING count(*) > 1 AND NOT bool_or(plik LIKE '%(1)%');

-- Wpływ kopii na wrzesień 2026: 988 wierszy, 32 684,00
SELECT count(*), sum(kwota_brutto) FROM pos_paragony
WHERE data_czas >= '2026-09-01' AND data_czas < '2026-10-01'
  AND plik LIKE '%(1)%';
```

## 3. Surowy przychód za wrzesień 2026, wszystkie źródła

Sumuję kolumnę kwoty w tabeli transakcyjnej każdego systemu, filtrując po jej natywnej kolumnie daty (`>= 2026-09-01 AND < 2026-10-01`). Niczego nie poprawiam.

| Źródło | Kolumna | Wiersze | Suma |
|---|---|---:|---:|
| POS: `pos_paragony` | kwota_brutto | 70 097 | 2 187 234,00 |
| E-commerce: `ecom_zamowienia` | brutto | 7 639 | 677 061,42 |
| E-commerce: `ecom_subskrypcje` | kwota | 8 302 | 437 178,00 |
| ERP: `erp_faktury` | kwota_netto | 1 445 | 4 858 331,65 |
| **Razem (surowo)** | | **87 483** | **8 159 805,07** |

```sql
SELECT 'POS – pos_paragony.kwota_brutto' AS zrodlo, count(*) n, sum(kwota_brutto)::double kwota
FROM pos_paragony
WHERE data_czas >= '2026-09-01' AND data_czas < '2026-10-01'
UNION ALL
SELECT 'E-com – ecom_zamowienia.brutto', count(*), sum(brutto)
FROM ecom_zamowienia
WHERE data_utc >= '2026-09-01' AND data_utc < '2026-10-01'
UNION ALL
SELECT 'E-com – ecom_subskrypcje.kwota', count(*), sum(kwota)
FROM ecom_subskrypcje
WHERE data_platnosci >= '2026-09-01' AND data_platnosci < '2026-10-01'
UNION ALL
SELECT 'ERP – erp_faktury.kwota_netto', count(*), sum(kwota_netto)
FROM erp_faktury
WHERE data >= '2026-09-01' AND data < '2026-10-01';
```

### Co jest w tej liczbie (zostawione bez poprawek)

Suma 8 159 805,07 **nie jest** jeszcze wiarygodnym przychodem. Składa się na nią kilka niespójności:

| Problem | Skala we wrześniu 2026 |
|---|---|
| Zduplikowane pliki paragonów (lokal 17, 11–13.09) | +32 684,00 (988 paragonów) |
| Storna POS liczone jako ujemne kwoty | 134 paragony, −4 330,00 |
| Mieszanie brutto (POS, e-com) z netto (ERP) | VAT na fakturach ERP: 1 117 416,30 |
| Zamówienia e-com w EUR zsumowane z PLN bez przeliczenia | 436 zamówień, 11 461,76 EUR |
| Zamówienia e-com ze zwrotem (`zwrot = true`) liczone jak sprzedaż | 1 005 zamówień, 87 827,45 |
| Daty e-com w UTC, a nie w Europe/Warsaw (przesunięte granice miesiąca) | nie liczone |
| Korekty ERP wliczone (ujemne) | 37 dokumentów, −13 770,08 netto |

Celowo **poza sumą**:
- `pos_pozycje`, `ecom_pozycje`, `erp_pozycje`: to szczegóły tych samych dokumentów, więc ich dodanie policzyłoby sprzedaż dwa razy. Dla porównania: `pos_pozycje` z numerami paragonów 2609xx daje 105 380 pozycji i `ilosc × cena_brutto` = 2 154 550,00, a nagłówki paragonów dają 2 187 234,00.
- `erp_platnosci`: to wpłaty za faktury, a nie osobna sprzedaż.
- `karty_podarunkowe`: sprzedaż kart we wrześniu to 562 szt. i 77 100 zł. To przedpłata (zobowiązanie), a nie przychód. Jeśli trzeba ją doliczyć, surowa suma wynosi 8 236 905,07.

```sql
-- Rozbicia użyte w tabeli problemów
SELECT storno, count(*), sum(kwota_brutto) FROM pos_paragony
WHERE data_czas >= '2026-09-01' AND data_czas < '2026-10-01' GROUP BY 1;

SELECT waluta, zwrot, count(*), sum(brutto) FROM ecom_zamowienia
WHERE data_utc >= '2026-09-01' AND data_utc < '2026-10-01' GROUP BY ALL ORDER BY ALL;

SELECT typ, count(*), sum(kwota_netto), sum(vat) FROM erp_faktury
WHERE data >= '2026-09-01' AND data < '2026-10-01' GROUP BY ALL;

SELECT plan, count(*), sum(kwota) FROM ecom_subskrypcje
WHERE data_platnosci >= '2026-09-01' AND data_platnosci < '2026-10-01' GROUP BY ALL;

SELECT count(*), sum(kwota) FROM karty_podarunkowe
WHERE data_sprzedazy >= '2026-09-01' AND data_sprzedazy < '2026-10-01';

SELECT count(*), sum(ilosc * cena_brutto) FROM pos_pozycje
WHERE nr_paragonu BETWEEN 2609010000 AND 2609309999;
```
