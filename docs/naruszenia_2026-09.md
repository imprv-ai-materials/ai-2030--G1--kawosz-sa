# Naruszenia reguł jakości: 2026-09-01 – 2026-09-30

Wynik uruchomienia 37 reguł z [`reguly.md`](reguly.md) na danych od 2026-09-01 do 2026-09-30 (`kawosz.duckdb`). Każda reguła sprawdza wszystkie rekordy z zakresu, a Pandera zbiera wszystkie naruszenia naraz (`lazy=True`). Błąd jednej reguły nie przerywa pozostałych.

Raport wygenerowano 2026-10-11 poleceniem:

```bash
PYTHONPATH=api poetry run python -m api.data_platform.reguly.uruchom --od 2026-09-01 --dzien 2026-09-30 --raport docs/naruszenia_2026-09.md
```

## Podsumowanie

- **Wsad zablokowany: tak.** Reguły blokujące z naruszeniami: POS-02, POS-03, POS-04, ERP-06, ERP-08.
- Reguły z naruszeniami: 19 z 37 (5 blokujących, 14 ostrzegających). Bez naruszeń: 18.
- „Rekordy” to wiersze ramki, którą sprawdza reguła (kolumna „Jednostka”: paragon, pozycja, lokal × dzień…). Ten sam rekord źródłowy może łamać kilka reguł, więc liczb z różnych reguł nie należy sumować.

| Reguła | Blokuje wsad | Właściciel | Rekordy z naruszeniem | Sprawdzone | Jednostka | Pozycja w skali |
|---|---|---|---:|---:|---|---|
| POS-02 | **tak** | Zespół danych | 988 | 70 097 | paragon | #15 |
| POS-03 | **tak** | Zespół danych | 988 | 70 097 | paragon | #15, #24 |
| POS-04 | **tak** | Zespół danych | 3 | 720 | lokal × dzień | #15, #25 |
| POS-07 | nie (ostrzega) | Operacje lokali (POS) | 14 | 70 097 | paragon | #21 |
| POS-08 | nie (ostrzega) | Operacje lokali (POS) | 3 | 137 | paragon | #22 |
| POS-09 | nie (ostrzega) | Operacje lokali (POS) | 134 | 134 | storno | #19 |
| POS-11 | nie (ostrzega) | Zespół danych | 3 | 720 | lokal × dzień | #15 |
| ERP-03 | nie (ostrzega) | Finanse i księgowość | 991 | 1 445 | dokument | #12 |
| ERP-06 | **tak** | Dane podstawowe (kartoteka ERP) | 789 | 5 013 | pozycja | #1 |
| ERP-07 | nie (ostrzega) | Dane podstawowe (kartoteka ERP) | 3 | 5 013 | pozycja | #20 |
| ERP-08 | **tak** | Sprzedaż B2B (kontrahenci) | 58 | 1 445 | dokument | #4, #27 |
| ERP-09 | nie (ostrzega) | Finanse i księgowość | 13 | 1 445 | dokument | #14 |
| ERP-10 | nie (ostrzega) | Sprzedaż B2B (kontrahenci) | 164 | 1 445 | dokument | #2, #4 |
| ERP-12 | nie (ostrzega) | Finanse i księgowość | 37 | 37 | korekta | #16 |
| ECOM-05 | nie (ostrzega) | E-commerce | 74 | 7 689 | zamówienie | #18 |
| ECOM-06 | nie (ostrzega) | E-commerce | 761 | 7 689 | zamówienie | #9 |
| ECOM-07 | nie (ostrzega) | E-commerce | 1 014 | 1 014 | zamówienie ze zwrotem | #7 |
| ECOM-08 | nie (ostrzega) | E-commerce | 2 974 | 11 209 | pozycja | #6 |
| ECOM-10 | nie (ostrzega) | E-commerce | 30 | 30 | dzień | #31 |

## Szczegóły naruszeń

### POS-02: blokuje wsad

Paragon (lokal, nr_paragonu) występuje w danych raz.

- Właściciel: Zespół danych. Pozycja w `skala_problemu.md`: #15.
- Rekordy z naruszeniem: 988 z 70 097 (jednostka: paragon).
- Naruszenia (rekord może łamać kilka warunków naraz):
  - powtórzony klucz (lokal, nr_paragonu): 988

