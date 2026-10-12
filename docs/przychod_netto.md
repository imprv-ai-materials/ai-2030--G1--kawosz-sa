# Przychód netto: definicja

Jedna definicja przychodu netto Kawosz S.A. dla wszystkich źródeł: POS, sklep internetowy (zamówienia i subskrypcje), karty podarunkowe i ERP. Definicja to dziewięć reguł, każda zapisana w kodzie jako osobny krok i sprawdzona na ręcznie policzonym przypadku. Most od surowej sumy z dashboardu BI do tej definicji, za wrzesień i sierpień 2026, jest w [`most_2026-09.md`](most_2026-09.md).

- **Kod:** [`api/api/contexts_boundaries/revenue_bc/przychod/definicja.py`](../api/api/contexts_boundaries/revenue_bc/przychod/definicja.py). Lista `KROKI` zawiera reguły w kolejności z tego dokumentu, a `przychod_netto(con, miesiac)` zwraca przychód netto miesiąca według źródeł.
- **Testy:** [`api/tests/contexts_boundaries/revenue_bc/test_definicja.py`](../api/tests/contexts_boundaries/revenue_bc/test_definicja.py). Każda reguła ma test na przypadku z sekcji 3, a przypadki są w `conftest.py`. Uruchomienie: `poetry run pytest api/tests/contexts_boundaries`.
- **Dane:** `kawosz.duckdb`, eksport z 30.09.2026.

## 1. Definicja w skrócie

**Przychód netto miesiąca** to suma kwot netto w PLN ze wszystkich źródeł, ujętych w tym miesiącu według czasu polskiego. Każdy dokument źródłowy liczy się raz. Kwoty przechodzą przez dziewięć reguł:

| # | Reguła | Czego dotyczy | Co robi |
|---:|---|---|---|
| 1 | POS netto według stawek VAT z pozycji | paragony | netto paragonu = Σ `ilosc × cena_brutto / (1 + vat/100)` z jego pozycji |
| 2 | E-commerce, karty i subskrypcje netto 23% | zamówienia, subskrypcje, karty | netto = brutto / 1,23 |
| 3 | Po odjęciu korekt ERP i zwrotów e-commerce | korekty ERP, zamówienia ze zwrotem | korekta ERP odejmuje się kwotą ujemną; zamówienie ze zwrotem nie daje przychodu |
| 4 | ERP po mapowaniu kontrahentów | faktury i korekty ERP | dokument trafia na rekord główny kontrahenta z `mapa_kontrahentow` |
| 5 | Subskrypcje roczne rozłożone na 12 miesięcy | obciążenia planu rocznego | 1/12 kwoty w miesiącu płatności i w każdym z 11 kolejnych |
| 6 | Karty w dniu realizacji | karty podarunkowe | przychód w dniu realizacji; karta niezrealizowana nie jest przychodem |
| 7 | EUR po kursie z `kursy_nbp` z dnia sprzedaży | zamówienia w EUR | kwota × kurs z dnia sprzedaży; bez notowania tego dnia: ostatni wcześniejszy kurs |
| 8 | Bez zamówień testowych | zamówienia | notatka testowa albo e-mail `@kawosz.pl` (sekcja 4) |
| 9 | Doba według czasu polskiego | zamówienia, subskrypcje | czas UTC przeliczony na Europe/Warsaw, zanim wybierzemy dzień i miesiąc |

Kwoty netto ERP zostają bez zmian, a POS, ERP i karty mają już daty lokalne.

## 2. Jak to działa w kodzie

- **Linia przychodu** to jeden dokument: paragon, zamówienie, obciążenie subskrypcji, karta, faktura albo korekta ERP. Ma kwotę, walutę i czas ujęcia.
- **Linie startowe są takie, jak sumuje je dashboard BI:** kwota i data leżą jak w tabelach, e-commerce jest w UTC, a EUR liczy się jak PLN (definicja BI: [`trzy_przychody.md`](trzy_przychody.md), sekcja 1). Bez żadnej reguły linie dają dokładnie surową sumę BI. We wrześniu 2026 to 8 236 905,07 zł.
- **Każda reguła to funkcja,** która dostaje SQL linii po poprzednim kroku i zwraca SQL linii po swoim (`pos_netto`, `vat_23`, …, `czas_polski`). Kroki można więc włączać po kolei, i tak liczy się most.
- **Dwie rzeczy liczymy dopiero przy sumowaniu**, żeby wynik po wszystkich krokach nie zależał od ich kolejności:
  - kurs EUR z dnia ujęcia, bo czas polski może przesunąć ten dzień (zamówienie z niedzieli 22:30 UTC to w Warszawie poniedziałek);
  - miesiąc planu rocznego, bo czas polski może przesunąć miesiąc płatności (płatność z 30.09 22:40 UTC to w Warszawie 1.10).

  Test `test_wynik_nie_zalezy_od_kolejnosci_regul` liczy definicję z regułami w odwrotnej kolejności i dostaje ten sam wynik. Od kolejności zależy tylko to, ile przypisujemy każdemu krokowi w moście.
