# Kontrakt „Paragony POS”: sprawdzenie 2026-01-01 – 2026-09-30 miesiąc po miesiącu

Kontrakt [`pos_paragony.yaml`](../api/api/data_platform/kontrakty/pos_paragony.yaml) w wersji 1.0.0. Właściciel: Operacje lokali (POS), odbiorca: Zespół danych, termin dostawy: D+1 do 6:00 (Europe/Warsaw).

Każdy miesiąc sprawdzono osobno wszystkimi 13 regułami kontraktu na `kawosz.duckdb`. To te same reguły, które działają co noc. Naruszenie reguły blokującej oznacza złamany kontrakt: dane z tych dni nie powinny trafić do raportów. Naruszenie reguły ostrzegającej to ostrzeżenie: dane idą dalej, a właściciel dostaje listę.

Raport wygenerowano 2026-10-12 poleceniem:

```bash
PYTHONPATH=api poetry run python -m api.data_platform.kontrakty.sprawdz pos_paragony --od 2026-01-01 --do 2026-09-30 --raport docs/kontrakt_pos_2026.md
```

## Podsumowanie

- **Kontrakt złamany w 4 z 9 miesięcy:** czerwiec 2026, lipiec 2026, sierpień 2026, wrzesień 2026.
- **Pierwsze złamanie:** 2026-06-01, POS-12, kolumna `kanal`: kolumna spoza kontraktu (w pliku po kolumnie `data_czas`).

| Miesiąc | Wynik | Złamane reguły (blokujące) | Ostrzeżenia (reguły) |
|---|---|---|---|
| styczeń 2026 | zgodny, ostrzeżenia: 3 | — | POS-07, POS-08, POS-09 |
| luty 2026 | zgodny, ostrzeżenia: 3 | — | POS-07, POS-08, POS-09 |
| marzec 2026 | zgodny, ostrzeżenia: 3 | — | POS-07, POS-08, POS-09 |
| kwiecień 2026 | zgodny, ostrzeżenia: 3 | — | POS-07, POS-08, POS-09 |
| maj 2026 | zgodny, ostrzeżenia: 3 | — | POS-07, POS-08, POS-09 |
| czerwiec 2026 | **kontrakt złamany** | POS-12 | POS-07, POS-08, POS-09 |
| lipiec 2026 | **kontrakt złamany** | POS-12 | POS-07, POS-08, POS-09 |
| sierpień 2026 | **kontrakt złamany** | POS-12 | POS-07, POS-08, POS-09 |
| wrzesień 2026 | **kontrakt złamany** | POS-02, POS-03, POS-04, POS-12 | POS-07, POS-08, POS-09, POS-11 |

Rekordy z naruszeniem według reguły i miesiąca (pogrubione: reguła blokująca, „—”: nie było czego sprawdzić):

| Reguła | Poziom | Jednostka | I | II | III | IV | V | VI | VII | VIII | IX |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| POS-01 | blokuje | paragon | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| POS-02 | blokuje | paragon | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **988** |
| POS-03 | blokuje | paragon | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **988** |
| POS-04 | blokuje | lokal × dzień | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **3** |
| POS-05 | blokuje | paragon | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| POS-06 | blokuje | pozycja | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| POS-07 | ostrzega | paragon | 8 | 4 | 6 | 9 | 9 | 4 | 4 | 8 | 14 |
| POS-08 | ostrzega | paragon | 2 | 5 | 16 | 11 | 10 | 5 | 8 | 3 | 3 |
| POS-09 | ostrzega | storno | 110 | 117 | 145 | 142 | 154 | 134 | 126 | 126 | 134 |
| POS-10 | blokuje | lokal × dzień | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| POS-11 | ostrzega | lokal × dzień | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 |
| POS-12 | blokuje | plik × kolumna | 0 | 0 | 0 | 0 | 0 | **720** | **744** | **744** | **723** |
| POS-13 | ostrzega | plik | — | — | — | — | — | — | — | — | — |

## Komunikaty miesiąc po miesiącu

### Styczeń 2026: zgodny, ostrzeżenia: 3