Przykłady (5 z 988):

| lokal | nr_paragonu | data_czas | kwota_brutto | plik | naruszenie |
|---|---|---|---|---|---|
| 17 | 2609110001 | 2026-09-11 07:10:22 | 14,00 | pos_paragony_17_2026-09-11 (1).csv | powtórzony klucz (lokal, nr_paragonu) |
| 17 | 2609110002 | 2026-09-11 07:11:36 | 10,00 | pos_paragony_17_2026-09-11 (1).csv | powtórzony klucz (lokal, nr_paragonu) |
| 17 | 2609110003 | 2026-09-11 07:11:41 | 14,00 | pos_paragony_17_2026-09-11 (1).csv | powtórzony klucz (lokal, nr_paragonu) |
| 17 | 2609110004 | 2026-09-11 07:16:11 | 146,00 | pos_paragony_17_2026-09-11 (1).csv | powtórzony klucz (lokal, nr_paragonu) |
| 17 | 2609110005 | 2026-09-11 07:16:53 | 42,00 | pos_paragony_17_2026-09-11 (1).csv | powtórzony klucz (lokal, nr_paragonu) |

### POS-03: blokuje wsad

Nazwa pliku, numer paragonu i czas są spójne; numeracja w dniu rośnie razem z czasem.

- Właściciel: Zespół danych. Pozycja w `skala_problemu.md`: #15, #24.
- Rekordy z naruszeniem: 988 z 70 097 (jednostka: paragon).
- Naruszenia (rekord może łamać kilka warunków naraz):
  - plik = pos_paragony_{lokal}_{dzień}.csv: 988

Przykłady (5 z 988):

| lokal | nr_paragonu | data_czas | storno | kwota_brutto | plik | plik_oczekiwany | data_w_numerze | data_paragonu | najpozniej_wczesniejszy | naruszenie |
|---|---|---|---|---|---|---|---|---|---|---|
| 17 | 2609110001 | 2026-09-11 07:10:22 | 0 | 14,00 | pos_paragony_17_2026-09-11 (1).csv | pos_paragony_17_2026-09-11.csv | 260911 | 260911 | — | plik = pos_paragony_{lokal}_{dzień}.csv |
| 17 | 2609110002 | 2026-09-11 07:11:36 | 0 | 10,00 | pos_paragony_17_2026-09-11 (1).csv | pos_paragony_17_2026-09-11.csv | 260911 | 260911 | 2026-09-11 07:10:22 | plik = pos_paragony_{lokal}_{dzień}.csv |
| 17 | 2609110003 | 2026-09-11 07:11:41 | 0 | 14,00 | pos_paragony_17_2026-09-11 (1).csv | pos_paragony_17_2026-09-11.csv | 260911 | 260911 | 2026-09-11 07:11:36 | plik = pos_paragony_{lokal}_{dzień}.csv |
| 17 | 2609110004 | 2026-09-11 07:16:11 | 0 | 146,00 | pos_paragony_17_2026-09-11 (1).csv | pos_paragony_17_2026-09-11.csv | 260911 | 260911 | 2026-09-11 07:11:41 | plik = pos_paragony_{lokal}_{dzień}.csv |
| 17 | 2609110005 | 2026-09-11 07:16:53 | 0 | 42,00 | pos_paragony_17_2026-09-11 (1).csv | pos_paragony_17_2026-09-11.csv | 260911 | 260911 | 2026-09-11 07:16:11 | plik = pos_paragony_{lokal}_{dzień}.csv |

### POS-04: blokuje wsad

Suma nagłówków paragonów lokalu w dniu równa się sumie ich pozycji.

- Właściciel: Zespół danych. Pozycja w `skala_problemu.md`: #15, #25.
- Rekordy z naruszeniem: 3 z 720 (jednostka: lokal × dzień).
- Naruszenia (rekord może łamać kilka warunków naraz):
  - liczba paragonów = liczba paragonów w pozycjach: 3
  - Σ kwota_brutto = Σ ilosc × cena_brutto: 3

Przykłady (3 z 3):