- **Każdy dokument raz.** Dashboard BI liczy zdublowane pliki z kas (lokal 17, 11–13.09.2026) dwa razy, a definicja raz: bierze plik bez dopisku „ (1)”, tak jak reguła jakości POS-02. **Żadna z dziewięciu reguł nie usuwa duplikatów**, więc w moście ich wpływ zostaje jako niewyjaśniona reszta: −29 998,73 zł we wrześniu i 0 w sierpniu.
- **Linia bez kwoty albo bez kursu to błąd, a nie pominięcie.** Paragon bez pozycji nie ma netto, a zamówienie w EUR sprzed pierwszego notowania nie ma kursu. Wtedy `suma` zatrzymuje się z komunikatem, zamiast po cichu zaniżyć przychód.

## 3. Reguły po kolei, z ręcznie policzonym przypadkiem

Wszystkie przypadki dotyczą września 2026 i są w [`conftest.py`](../api/tests/contexts_boundaries/revenue_bc/conftest.py). Najpierw sprawdzamy każdą regułę osobno na liniach BI, a na końcu całą definicję. Na liniach BI źródła dają razem 2 649,00 zł:

| Źródło | Linie BI we wrześniu | Kwota BI [zł] |
|---|---|---:|
| POS | paragon 183,00 wczytany dwa razy (zdublowany plik) | 366,00 |
| Zamówienia | 123,00 + 61,50 (zwrot) + 20 EUR + 123,00 (`qa@kawosz.pl`) + 246,00 (notatka testowa) + 61,50 (30.09 22:15 UTC) + 10 EUR | 645,00 |
| Subskrypcje | miesięczna 39,00 + roczna 399,00 | 438,00 |
| Karty | sprzedane we wrześniu: 100 + 50 + 150 | 300,00 |
| ERP | faktura 1 000,00 + korekta −100,00 | 900,00 |

### 3.1 POS netto według stawek VAT z pozycji

Paragon za 183,00 zł ma dwie pozycje: latte za 14,00 zł z VAT 8% i kawę za 169,00 zł z VAT 23%.

- netto = 14,00 / 1,08 + 169,00 / 1,23 = 12,96 + 137,40 = **150,36 zł**;
- BI ma ten paragon dwa razy, więc POS na liniach BI to 2 × 150,36 = 300,72 zł.

Stawka jest w każdej pozycji, bo w lokalach są stawki 5%, 8% i 23%. Jedna stawka 23% od kwoty paragonu zaniżyłaby netto POS we wrześniu 2026 o ok. 231 tys. zł ([`trzy_przychody.md`](trzy_przychody.md), 2.4). Test: `test_1_pos_netto_wedlug_stawek_z_pozycji`.

### 3.2 E-commerce, karty i subskrypcje netto 23%

- zamówienia: 645,00 / 1,23 = **524,39 zł**;
- subskrypcje: 438,00 / 1,23 = **356,10 zł**;
- karty: 300,00 / 1,23 = **243,90 zł**.

Stawka 23% obejmuje też wiersz `DOSTAWA`. W przypadku kart to uproszczenie: karta wielocelowa nie ma VAT przy sprzedaży, a przy realizacji VAT zależy od kupionego towaru. Test: `test_2_ecom_subskrypcje_i_karty_netto_23`.

### 3.3 Po odjęciu korekt ERP i zwrotów e-commerce

- **Korekty ERP:** korekta ma ujemną `kwota_netto` i własną datę, więc odejmuje się od faktur w miesiącu korekty. BI już to robi: ERP to 1 000,00 − 100,00 = 900,00 zł, a reguła niczego tu nie zmienia. Korekta nie wskazuje faktury, którą koryguje (ERP-12), więc nie da się jej przypisać do miesiąca faktury.
- **Zwroty e-commerce:** zamówienie z `zwrot = true` (61,50 zł) nie daje przychodu, więc zamówienia to 645,00 − 61,50 = **583,50 zł**. Tabela nie ma daty ani kwoty zwrotu (ECOM-07). Przyjmujemy więc zwrot pełny i ujęty w miesiącu zamówienia.