**POS-07 · ostrzega · kolumna `metoda_platnosci`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-07: „Paragon ma metodę płatności”. Naruszenie: brak wartości. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-05**; w tym miesiącu: 2026-01-05 – 2026-01-30
- Skala w miesiącu: rekordy: 8 (paragon); lokal 9
- Co zrobić: Operacje lokali sprawdzają w lokalu, czym zapłacono (zwykle to kasa po awarii terminala), i uzupełniają metodę w systemie POS. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)

**POS-08 · ostrzega · kolumny `storno`, `kwota_brutto`, `pos_pozycje.ilosc`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-08: „Paragon z ujemną pozycją lub kwotą (zwrot, anulowanie) ma storno = 1, a storno ma ujemną kwotę”. Naruszenie: ujemna ilość lub kwota bez storno = 1. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-22**; w tym miesiącu: 2026-01-22 – 2026-01-28
- Skala w miesiącu: rekordy: 2 (paragon); lokale: 7, 17
- Co zrobić: Operacje lokali przypominają lokalowi, jak w kasie robi się zwrot, i poprawiają flagę storno. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)

**POS-09 · ostrzega · kolumna `nr_paragonu_stornowanego`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-09: „Storno wskazuje numer paragonu, który stornuje”. Naruszenie: brak kolumny nr_paragonu_stornowanego. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-02**; w tym miesiącu: 2026-01-02 – 2026-01-31
- Skala w miesiącu: rekordy: 110 (storno); pliki: 105; lokale: 23
- Co zrobić: Operacje lokali zamawiają u dostawcy POS kolumnę nr_paragonu_stornowanego na końcu pliku. Kontrakt już ją przewiduje, więc nie trzeba nowej wersji. Do tego czasu storna nie da się powiązać z paragonem, który anuluje. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)


### Luty 2026: zgodny, ostrzeżenia: 3

**POS-07 · ostrzega · kolumna `metoda_platnosci`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-07: „Paragon ma metodę płatności”. Naruszenie: brak wartości. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-05** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-02-08 – 2026-02-23
- Skala w miesiącu: rekordy: 4 (paragon); lokal 9
- Co zrobić: Operacje lokali sprawdzają w lokalu, czym zapłacono (zwykle to kasa po awarii terminala), i uzupełniają metodę w systemie POS. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)

**POS-08 · ostrzega · kolumny `storno`, `kwota_brutto`, `pos_pozycje.ilosc`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-08: „Paragon z ujemną pozycją lub kwotą (zwrot, anulowanie) ma storno = 1, a storno ma ujemną kwotę”. Naruszenie: ujemna ilość lub kwota bez storno = 1. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-22** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-02-04 – 2026-02-28
- Skala w miesiącu: rekordy: 5 (paragon); lokale: 3, 6, 14, 17, 23
- Co zrobić: Operacje lokali przypominają lokalowi, jak w kasie robi się zwrot, i poprawiają flagę storno. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)

**POS-09 · ostrzega · kolumna `nr_paragonu_stornowanego`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-09: „Storno wskazuje numer paragonu, który stornuje”. Naruszenie: brak kolumny nr_paragonu_stornowanego. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-02** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-02-01 – 2026-02-28
- Skala w miesiącu: rekordy: 117 (storno); pliki: 109; lokale: 24
- Co zrobić: Operacje lokali zamawiają u dostawcy POS kolumnę nr_paragonu_stornowanego na końcu pliku. Kontrakt już ją przewiduje, więc nie trzeba nowej wersji. Do tego czasu storna nie da się powiązać z paragonem, który anuluje. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)


### Marzec 2026: zgodny, ostrzeżenia: 3

**POS-07 · ostrzega · kolumna `metoda_platnosci`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-07: „Paragon ma metodę płatności”. Naruszenie: brak wartości. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-05** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-03-03 – 2026-03-28
- Skala w miesiącu: rekordy: 6 (paragon); lokal 9
- Co zrobić: Operacje lokali sprawdzają w lokalu, czym zapłacono (zwykle to kasa po awarii terminala), i uzupełniają metodę w systemie POS. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)