| lokal | dzien | paragony | paragony_w_pozycjach | suma_naglowkow | suma_pozycji | naruszenie |
|---|---|---|---|---|---|---|
| 17 | 2026-09-11 | 702 | 351 | 23 160,00 | 11 580,00 | liczba paragonów = liczba paragonów w pozycjach; Σ kwota_brutto = Σ ilosc × cena_brutto |
| 17 | 2026-09-12 | 598 | 299 | 19 764,00 | 9 882,00 | liczba paragonów = liczba paragonów w pozycjach; Σ kwota_brutto = Σ ilosc × cena_brutto |
| 17 | 2026-09-13 | 676 | 338 | 22 444,00 | 11 222,00 | liczba paragonów = liczba paragonów w pozycjach; Σ kwota_brutto = Σ ilosc × cena_brutto |

### POS-07: ostrzega

Paragon ma metodę płatności.

- Właściciel: Operacje lokali (POS). Pozycja w `skala_problemu.md`: #21.
- Rekordy z naruszeniem: 14 z 70 097 (jednostka: paragon).
- Naruszenia (rekord może łamać kilka warunków naraz):
  - metoda_platnosci: brak wartości: 14

Przykłady (5 z 14):

| lokal | nr_paragonu | data_czas | kwota_brutto | metoda_platnosci | naruszenie |
|---|---|---|---|---|---|
| 9 | 2609030054 | 2026-09-03 15:55:07 | 34,00 | — | metoda_platnosci: brak wartości |
| 9 | 2609060010 | 2026-09-06 09:47:48 | 19,00 | — | metoda_platnosci: brak wartości |
| 9 | 2609090007 | 2026-09-09 09:25:05 | 14,00 | — | metoda_platnosci: brak wartości |
| 9 | 2609120018 | 2026-09-12 13:21:48 | 13,00 | — | metoda_platnosci: brak wartości |
| 9 | 2609140046 | 2026-09-14 13:06:58 | 17,00 | — | metoda_platnosci: brak wartości |

### POS-08: ostrzega

Paragon z ujemną pozycją lub kwotą (zwrot, anulowanie) ma storno = 1, a storno ma ujemną kwotę.

- Właściciel: Operacje lokali (POS). Pozycja w `skala_problemu.md`: #22.
- Rekordy z naruszeniem: 3 z 137 (jednostka: paragon).
- Naruszenia (rekord może łamać kilka warunków naraz):
  - ujemna ilość lub kwota bez storno = 1: 3

Przykłady (3 z 3):

| lokal | nr_paragonu | data_czas | storno | kwota_brutto | pozycje_ujemne | naruszenie |
|---|---|---|---|---|---|---|
| 6 | 2609100064 | 2026-09-10 18:09:32 | 0 | -50,00 | 1 | ujemna ilość lub kwota bez storno = 1 |
| 14 | 2609300091 | 2026-09-30 18:56:23 | 0 | -38,00 | 1 | ujemna ilość lub kwota bez storno = 1 |
| 17 | 2609210247 | 2026-09-21 16:24:32 | 0 | 55,00 | 1 | ujemna ilość lub kwota bez storno = 1 |

### POS-09: ostrzega

Storno wskazuje numer paragonu, który stornuje.

- Właściciel: Operacje lokali (POS). Pozycja w `skala_problemu.md`: #19.
- Rekordy z naruszeniem: 134 z 134 (jednostka: storno).
- Naruszenia (rekord może łamać kilka warunków naraz):
  - brak kolumny nr_paragonu_stornowanego: 134

Przykłady (5 z 134):

| lokal | nr_paragonu | data_czas | kwota_brutto | metoda_platnosci | storno | kanal | plik | naruszenie |
|---|---|---|---|---|---|---|---|---|
| 1 | 2609080115 | 2026-09-08 13:18:55 | -40,00 | karta | 1 | sala | pos_paragony_1_2026-09-08.csv | brak kolumny nr_paragonu_stornowanego |
| 1 | 2609140104 | 2026-09-14 11:53:49 | -32,00 | karta | 1 | wynos | pos_paragony_1_2026-09-14.csv | brak kolumny nr_paragonu_stornowanego |
| 1 | 2609290107 | 2026-09-29 17:06:23 | -59,00 | karta | 1 | aplikacja | pos_paragony_1_2026-09-29.csv | brak kolumny nr_paragonu_stornowanego |
| 2 | 2609030107 | 2026-09-03 11:12:32 | -8,00 | karta | 1 | wynos | pos_paragony_2_2026-09-03.csv | brak kolumny nr_paragonu_stornowanego |
| 2 | 2609040106 | 2026-09-04 10:24:29 | -8,00 | karta | 1 | wynos | pos_paragony_2_2026-09-04.csv | brak kolumny nr_paragonu_stornowanego |

