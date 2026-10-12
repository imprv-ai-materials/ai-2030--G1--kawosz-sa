# Macierz wartości: ile daje decyzja o wizycie

Ile zarabiamy albo tracimy na jednym biurze w porównaniu z brakiem działania, zależnie od tego, czy biuro chciało odejść i czy do niego pojechaliśmy. Liczby pochodzą z [`retention_bc/zalozenia.yaml`](../retention_bc/zalozenia.yaml) (warsztat z 2026-10-06):

- **V** = 24 192 zł: wartość utrzymanego biura (marża 1 344 zł/mies. × 18 mies.);
- **C** = 1 260 zł: koszt wizyty (300 zł) plus rabat (10% × 3 200 zł × 3 mies.);
- **s** = 0,30: odsetek biur chcących odejść, które po wizycie zostają (pilotaż: 12 z 40).

## Macierz

| | **Biuro chciało odejść** | **Biuro i tak by zostało** |
|---|---|---|
| **Wizyta** | Trafiona wizyta: s × V − C = 0,30 × 24 192 − 1 260 = **+5 997,60 zł** | Zbędna wizyta: −C = **−1 260 zł** |
| **Bez wizyty** | Pominięte odejście: **0 zł** | Słusznie pominięte biuro: **0 zł** |

## Jak czytać

- **Trafiona wizyta to wartość oczekiwana, nie wynik pojedynczej wizyty.** Biuro zostaje z prawdopodobieństwem s i wtedy daje V − C = +22 932 zł. W pozostałych 70% przypadków odchodzi mimo wizyty i tracimy C = 1 260 zł. Średnio wychodzi +5 997,60 zł.
- **Zero w wierszu „bez wizyty” oznacza zero względem braku działania, a nie brak straty.** Pominięte odejście kosztuje nas utraconą okazję: 5 997,60 zł, które mogła przynieść wizyta.
- **Zbędna wizyta kosztuje pełne C,** bo rabat dostaje praktycznie każde odwiedzone biuro („nie wiemy tego z góry”).
- **Przedział:** przy s z przedziału 0,20–0,40 i V z przedziału 18 816–29 568 zł trafiona wizyta daje od +2 503,20 zł do +10 567,20 zł. Dla C notatki nie podają przedziału.

## Co z tego wynika dla progu

Jeśli model daje biuru prawdopodobieństwo odejścia p, oczekiwany wynik wizyty to p × (s × V − C) + (1 − p) × (−C) = p × s × V − C. Wizyta się opłaca, gdy p > C / (s × V) = 1 260 / 7 257,60 ≈ **0,174**. Przy limicie 60 wizyt na kwartał (budżet z `zalozenia.yaml`) jedziemy do 60 biur z najwyższym p × s × V − C spośród tych, które przekraczają próg.

Pytania otwarte do V, C i s są w `zalozenia.yaml` (pole `otwarte`).