**POS-08 · ostrzega · kolumny `storno`, `kwota_brutto`, `pos_pozycje.ilosc`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-08: „Paragon z ujemną pozycją lub kwotą (zwrot, anulowanie) ma storno = 1, a storno ma ujemną kwotę”. Naruszenie: ujemna ilość lub kwota bez storno = 1. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-22** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-03-01 – 2026-03-31
- Skala w miesiącu: rekordy: 16 (paragon); lokale: 8
- Co zrobić: Operacje lokali przypominają lokalowi, jak w kasie robi się zwrot, i poprawiają flagę storno. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)

**POS-09 · ostrzega · kolumna `nr_paragonu_stornowanego`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-09: „Storno wskazuje numer paragonu, który stornuje”. Naruszenie: brak kolumny nr_paragonu_stornowanego. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-02** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-03-01 – 2026-03-31
- Skala w miesiącu: rekordy: 145 (storno); pliki: 123; lokale: 24
- Co zrobić: Operacje lokali zamawiają u dostawcy POS kolumnę nr_paragonu_stornowanego na końcu pliku. Kontrakt już ją przewiduje, więc nie trzeba nowej wersji. Do tego czasu storna nie da się powiązać z paragonem, który anuluje. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)


### Kwiecień 2026: zgodny, ostrzeżenia: 3

**POS-07 · ostrzega · kolumna `metoda_platnosci`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-07: „Paragon ma metodę płatności”. Naruszenie: brak wartości. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-05** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-04-01 – 2026-04-30
- Skala w miesiącu: rekordy: 9 (paragon); lokal 9
- Co zrobić: Operacje lokali sprawdzają w lokalu, czym zapłacono (zwykle to kasa po awarii terminala), i uzupełniają metodę w systemie POS. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)

**POS-08 · ostrzega · kolumny `storno`, `kwota_brutto`, `pos_pozycje.ilosc`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-08: „Paragon z ujemną pozycją lub kwotą (zwrot, anulowanie) ma storno = 1, a storno ma ujemną kwotę”. Naruszenie: ujemna ilość lub kwota bez storno = 1. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-22** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-04-02 – 2026-04-29
- Skala w miesiącu: rekordy: 11 (paragon); lokale: 8
- Co zrobić: Operacje lokali przypominają lokalowi, jak w kasie robi się zwrot, i poprawiają flagę storno. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)

**POS-09 · ostrzega · kolumna `nr_paragonu_stornowanego`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-09: „Storno wskazuje numer paragonu, który stornuje”. Naruszenie: brak kolumny nr_paragonu_stornowanego. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-02** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-04-01 – 2026-04-30
- Skala w miesiącu: rekordy: 142 (storno); pliki: 126; lokale: 24
- Co zrobić: Operacje lokali zamawiają u dostawcy POS kolumnę nr_paragonu_stornowanego na końcu pliku. Kontrakt już ją przewiduje, więc nie trzeba nowej wersji. Do tego czasu storna nie da się powiązać z paragonem, który anuluje. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)


### Maj 2026: zgodny, ostrzeżenia: 3

**POS-07 · ostrzega · kolumna `metoda_platnosci`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-07: „Paragon ma metodę płatności”. Naruszenie: brak wartości. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-05** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-05-08 – 2026-05-31
- Skala w miesiącu: rekordy: 9 (paragon); lokal 9
- Co zrobić: Operacje lokali sprawdzają w lokalu, czym zapłacono (zwykle to kasa po awarii terminala), i uzupełniają metodę w systemie POS. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)

**POS-08 · ostrzega · kolumny `storno`, `kwota_brutto`, `pos_pozycje.ilosc`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-08: „Paragon z ujemną pozycją lub kwotą (zwrot, anulowanie) ma storno = 1, a storno ma ujemną kwotę”. Naruszenie: ujemna ilość lub kwota bez storno = 1. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-22** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-05-01 – 2026-05-30
- Skala w miesiącu: rekordy: 10 (paragon); lokale: 8
- Co zrobić: Operacje lokali przypominają lokalowi, jak w kasie robi się zwrot, i poprawiają flagę storno. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)