### POS-11: ostrzega

Liczba paragonów lokalu w dniu to 0.4–1.8 × mediany z 28 poprzednich dni.

- Właściciel: Zespół danych. Pozycja w `skala_problemu.md`: #15.
- Rekordy z naruszeniem: 3 z 720 (jednostka: lokal × dzień).
- Naruszenia (rekord może łamać kilka warunków naraz):
  - paragony = 0.4–1.8 × mediana z 28 dni: 3

Przykłady (3 z 3):

| lokal | dzien | paragony | mediana_28_dni | dni_historii | naruszenie |
|---|---|---|---|---|---|
| 17 | 2026-09-11 | 702 | 312,50 | 28 | paragony = 0.4–1.8 × mediana z 28 dni |
| 17 | 2026-09-12 | 598 | 313,00 | 28 | paragony = 0.4–1.8 × mediana z 28 dni |
| 17 | 2026-09-13 | 676 | 313,00 | 28 | paragony = 0.4–1.8 × mediana z 28 dni |

### ERP-03: ostrzega

VAT dokumentu zgadza się ze stawkami indeksów (stawki inne niż 23% wpisuje księgowość).

- Właściciel: Finanse i księgowość. Pozycja w `skala_problemu.md`: #12.
- Rekordy z naruszeniem: 991 z 1 445 (jednostka: dokument).
- Naruszenia (rekord może łamać kilka warunków naraz):
  - VAT = Σ netto pozycji × stawka indeksu: 991

Przykłady (5 z 991):

| nr_faktury | data | kwota_netto | vat | vat_wg_stawek | indeksy_stawka_inna | naruszenie |
|---|---|---|---|---|---|---|
| FV/2026/09/00001 | 2026-09-01 | 220,61 | 50,74 | 50,22 | 20.01.0001 | VAT = Σ netto pozycji × stawka indeksu |
| FV/2026/09/00002 | 2026-09-11 | 1 010,86 | 232,50 | 222,61 | 20.01.0001 | VAT = Σ netto pozycji × stawka indeksu |
| FV/2026/09/00004 | 2026-09-18 | 657,24 | 151,17 | 150,65 | 20.01.0001 | VAT = Σ netto pozycji × stawka indeksu |
| FV/2026/09/00005 | 2026-09-21 | 2 002,19 | 460,50 | 450,10 | 20.01.0001 | VAT = Σ netto pozycji × stawka indeksu |
| FV/2026/09/00007 | 2026-09-25 | 2 217,57 | 510,04 | 496,00 | 20.01.0001 | VAT = Σ netto pozycji × stawka indeksu |

### ERP-06: blokuje wsad

Indeks sprzedany na dokumencie ma kategorię w kartotece.

- Właściciel: Dane podstawowe (kartoteka ERP). Pozycja w `skala_problemu.md`: #1.
- Rekordy z naruszeniem: 789 z 5 013 (jednostka: pozycja).
- Naruszenia (rekord może łamać kilka warunków naraz):
  - kategoria: brak wartości: 789

Przykłady (5 z 789):

| nr_faktury | indeks | nazwa | kategoria | netto | naruszenie |
|---|---|---|---|---|---|
| FV/2026/09/00002 | 80.01.0002 | ABONAMENT KAWOSZ DLA BIUR – PLAN M | — | 778,00 | kategoria: brak wartości |
| FV/2026/09/00003 | 80.01.0004 | ABONAMENT KAWOSZ DLA BIUR – PLAN XL | — | 3 224,52 | kategoria: brak wartości |
| FV/2026/09/00007 | 80.01.0002 | ABONAMENT KAWOSZ DLA BIUR – PLAN M | — | 1 691,02 | kategoria: brak wartości |
| FV/2026/09/00010 | 80.01.0002 | ABONAMENT KAWOSZ DLA BIUR – PLAN M | — | 2 055,05 | kategoria: brak wartości |
| FV/2026/09/00012 | 80.01.0002 | ABONAMENT KAWOSZ DLA BIUR – PLAN M | — | 1 869,58 | kategoria: brak wartości |