Test: `test_3_korekty_erp_i_zwroty_ecom_odjete`.

### 3.4 ERP po mapowaniu kontrahentów

Faktura na 1 000,00 zł jest wystawiona na rekord 260001, czyli drugi rekord firmy 200001. Po mapowaniu wskazuje 200001. **Suma ERP się nie zmienia (900,00 zł),** zmienia się tylko klient. Reguła jest potrzebna do przychodu według klienta, a do sumy nie.

Mapa obejmuje każdy dokument ERP: w sierpniu i wrześniu 2026 to 2 881 z 2 881. `mapa_kontrahentow.py` sprawdza, że miesięczne sumy faktur są takie same przed scaleniem i po nim. Pary oznaczone „do decyzji” zostają osobno, dopóki ktoś ich nie rozstrzygnie. Test: `test_4_erp_po_mapowaniu_kontrahentow`.

### 3.5 Subskrypcje roczne rozłożone na 12 miesięcy

Obciążenie planu rocznego (399,00 zł) daje 399,00 / 12 = 33,25 zł w miesiącu płatności i w każdym z 11 kolejnych.

| Płatność (UTC) | Miesiące przychodu | We wrześniu 2026 [zł] |
|---|---|---:|
| 2.09.2026 23:00 | IX.2026 – VIII.2027 | 33,25 |
| 14.10.2025 23:10 | X.2025 – IX.2026 | 33,25 |
| 30.09.2025 22:40 | IX.2025 – VIII.2026 (w czasie polskim: X.2025 – IX.2026, patrz 3.9) | 0,00 |

Subskrypcje we wrześniu: 39,00 + 33,25 + 33,25 = **105,50 zł** zamiast 438,00. Pierwsza dwunasta przypada na miesiąc płatności, bo od niego klient dostaje kawę. Test: `test_5_plan_roczny_na_12_miesiecy`.

### 3.6 Karty w dniu realizacji

| Karta | Sprzedaż | Realizacja | We wrześniu 2026 [zł] |
|---|---|---|---:|
| KP-1 | 3.09 | — | 0 |
| KP-2 | 20.08 | 5.09 | 200 |
| KP-3 | 4.09 | 20.09 | 50 |
| KP-4 | 10.09 | 2.10 | 0 |

Karty we wrześniu: 200 + 50 = **250,00 zł** zamiast 300,00 (kwoty brutto, bez reguły 2). Sprzedaż karty to przedpłata, czyli zobowiązanie, a przychód powstaje przy realizacji. Test: `test_6_karty_w_dniu_realizacji`.

### 3.7 EUR po kursie z `kursy_nbp` z dnia sprzedaży

| Zamówienie | Dzień sprzedaży | Kurs | W PLN |
|---|---|---|---:|
| 20,00 EUR | sobota 5.09 | brak notowania, kurs z piątku 4.09: 4,2208 | 84,42 |
| 10,00 EUR | niedziela 6.09 (UTC) | brak notowania, kurs z piątku 4.09: 4,2208 | 42,21 |

Zamówienia: 123 + 61,50 + 84,42 + 123 + 246 + 61,50 + 42,21 = **741,62 zł** zamiast 645,00.

Po regule 9 drugie zamówienie ma w Warszawie datę poniedziałek 7.09 00:30, więc bierze kurs z 7.09 (4,2039) i daje 42,04 zł. Sprawdza to test `test_kurs_z_dnia_po_czasie_polskim`. Test samej reguły: `test_7_eur_po_kursie_z_dnia_sprzedazy`.