**POS-09 · ostrzega · kolumna `nr_paragonu_stornowanego`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-09: „Storno wskazuje numer paragonu, który stornuje”. Naruszenie: brak kolumny nr_paragonu_stornowanego. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-02** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-05-01 – 2026-05-31
- Skala w miesiącu: rekordy: 154 (storno); pliki: 131; lokale: 24
- Co zrobić: Operacje lokali zamawiają u dostawcy POS kolumnę nr_paragonu_stornowanego na końcu pliku. Kontrakt już ją przewiduje, więc nie trzeba nowej wersji. Do tego czasu storna nie da się powiązać z paragonem, który anuluje. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)


### Czerwiec 2026: kontrakt złamany

**POS-12 · blokuje · kolumna `kanal`**

Złamany kontrakt „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-12: „Plik z kasy ma kolumny z kontraktu, w kolejności z kontraktu, i żadnych innych”. Naruszenie: kolumna spoza kontraktu (w pliku po kolumnie `data_czas`). Poziom blokuje: dane z tych dni nie trafiają do raportów.

- Od dnia: **2026-06-01**; w tym miesiącu: 2026-06-01 – 2026-06-30
- Skala w miesiącu: rekordy: 720 (plik × kolumna); pliki: 720; lokale: 24
- Co zrobić: Operacje lokali ustalają z dostawcą POS, czy zmiana jest zamierzona. Jeśli tak, zgłaszają ją zespołowi danych: nazwę kolumny, typ, znaczenie, słownik wartości i datę wdrożenia. Zespół danych wydaje nową wersję kontraktu. Jeśli nie, dostawca wraca do układu z kontraktu i wysyła pliki ponownie. Do tego czasu pliki ze zmianą nie trafiają do raportów.
- Odpowiada: Operacje lokali (POS)

**POS-07 · ostrzega · kolumna `metoda_platnosci`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-07: „Paragon ma metodę płatności”. Naruszenie: brak wartości. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-05** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-06-02 – 2026-06-30
- Skala w miesiącu: rekordy: 4 (paragon); lokal 9
- Co zrobić: Operacje lokali sprawdzają w lokalu, czym zapłacono (zwykle to kasa po awarii terminala), i uzupełniają metodę w systemie POS. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)

**POS-08 · ostrzega · kolumny `storno`, `kwota_brutto`, `pos_pozycje.ilosc`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-08: „Paragon z ujemną pozycją lub kwotą (zwrot, anulowanie) ma storno = 1, a storno ma ujemną kwotę”. Naruszenie: ujemna ilość lub kwota bez storno = 1. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-22** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-06-07 – 2026-06-25
- Skala w miesiącu: rekordy: 5 (paragon); lokale: 4, 12, 13, 14, 16
- Co zrobić: Operacje lokali przypominają lokalowi, jak w kasie robi się zwrot, i poprawiają flagę storno. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)

**POS-09 · ostrzega · kolumna `nr_paragonu_stornowanego`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-09: „Storno wskazuje numer paragonu, który stornuje”. Naruszenie: brak kolumny nr_paragonu_stornowanego. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-02** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-06-01 – 2026-06-30
- Skala w miesiącu: rekordy: 134 (storno); pliki: 117; lokale: 24
- Co zrobić: Operacje lokali zamawiają u dostawcy POS kolumnę nr_paragonu_stornowanego na końcu pliku. Kontrakt już ją przewiduje, więc nie trzeba nowej wersji. Do tego czasu storna nie da się powiązać z paragonem, który anuluje. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)


### Lipiec 2026: kontrakt złamany

**POS-12 · blokuje · kolumna `kanal`**

Złamany kontrakt „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-12: „Plik z kasy ma kolumny z kontraktu, w kolejności z kontraktu, i żadnych innych”. Naruszenie: kolumna spoza kontraktu (w pliku po kolumnie `data_czas`). Poziom blokuje: dane z tych dni nie trafiają do raportów.