### ERP-07: ostrzega

Nazwa sprzedanego indeksu jest w kartotece jedna (bez drugiego indeksu o tej samej nazwie).

- Właściciel: Dane podstawowe (kartoteka ERP). Pozycja w `skala_problemu.md`: #20.
- Rekordy z naruszeniem: 3 z 5 013 (jednostka: pozycja).
- Naruszenia (rekord może łamać kilka warunków naraz):
  - indeksy_o_tej_nazwie: equal_to(1): 3

Przykłady (3 z 3):

| nr_faktury | indeks | nazwa | kategoria | indeksy_o_tej_nazwie | naruszenie |
|---|---|---|---|---|---|
| FV/2026/09/00092 | 10.02.0001 | KAWA ZIARN. BRAZYLIA SANTOS 1KG | Kawa ziarnista | 2 | indeksy_o_tej_nazwie: equal_to(1) |
| FV/2026/09/00210 | 10.02.0001 | KAWA ZIARN. BRAZYLIA SANTOS 1KG | Kawa ziarnista | 2 | indeksy_o_tej_nazwie: equal_to(1) |
| FV/2026/09/00996 | 10.02.0001 | KAWA ZIARN. BRAZYLIA SANTOS 1KG | Kawa ziarnista | 2 | indeksy_o_tej_nazwie: equal_to(1) |

### ERP-08: blokuje wsad

Dokument trafia na główny rekord kontrahenta, a nie na drugi rekord tej samej firmy (NIP lub adres).

- Właściciel: Sprzedaż B2B (kontrahenci). Pozycja w `skala_problemu.md`: #4, #27.
- Rekordy z naruszeniem: 58 z 1 445 (jednostka: dokument).
- Naruszenia (rekord może łamać kilka warunków naraz):
  - brak starszego kontrahenta pod tym samym adresem: 58
  - brak starszego kontrahenta z tym samym NIP-em: 53

Przykłady (5 z 58):

| nr_faktury | data | kwota_netto | id_kontrahenta | nazwa | nip | najstarszy_z_tym_nip | najstarszy_pod_adresem | naruszenie |
|---|---|---|---|---|---|---|---|---|
| FV/2026/09/01372 | 2026-09-30 | 5 824,48 | 260039 | LABORATORIUM SOŁACZ SP Z OO | 162308658 | 260039 | 200430 | brak starszego kontrahenta pod tym samym adresem |
| FV/2026/09/01352 | 2026-09-30 | 3 447,83 | 260003 | Agencja Jeżyce Spółka Akcyjna | 9520565285 | 201153 | 201153 | brak starszego kontrahenta pod tym samym adresem; brak starszego kontrahenta z tym samym NIP-em |
| FV/2026/09/01380 | 2026-09-30 | 2 728,77 | 260053 | AGENCJA WIELKOPOLSKA SP Z OO | 305059875 | 260053 | 200410 | brak starszego kontrahenta pod tym samym adresem |
| FV/2026/09/01353 | 2026-09-30 | 4 830,97 | 260005 | Walczak spółka z o.o. | 9145930530 | 200109 | 200109 | brak starszego kontrahenta pod tym samym adresem; brak starszego kontrahenta z tym samym NIP-em |
| FV/2026/09/01384 | 2026-09-30 | 1 041,65 | 260063 | SPÓŁDZIELNIA KWADRANT SP Z OO | 471122027 | 260063 | 201678 | brak starszego kontrahenta pod tym samym adresem |

### ERP-09: ostrzega

Kontrahent dokumentu ma NIP z 10 cyframi i poprawną sumą kontrolną.

- Właściciel: Finanse i księgowość. Pozycja w `skala_problemu.md`: #14.
- Rekordy z naruszeniem: 13 z 1 445 (jednostka: dokument).
- Naruszenia (rekord może łamać kilka warunków naraz):
  - NIP: 10 cyfr i poprawna suma kontrolna: 13

Przykłady (5 z 13):