Reguła jakości ECOM-04 i księgowość (skala #13) używają kursu z dnia poprzedzającego. Definicja bierze kurs z dnia sprzedaży, zgodnie z tą regułą. Na danych różnica jest mała: −7,24 zł we wrześniu i +13,39 zł w sierpniu 2026.

### 3.8 Bez zamówień testowych

Znikają zamówienie z e-mailem `qa@kawosz.pl` (123,00 zł) i zamówienie z notatką „zamówienie testowe QA” (246,00 zł). Zamówienie z notatką klienta „Proszę o szybką wysyłkę” zostaje. Zamówienia: 645,00 − 123,00 − 246,00 = **276,00 zł**.

Rozpoznawanie zamówień testowych opisuje sekcja 4. Testy: `test_8_bez_zamowien_testowych` i `test_rozpoznanie_zamowienia_testowego` (6 notatek i adresów z danych).

### 3.9 Doba według czasu polskiego

We wrześniu Warszawa to UTC+2.

| Dokument | UTC | Warszawa | Skutek dla września |
|---|---|---|---:|
| zamówienie 123,00 | 31.08 22:30 | 1.09 00:30 | +123,00 |
| zamówienie 61,50 | 30.09 22:15 | 1.10 00:15 | −61,50 |
| subskrypcja 39,00 | 31.08 22:20 | 1.09 00:20 | +39,00 |

Zamówienia: 645,00 + 123,00 − 61,50 = **706,50 zł**, subskrypcje: 438,00 + 39,00 = **477,00 zł**. POS, ERP i karty mają daty lokalne, więc reguła ich nie zmienia. Test: `test_9_doba_wedlug_czasu_polskiego`.

### 3.10 Cała definicja

| Źródło | Rachunek | Netto [zł] |
|---|---|---:|
| POS | paragon liczony raz: 14,00 / 1,08 + 169,00 / 1,23 | 150,36 |
| Zamówienia | 123/1,23 + 20/1,23 × 4,2208 + 10/1,23 × 4,2039 + 123/1,23 (bez zwrotu, dwóch testowych i zamówienia z 1.10) | 302,81 |
| Subskrypcje | 2 × 39/1,23 + 3 × 399/1,23/12 (dwie miesięczne i trzy dwunaste planów rocznych) | 144,51 |
| Karty | (200 + 50) / 1,23 | 203,25 |
| ERP | 1 000,00 − 100,00 | 900,00 |
| **Razem** | | **1 700,93** |

Test: `test_przychod_netto_wedlug_definicji`. Most na tych samych danych prowadzi od 2 649,00 zł (BI) do 1 700,93 zł. Reszta wynosi −150,37 zł: to drugi egzemplarz zdublowanego paragonu (150,36 zł), a 1 gr to zaokrąglenie sum do grosza (`test_most.py`).

## 4. Zamówienia testowe: po czym je rozpoznać

**Zamówienie jest testowe, jeśli ma notatkę testową albo e-mail w domenie `@kawosz.pl`.** Obie wartości reguła bierze z kontraktu [`ecom_zamowienia.yaml`](../api/api/data_platform/kontrakty/ecom_zamowienia.yaml), z parametrów reguły jakości ECOM-05:
- notatka pasuje do wyrażenia `test|nie realiz|nie wysyłać`, bez względu na wielkość liter;
- e-mail kończy się na `@kawosz.pl`, także z wielkimi literami (np. `QA+108@Kawosz.pl`).

Dzięki temu definicja i nocna kontrola jakości rozpoznają te same zamówienia.

**Dlaczego oba sygnały, a nie jeden.** W całej historii (I.2024–IX.2026):
- jest 595 zamówień testowych: 420 z notatką testową, 366 z adresem `@kawosz.pl`, 191 z jednym i drugim;
- sam adres nie wystarcza: część zamówień z notatką testową ma zwykły adres klienta (np. `karol.wisniewski@o2.pl`);
- sama notatka też nie wystarcza: część zamówień z adresu `@kawosz.pl` ma zwykłą notatkę klienta albo nie ma jej wcale.

**Potwierdzenie trzecim, niezależnym sygnałem:** ceny w pozycjach.
- Każde z 595 zamówień ma ceny spoza cennika: 1,179 × cennik w PLN i 0,293–0,298 × cena PLN w EUR (zwykłe zamówienia w EUR mają ok. 0,25).
- Żadne inne zamówienie nie ma cen spoza cennika.

Trzy sygnały wyznaczają więc dokładnie ten sam zbiór. Ceny nie są w regule, bo są tylko skutkiem testu, a nie jego oznaczeniem. Prawdziwa promocja też zmieniłaby cenę.

Żadne zamówienie testowe nie ma flagi `zwrot`, więc bez tej reguły wszystkie wchodzą do przychodu. W sierpniu 2026 było ich 16 (1 830,19 zł brutto), a we wrześniu 74 (73 w PLN na 10 852,28 zł i 1 na 17,97 EUR), licząc w czasie polskim.

**10 przykładów z sierpnia i września 2026** (czas polski, kwoty brutto w walucie zamówienia):

| ID | Czas | Waluta | Brutto | E-mail | Notatka | Sygnał | Ceny ÷ cennik |
|---:|---|---|---:|---|---|---|---:|
| 1207608 | 2026-08-04 23:29 | PLN | 66,01 | qa@kawosz.pl | — | e-mail | 1,179 |
| 1207679 | 2026-08-05 12:53 | PLN | 203,25 | test@kawosz.pl | — | e-mail | 1,179 |
| 1210454 | 2026-08-18 21:05 | PLN | 117,89 | jan.testowy@kawosz.pl | — | e-mail | 1,179 |
| 1214268 | 2026-09-05 10:14 | PLN | 90,67 | qa@kawosz.pl | Zostawić u sąsiada (nr 4) | e-mail | 1,179 |
| 1219471 | 2026-09-25 10:42 | EUR | 17,97 | jan.testowy@kawosz.pl | — | e-mail | 0,295 |
| 1207404 | 2026-08-04 01:43 | PLN | 73,67 | karol.wisniewski@o2.pl | Testowe – zwrot środków automatyczny | notatka | 1,179 |
| 1208334 | 2026-08-08 14:38 | PLN | 98,33 | kwiatkowski.artur531@interia.pl | test nowego checkoutu – Marek | notatka | 1,179 |
| 1215091 | 2026-09-08 12:00 | PLN | 161,58 | pietrzak.anna543@gmail.com | prosze nie realizowac (test) | notatka | 1,179 |
| 1210262 | 2026-08-17 23:54 | PLN | 77,91 | sklep.test@kawosz.pl | TEST – nie wysyłać | oba | 1,179 |
| 1213544 | 2026-09-02 11:44 | PLN | 203,24 | test@kawosz.pl | test bramki płatności, anulować | oba | 1,179 |

Zamówienie 1214268 ma zwykłą notatkę klienta, a 1207404 ma notatkę „zwrot środków automatyczny”, ale bez flagi `zwrot`. Oba przypadki pokazują, dlaczego sygnały trzeba łączyć.

```sql
-- Zamówienia testowe z sygnałami i stosunkiem cen do cennika (ten sam warunek co reguła 8 i ECOM-05)
WITH t AS (
    SELECT z.*, timezone('Europe/Warsaw', data_utc::TIMESTAMP AT TIME ZONE 'UTC') AS czas_pl,
           coalesce(regexp_matches(notatka, '(?i)test|nie realiz|nie wysyłać'), false) AS sygnal_notatka,
           coalesce(ends_with(lower(email), '@kawosz.pl'), false) AS sygnal_email
    FROM ecom_zamowienia z),
c AS (SELECT p.id_zamowienia AS id, round(avg(p.cena_brutto / pr.cena_brutto_pln), 3) AS cena_do_cennika
      FROM ecom_pozycje p JOIN ecom_produkty pr USING (sku) GROUP BY 1)
SELECT id, czas_pl, waluta, brutto, email, notatka, sygnal_notatka, sygnal_email, cena_do_cennika
FROM t LEFT JOIN c USING (id)
WHERE (sygnal_notatka OR sygnal_email) AND czas_pl >= '2026-08-01'
ORDER BY id;
```

## 5. Założenia do potwierdzenia

| # | Założenie | Dlaczego | Kto potwierdza |
|---:|---|---|---|
| 1 | Zwrot e-commerce jest pełny i ujęty w miesiącu zamówienia | tabela nie ma daty ani kwoty zwrotu (skala #7, ECOM-07) | E-commerce |
| 2 | Plan roczny: pierwsza dwunasta w miesiącu płatności | opis reguły nie mówi, od którego miesiąca | Finanse |
| 3 | Karty podarunkowe netto 23% | tak brzmi reguła; przy realizacji VAT zależy od towaru (np. 8% na kawę w lokalu) | Finanse |
| 4 | Kurs EUR z dnia sprzedaży, a nie z dnia poprzedzającego | tak brzmi reguła; ECOM-04 i księgowość biorą dzień poprzedzający (różnica kilkanaście zł miesięcznie) | Finanse |
| 5 | Korekta ERP w miesiącu swojej daty | korekta nie wskazuje faktury (ERP-12) | Finanse |
| 6 | Każdy paragon liczy się raz | duplikatów nie usuwa żadna reguła, robi to tylko założenie definicji; nocą blokuje je POS-02 | właściciel definicji: dopisać regułę albo zostawić założenie |