- Od dnia: **2026-06-01** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-07-01 – 2026-07-31
- Skala w miesiącu: rekordy: 744 (plik × kolumna); pliki: 744; lokale: 24
- Co zrobić: Operacje lokali ustalają z dostawcą POS, czy zmiana jest zamierzona. Jeśli tak, zgłaszają ją zespołowi danych: nazwę kolumny, typ, znaczenie, słownik wartości i datę wdrożenia. Zespół danych wydaje nową wersję kontraktu. Jeśli nie, dostawca wraca do układu z kontraktu i wysyła pliki ponownie. Do tego czasu pliki ze zmianą nie trafiają do raportów.
- Odpowiada: Operacje lokali (POS)

**POS-07 · ostrzega · kolumna `metoda_platnosci`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-07: „Paragon ma metodę płatności”. Naruszenie: brak wartości. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-05** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-07-02 – 2026-07-30
- Skala w miesiącu: rekordy: 4 (paragon); lokal 9
- Co zrobić: Operacje lokali sprawdzają w lokalu, czym zapłacono (zwykle to kasa po awarii terminala), i uzupełniają metodę w systemie POS. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)

**POS-08 · ostrzega · kolumny `storno`, `kwota_brutto`, `pos_pozycje.ilosc`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-08: „Paragon z ujemną pozycją lub kwotą (zwrot, anulowanie) ma storno = 1, a storno ma ujemną kwotę”. Naruszenie: ujemna ilość lub kwota bez storno = 1. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-22** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-07-03 – 2026-07-22
- Skala w miesiącu: rekordy: 8 (paragon); lokale: 7
- Co zrobić: Operacje lokali przypominają lokalowi, jak w kasie robi się zwrot, i poprawiają flagę storno. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)

**POS-09 · ostrzega · kolumna `nr_paragonu_stornowanego`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-09: „Storno wskazuje numer paragonu, który stornuje”. Naruszenie: brak kolumny nr_paragonu_stornowanego. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-02** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-07-01 – 2026-07-31
- Skala w miesiącu: rekordy: 126 (storno); pliki: 118; lokale: 24
- Co zrobić: Operacje lokali zamawiają u dostawcy POS kolumnę nr_paragonu_stornowanego na końcu pliku. Kontrakt już ją przewiduje, więc nie trzeba nowej wersji. Do tego czasu storna nie da się powiązać z paragonem, który anuluje. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)


### Sierpień 2026: kontrakt złamany

**POS-12 · blokuje · kolumna `kanal`**

Złamany kontrakt „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-12: „Plik z kasy ma kolumny z kontraktu, w kolejności z kontraktu, i żadnych innych”. Naruszenie: kolumna spoza kontraktu (w pliku po kolumnie `data_czas`). Poziom blokuje: dane z tych dni nie trafiają do raportów.

- Od dnia: **2026-06-01** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-08-01 – 2026-08-31
- Skala w miesiącu: rekordy: 744 (plik × kolumna); pliki: 744; lokale: 24
- Co zrobić: Operacje lokali ustalają z dostawcą POS, czy zmiana jest zamierzona. Jeśli tak, zgłaszają ją zespołowi danych: nazwę kolumny, typ, znaczenie, słownik wartości i datę wdrożenia. Zespół danych wydaje nową wersję kontraktu. Jeśli nie, dostawca wraca do układu z kontraktu i wysyła pliki ponownie. Do tego czasu pliki ze zmianą nie trafiają do raportów.
- Odpowiada: Operacje lokali (POS)

**POS-07 · ostrzega · kolumna `metoda_platnosci`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-07: „Paragon ma metodę płatności”. Naruszenie: brak wartości. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-05** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-08-05 – 2026-08-28
- Skala w miesiącu: rekordy: 8 (paragon); lokal 9
- Co zrobić: Operacje lokali sprawdzają w lokalu, czym zapłacono (zwykle to kasa po awarii terminala), i uzupełniają metodę w systemie POS. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)