| nr_faktury | data | id_kontrahenta | nazwa | nip | nip10 | naruszenie |
|---|---|---|---|---|---|---|
| FV/2026/09/00068 | 2026-09-30 | 200101 | Wilda Sp. z o.o. | 670700527 | 670700527 | NIP: 10 cyfr i poprawna suma kontrolna |
| FV/2026/09/00379 | 2026-09-30 | 200584 | Jeżyce Partners Sp. z o.o. | 960741202 | 960741202 | NIP: 10 cyfr i poprawna suma kontrolna |
| FV/2026/09/00424 | 2026-09-30 | 200645 | BIUROWIEC IMPULS SP. Z O.O. | 607160764 | 607160764 | NIP: 10 cyfr i poprawna suma kontrolna |
| FV/2026/09/00517 | 2026-09-30 | 200786 | Pracownia Wektor Sp. z o.o. | 360672289 | 360672289 | NIP: 10 cyfr i poprawna suma kontrolna |
| FV/2026/09/00533 | 2026-09-30 | 200806 | Mazowsze s.c. | 265993040 | 265993040 | NIP: 10 cyfr i poprawna suma kontrolna |

### ERP-10: ostrzega

Kontrahent dokumentu ma ID biura z CRM i jest jedynym kontrahentem z tym ID.

- Właściciel: Sprzedaż B2B (kontrahenci). Pozycja w `skala_problemu.md`: #2, #4.
- Rekordy z naruszeniem: 164 z 1 445 (jednostka: dokument).
- Naruszenia (rekord może łamać kilka warunków naraz):
  - id_biura_crm: brak wartości: 148
  - ID z CRM przypięte do kilku kontrahentów: 16

Przykłady (5 z 164):

| nr_faktury | data | kwota_netto | id_kontrahenta | nazwa | id_biura_crm | kontrahenci_z_tym_crm | naruszenie |
|---|---|---|---|---|---|---|---|
| FV/2026/09/00198 | 2026-09-30 | 4 841,33 | 200303 | Aleja Sp. z o.o. | 10303 | 2 | ID z CRM przypięte do kilku kontrahentów |
| FV/2026/09/00006 | 2026-09-22 | 750,80 | 201724 | Grupa Kwartet Sp. z o.o. | — | — | id_biura_crm: brak wartości |
| FV/2026/09/00814 | 2026-09-30 | 2 182,90 | 201255 | Biuro Gopło Sp. z o.o. | 11255 | 2 | ID z CRM przypięte do kilku kontrahentów |
| FV/2026/09/00012 | 2026-09-30 | 1 938,94 | 200010 | SKŁODOWSKA DESIGN SP. Z O.O. | — | — | id_biura_crm: brak wartości |
| FV/2026/09/00863 | 2026-09-30 | 2 328,49 | 201320 | MŁYN SP. Z O.O. | 11320 | 2 | ID z CRM przypięte do kilku kontrahentów |

### ERP-12: ostrzega

Korekta wskazuje numer faktury, którą koryguje.

- Właściciel: Finanse i księgowość. Pozycja w `skala_problemu.md`: #16.
- Rekordy z naruszeniem: 37 z 37 (jednostka: korekta).
- Naruszenia (rekord może łamać kilka warunków naraz):
  - brak kolumny nr_faktury_korygowanej: 37

Przykłady (5 z 37):

| nr_faktury | id_kontrahenta | data | typ | waluta | kwota_netto | vat | naruszenie |
|---|---|---|---|---|---|---|---|
| KOR/2026/09/0001 | 200019 | 2026-09-01 | korekta | PLN | -1 272,35 | -292,64 | brak kolumny nr_faktury_korygowanej |
| KOR/2026/09/0002 | 200556 | 2026-09-01 | korekta | PLN | -95,80 | -22,03 | brak kolumny nr_faktury_korygowanej |
| KOR/2026/09/0003 | 200244 | 2026-09-03 | korekta | PLN | -493,36 | -113,47 | brak kolumny nr_faktury_korygowanej |
| KOR/2026/09/0004 | 200307 | 2026-09-03 | korekta | PLN | -120,22 | -27,65 | brak kolumny nr_faktury_korygowanej |
| KOR/2026/09/0005 | 201089 | 2026-09-03 | korekta | PLN | -10,84 | -2,49 | brak kolumny nr_faktury_korygowanej |

### ECOM-05: ostrzega