**POS-08 · ostrzega · kolumny `storno`, `kwota_brutto`, `pos_pozycje.ilosc`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-08: „Paragon z ujemną pozycją lub kwotą (zwrot, anulowanie) ma storno = 1, a storno ma ujemną kwotę”. Naruszenie: ujemna ilość lub kwota bez storno = 1. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-22** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-08-06 – 2026-08-27
- Skala w miesiącu: rekordy: 3 (paragon); lokale: 4, 12, 22
- Co zrobić: Operacje lokali przypominają lokalowi, jak w kasie robi się zwrot, i poprawiają flagę storno. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)

**POS-09 · ostrzega · kolumna `nr_paragonu_stornowanego`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-09: „Storno wskazuje numer paragonu, który stornuje”. Naruszenie: brak kolumny nr_paragonu_stornowanego. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-02** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-08-01 – 2026-08-31
- Skala w miesiącu: rekordy: 126 (storno); pliki: 116; lokale: 24
- Co zrobić: Operacje lokali zamawiają u dostawcy POS kolumnę nr_paragonu_stornowanego na końcu pliku. Kontrakt już ją przewiduje, więc nie trzeba nowej wersji. Do tego czasu storna nie da się powiązać z paragonem, który anuluje. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)


### Wrzesień 2026: kontrakt złamany

**POS-02 · blokuje · kolumny `lokal`, `nr_paragonu`**

Złamany kontrakt „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-02: „Paragon (lokal, nr_paragonu) występuje w danych raz”. Naruszenie: powtórzony klucz (lokal, nr_paragonu). Poziom blokuje: dane z tych dni nie trafiają do raportów.

- Od dnia: **2026-09-11**; w tym miesiącu: 2026-09-11 – 2026-09-13
- Skala w miesiącu: rekordy: 988 (paragon); pliki: 3; lokal 17
- Co zrobić: Ten sam paragon przyszedł dwa razy, zwykle jako kopia pliku z dopiskiem w nazwie, np. „ (1)”. Zespół danych usuwa kopię z wsadu i ładuje dzień ponownie. Operacje lokali ustalają z dostawcą POS, dlaczego kasa wysłała plik drugi raz.
- Odpowiada: Zespół danych

**POS-03 · blokuje · nazwa pliku**

Złamany kontrakt „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-03: „Nazwa pliku, numer paragonu i czas są spójne; numeracja w dniu rośnie razem z czasem”. Naruszenie: plik = pos_paragony_{lokal}_{dzień}.csv. Poziom blokuje: dane z tych dni nie trafiają do raportów.

- Od dnia: **2026-09-11**; w tym miesiącu: 2026-09-11 – 2026-09-13
- Skala w miesiącu: rekordy: 988 (paragon); pliki: 3; lokal 17
- Co zrobić: Kopię pliku z dopiskiem w nazwie zespół danych usuwa z wsadu. Paragon z numerem albo datą spoza kolejności Operacje lokali wyjaśniają z lokalem: czy to ręczna korekta, czy zła data na kasie.
- Odpowiada: Zespół danych

**POS-04 · blokuje · kolumny `kwota_brutto`, `pos_pozycje.ilosc`, `pos_pozycje.cena_brutto`**

Złamany kontrakt „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-04: „Suma nagłówków paragonów lokalu w dniu równa się sumie ich pozycji”. Naruszenie: liczba paragonów = liczba paragonów w pozycjach; Σ kwota_brutto = Σ ilosc × cena_brutto. Poziom blokuje: dane z tych dni nie trafiają do raportów.

- Od dnia: **2026-09-11**; w tym miesiącu: 2026-09-11 – 2026-09-13
- Skala w miesiącu: rekordy: 3 (lokal × dzień); lokal 17
- Co zrobić: Przychód lokalu z tego dnia jest niepewny. Zespół danych sprawdza, czy to zdublowany plik (POS-02) albo brak pozycji. Jeśli nie, prosi dostawcę POS o ponowny eksport dnia.
- Odpowiada: Zespół danych

**POS-12 · blokuje · kolumna `kanal`**

Złamany kontrakt „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-12: „Plik z kasy ma kolumny z kontraktu, w kolejności z kontraktu, i żadnych innych”. Naruszenie: kolumna spoza kontraktu (w pliku po kolumnie `data_czas`). Poziom blokuje: dane z tych dni nie trafiają do raportów.