Zamówienie nie jest testowe: e-mail spoza @kawosz.pl, bez notatki testowej, ceny PLN z cennika.

- Właściciel: E-commerce. Pozycja w `skala_problemu.md`: #18.
- Rekordy z naruszeniem: 74 z 7 689 (jednostka: zamówienie).
- Naruszenia (rekord może łamać kilka warunków naraz):
  - cena PLN inna niż w cenniku: 73
  - notatka testowa: 54
  - e-mail w domenie @kawosz.pl: 23

Przykłady (5 z 74):

| id | waluta | brutto | email | notatka | ceny_spoza_cennika | naruszenie |
|---|---|---|---|---|---|---|
| 1214182 | PLN | 164,98 | sklep.test@kawosz.pl | — | 3 | cena PLN inna niż w cenniku; e-mail w domenie @kawosz.pl |
| 1213245 | PLN | 69,42 | sklep.test@kawosz.pl | TEST – nie wysyłać | 1 | cena PLN inna niż w cenniku; e-mail w domenie @kawosz.pl; notatka testowa |
| 1213878 | PLN | 70,26 | karolinakozlowska21@gmail.com | [TEST] sprawdzenie integracji z kurierem | 1 | cena PLN inna niż w cenniku; notatka testowa |
| 1219471 | EUR | 17,97 | jan.testowy@kawosz.pl | — | 0 | e-mail w domenie @kawosz.pl |
| 1214268 | PLN | 90,67 | qa@kawosz.pl | Zostawić u sąsiada (nr 4) | 1 | cena PLN inna niż w cenniku; e-mail w domenie @kawosz.pl |

### ECOM-06: ostrzega

Zamówienie ma e-mail klienta (także przy pobraniu).

- Właściciel: E-commerce. Pozycja w `skala_problemu.md`: #9.
- Rekordy z naruszeniem: 761 z 7 689 (jednostka: zamówienie).
- Naruszenia (rekord może łamać kilka warunków naraz):
  - email: brak wartości: 761

Przykłady (5 z 761):

| id | metoda_platnosci | brutto | email | naruszenie |
|---|---|---|---|---|
| 1213210 | pobranie | 52,50 | — | email: brak wartości |
| 1213224 | pobranie | 55,39 | — | email: brak wartości |
| 1213229 | pobranie | 57,55 | — | email: brak wartości |
| 1213257 | pobranie | 139,79 | — | email: brak wartości |
| 1213258 | pobranie | 136,91 | — | email: brak wartości |

### ECOM-07: ostrzega

Zamówienie ze zwrotem ma datę i kwotę zwrotu.

- Właściciel: E-commerce. Pozycja w `skala_problemu.md`: #7.
- Rekordy z naruszeniem: 1 014 z 1 014 (jednostka: zamówienie ze zwrotem).
- Naruszenia (rekord może łamać kilka warunków naraz):
  - brak kolumny data_zwrotu: 1 014
  - brak kolumny kwota_zwrotu: 1 014

Przykłady (5 z 1 014):

| id | data_utc | waluta | brutto | email | notatka | zwrot | metoda_platnosci | naruszenie |
|---|---|---|---|---|---|---|---|---|
| 1213211 | 2026-08-31 22:02:32 | PLN | 50,34 | emiliajakubowska89@gmail.com | — | tak | BLIK | brak kolumny data_zwrotu; brak kolumny kwota_zwrotu |
| 1213212 | 2026-08-31 22:03:10 | PLN | 136,91 | piotrowska.sylwia791@poczta.fm | — | tak | karta | brak kolumny data_zwrotu; brak kolumny kwota_zwrotu |
| 1213215 | 2026-08-31 22:04:53 | PLN | 68,37 | wrobel.marta711@onet.pl | — | tak | przelew | brak kolumny data_zwrotu; brak kolumny kwota_zwrotu |
| 1213217 | 2026-08-31 22:06:47 | PLN | 90,73 | weronikajakubowska45@interia.pl | — | tak | karta | brak kolumny data_zwrotu; brak kolumny kwota_zwrotu |
| 1213220 | 2026-08-31 22:12:21 | PLN | 59,72 | dariusz.dudek@wp.pl | — | tak | karta | brak kolumny data_zwrotu; brak kolumny kwota_zwrotu |

### ECOM-08: ostrzega