- Od dnia: **2026-06-01** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-09-01 – 2026-09-30
- Skala w miesiącu: rekordy: 723 (plik × kolumna); pliki: 723; lokale: 24
- Co zrobić: Operacje lokali ustalają z dostawcą POS, czy zmiana jest zamierzona. Jeśli tak, zgłaszają ją zespołowi danych: nazwę kolumny, typ, znaczenie, słownik wartości i datę wdrożenia. Zespół danych wydaje nową wersję kontraktu. Jeśli nie, dostawca wraca do układu z kontraktu i wysyła pliki ponownie. Do tego czasu pliki ze zmianą nie trafiają do raportów.
- Odpowiada: Operacje lokali (POS)

**POS-07 · ostrzega · kolumna `metoda_platnosci`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-07: „Paragon ma metodę płatności”. Naruszenie: brak wartości. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-05** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-09-03 – 2026-09-28
- Skala w miesiącu: rekordy: 14 (paragon); lokal 9
- Co zrobić: Operacje lokali sprawdzają w lokalu, czym zapłacono (zwykle to kasa po awarii terminala), i uzupełniają metodę w systemie POS. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)

**POS-08 · ostrzega · kolumny `storno`, `kwota_brutto`, `pos_pozycje.ilosc`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-08: „Paragon z ujemną pozycją lub kwotą (zwrot, anulowanie) ma storno = 1, a storno ma ujemną kwotę”. Naruszenie: ujemna ilość lub kwota bez storno = 1. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-22** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-09-10 – 2026-09-30
- Skala w miesiącu: rekordy: 3 (paragon); lokale: 6, 14, 17
- Co zrobić: Operacje lokali przypominają lokalowi, jak w kasie robi się zwrot, i poprawiają flagę storno. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)

**POS-09 · ostrzega · kolumna `nr_paragonu_stornowanego`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-09: „Storno wskazuje numer paragonu, który stornuje”. Naruszenie: brak kolumny nr_paragonu_stornowanego. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-01-02** (pierwszy raz w sprawdzanym okresie); w tym miesiącu: 2026-09-01 – 2026-09-30
- Skala w miesiącu: rekordy: 134 (storno); pliki: 124; lokale: 24
- Co zrobić: Operacje lokali zamawiają u dostawcy POS kolumnę nr_paragonu_stornowanego na końcu pliku. Kontrakt już ją przewiduje, więc nie trzeba nowej wersji. Do tego czasu storna nie da się powiązać z paragonem, który anuluje. Dane idą dalej.
- Odpowiada: Operacje lokali (POS)

**POS-11 · ostrzega · kolumny `lokal`, `nr_paragonu`**

Ostrzeżenie z kontraktu „Paragony POS” (`pos_paragony.yaml`, wersja 1.0.0), reguła POS-11: „Liczba paragonów lokalu w dniu to 0.4–1.8 × mediany z 28 poprzednich dni”. Naruszenie: paragony = 0.4–1.8 × mediana z 28 dni. Poziom ostrzega: dane idą dalej.

- Od dnia: **2026-09-11**; w tym miesiącu: 2026-09-11 – 2026-09-13
- Skala w miesiącu: rekordy: 3 (lokal × dzień); lokal 17
- Co zrobić: Zespół danych sprawdza, czy to zdublowany albo niepełny plik. Jeśli ruch jest prawdziwy (zamknięcie lokalu, wydarzenie), odnotowuje to i niczego nie poprawia.
- Odpowiada: Zespół danych


## Czego nie dało się sprawdzić

- **POS-13** (Plik za dzień D dotarł w terminie dostawy z kontraktu): w żadnym miesiącu nie było czego sprawdzić (plik). Reguła sprawdza tylko pliki ze znanym czasem dostawy. Archiwum ZIP go nie ma: wszystkie pliki mają w nim datę spakowania 30.09.2026 23:59. Termin da się sprawdzić, gdy loader zapisze, kiedy plik dotarł.