Sprzedany produkt ma w cenniku sklepu nazwę, której nie nosi inny SKU.

- Właściciel: E-commerce. Pozycja w `skala_problemu.md`: #6.
- Rekordy z naruszeniem: 2 974 z 11 209 (jednostka: pozycja).
- Naruszenia (rekord może łamać kilka warunków naraz):
  - sku_o_tej_nazwie: equal_to(1): 2 974

Przykłady (5 z 2 974):

| id_zamowienia | sku | nazwa | sku_o_tej_nazwie | naruszenie |
|---|---|---|---|---|
| 1213214 | KW-BRAZYLIA-006 | Brazylia Santos – kawa ziarnista 1000 g | 2 | sku_o_tej_nazwie: equal_to(1) |
| 1213216 | KW-KENIAAAK-007 | Kenia AA – kawa ziarnista 250 g | 2 | sku_o_tej_nazwie: equal_to(1) |
| 1213216 | KW-KOLUMBIA-005 | Kolumbia Huila – kawa ziarnista 250 g | 2 | sku_o_tej_nazwie: equal_to(1) |
| 1213221 | KW-ETIOPIAY-004 | Etiopia Yirgacheffe – kawa ziarnista 250 g | 2 | sku_o_tej_nazwie: equal_to(1) |
| 1213221 | KW-KENIAAA-021 | Kenia AA – kawa ziarnista 250 g | 2 | sku_o_tej_nazwie: equal_to(1) |

### ECOM-10: ostrzega

Każda realizacja karty podarunkowej ma w tym dniu płatność „karta podarunkowa” w POS lub sklepie.

- Właściciel: E-commerce. Pozycja w `skala_problemu.md`: #31.
- Rekordy z naruszeniem: 30 z 30 (jednostka: dzień).
- Naruszenia (rekord może łamać kilka warunków naraz):
  - realizacje kart = płatności „karta podarunkowa” w POS i sklepie: 30

Przykłady (5 z 30):

| dzien | realizacje | kwota_realizacji | platnosci_karta_podarunkowa | naruszenie |
|---|---|---|---|---|
| 2026-09-01 | 15 | 1 850,00 | 0,00 | realizacje kart = płatności „karta podarunkowa” w POS i sklepie |
| 2026-09-02 | 11 | 1 250,00 | 0,00 | realizacje kart = płatności „karta podarunkowa” w POS i sklepie |
| 2026-09-03 | 9 | 1 050,00 | 0,00 | realizacje kart = płatności „karta podarunkowa” w POS i sklepie |
| 2026-09-04 | 13 | 1 900,00 | 0,00 | realizacje kart = płatności „karta podarunkowa” w POS i sklepie |
| 2026-09-05 | 15 | 2 700,00 | 0,00 | realizacje kart = płatności „karta podarunkowa” w POS i sklepie |

## Reguły bez naruszeń

| Reguła | Poziom | Sprawdzone | Jednostka | Pozycja w skali |
|---|---|---:|---|---|
| POS-01 | blokuje | 70 097 | paragon | — |
| POS-05 | blokuje | 69 109 | paragon | — |
| POS-06 | blokuje | 105 380 | pozycja | #24, #3 |
| POS-10 | blokuje | 720 | lokal × dzień | — |
| ERP-01 | blokuje | 1 445 | dokument | — |
| ERP-02 | blokuje | 1 445 | dokument × płatność | #3 |
| ERP-04 | blokuje | 1 445 | dokument | #25 |
| ERP-05 | blokuje | 1 445 | dokument | #32 |
| ERP-11 | ostrzega | 1 408 | faktura | #23 |
| ERP-13 | blokuje | 1 | dzień eksportu | — |
| ERP-14 | ostrzega | 1 | miesiąc | — |
| ECOM-01 | blokuje | 7 689 | zamówienie | — |
| ECOM-02 | blokuje | 7 689 | zamówienie | #25 |
| ECOM-03 | blokuje | 7 689 | zamówienie | #30 |
| ECOM-04 | blokuje | 440 | zamówienie w EUR | #13, #33 |
| ECOM-09 | blokuje | 8 474 | obciążenie | #17 |
| ECOM-11 | blokuje | 30 | dzień | #17 |
| ECOM-12 | ostrzega | 30 | dzień | — |
