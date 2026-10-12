# Opóźnienia danych w źródłach cech churnu

Cechy modelu churnu (`api/api/ai/features/sql/`) liczymy na początek dnia t0. W t0 znamy tylko te rekordy, które do
t0 **dotarły**, a nie wszystkie, które mają datę zdarzenia sprzed t0. Sprawdziłem, z jakim opóźnieniem dociera każde
źródło, i uwzględniłem to w cechach.

**Wynik:**
- Opóźnienie da się zmierzyć tylko w telemetrii, bo tylko ona ma datę dostarczenia. Wynosi **zawsze 2 dni** we
  wszystkich 1 863 414 wierszach.
- ERP, CRM i helpdesk nie mają daty dostarczenia. Eksport z 30.09.2026 jest kompletny do ostatniego dnia, więc z danych
  opóźnienia nie widać. Dla ERP przyjąłem **D+1** z kontraktu dostawy. Dla CRM i helpdesku kontraktu nie ma, więc
  przyjąłem też **D+1**, jak w pozostałych nocnych dostawach. To założenie trzeba potwierdzić z właścicielami systemów.
- Przy D+1 rekord z dnia t0 − 1 dociera dopiero w t0, więc w t0 znamy zdarzenia do **t0 − 2**.
- Najmocniej zmienia się `dni_od_ostatniego_zamowienia`: 34,5% wierszy, AUC samej cechy spada z 0,700 do 0,660.
  69% faktur ERP ma datę ostatniego dnia miesiąca, a snapszoty wypadają 1. dnia. Miesięczna faktura z t0 − 1 dociera
  więc dopiero w t0. Pozostałe cechy zmieniają się w najwyżej 1,7% wierszy.

## 1. Opóźnienie w każdym źródle

| Źródło | Tabele w cechach | Data zdarzenia | Data dostarczenia w danych | Opóźnienie | Podstawa |
|---|---|---|---|---|---|
| IoT | `iot_telemetria` | `data` | `data_dostarczenia` | **2 dni**, zmierzone | wszystkie wiersze: `data_dostarczenia − data = 2` (sekcja 2) |
| ERP | `erp_faktury`, `erp_pozycje`, `erp_platnosci` | `data`, `data_platnosci` | brak | **D+1**, przyjęte | kontrakt `erp_faktury.yaml`: „D+1 do 6:00”. To projekt, który właściciel musi jeszcze zaakceptować |
| CRM | `crm_umowy_historia`, `crm_kontakty_am`, `ankiety_nps` | `data_zdarzenia`, `data`, `data_odpowiedzi` | brak | **D+1**, przyjęte | brak kontraktu; tak jak inne nocne dostawy |
| Helpdesk | `helpdesk_zgloszenia` | `utworzono` | brak | **D+1**, przyjęte | brak kontraktu; tak jak inne nocne dostawy |
| CRM, stan bieżący | `crm_biura`, `iot_ekspresy` | brak | brak | nie dotyczy | migawka z dnia eksportu bez historii (sekcja 7) |

POS i e-commerce nie wchodzą do cech. Mają kontrakty D+1 do 6:00, a POS zapisuje czas dostawy pliku w
`pos_pliki.czas_dostawy`. W `kawosz.duckdb` ta kolumna jest pusta (22 844 pliki), bo baza powstała z archiwum, a nie
z nocnych dostaw.

## 2. Telemetria: zmierzone opóźnienie

```sql
SELECT data_dostarczenia - data AS opoznienie, count(*), min(data), max(data)
FROM iot_telemetria GROUP BY 1;
```

| Opóźnienie (dni) | Wiersze | Pierwszy dzień pomiaru | Ostatni dzień pomiaru |
|---:|---:|---|---|
| 2 | 1 863 414 | 2024-01-01 | 2026-09-30 |

Innych opóźnień nie ma i żaden wiersz nie ma pustej daty dostarczenia. 3 750 wierszy z 29 i 30.09 ma datę
dostarczenia 1 i 2.10, czyli po dniu eksportu. W rzeczywistości nie mogłyby się znaleźć w eksporcie. Cech to nie
dotyczy, bo ostatnie t0 to 2026-06-01.

## 3. ERP, CRM i helpdesk: czy końcówka eksportu jest niepełna

Gdyby rekordy docierały z opóźnieniem dłuższym niż dzień eksportu, w ostatnich dniach przed 30.09 brakowałoby ich.
Porównuję średnią dzienną liczbę rekordów z trzech ostatnich dni września (pon.–śr.) z tymi samymi dniami na końcu
lipca i sierpnia. Zestawienie z poprzednimi miesiącami jest potrzebne, bo faktury i płatności mają cykl miesięczny.

| Tabela (data zdarzenia) | 29–31.07 | 29–31.08 (sob.–pon.) | 28–30.09 |
|---|---:|---:|---:|
| `crm_umowy_historia` (`data_zdarzenia`) | 4,7 | 5,7 | 15,7 |
| `crm_kontakty_am` (`data`) | 15,7 | 15,3 | 31,0 |
| `helpdesk_zgloszenia` (`utworzono`) | 30,0 | 16,0 | 29,7 |
| `erp_faktury` (`data`) | 468,3 | 463,7 | 468,0 |
| `erp_platnosci` (`data_platnosci`) | 1,0 | 1,0 | 5,7 |
| `iot_telemetria` (`data`) | 1 887,0 | 1 868,0 | 1 875,0 |

Końcówka września nie jest uboższa od poprzednich miesięcy. Eksport jest pełnym zrzutem systemów, a nie strumieniem
dostaw, więc nie mówi nic o opóźnieniu na produkcji. Opóźnienie produkcyjne pochodzi z kontraktu (ERP) albo z
założenia (CRM, helpdesk).

## 4. Ankiety NPS: wysyłka a odpowiedź

Ankiety wychodzą raz na kwartał (ostatnio 11.08.2026, 1 375 ankiet). Odpowiedź przychodzi 1–21 dni po wysyłce
(mediana 2, 90. percentyl 6 dni). Na 14 936 ankiet odpowiedziało 8 628, a nieodpowiedziana ankieta ma pusty wynik.

Ankieta liczy się więc **od dnia odpowiedzi**, nie wysyłki. Dopóki biuro nie odpowiedziało, nie ma nowego wyniku, a
`nps_ostatni` zostaje przy poprzedniej odpowiedzi. Na dzień odpowiedzi nakłada się jeszcze opóźnienie CRM, D+1.

## 5. Jak opóźnienie wchodzi do cech

Zasada: rekord jest znany w t0, gdy dotarł przed początkiem dnia t0, czyli `data zdarzenia + opóźnienie < t0`.
Ostatni znany dzień zdarzeń to `znane_do = t0 − 1 − opóźnienie`.

| Źródło | Warunek w SQL | Ostatni znany dzień |
|---|---|---|
| IoT | `data_dostarczenia < t0`, okna liczone od t0 − 3 | t0 − 3 |
| ERP, CRM, helpdesk | `data <= znane_do`, gdzie `znane_do = t0 − 2` | t0 − 2 |

- **Okna** (np. `kontakty_am_90d`, `awarie_60d`, `sr_opoznienie_platnosci`) obejmują N ostatnich *znanych* dni:
  `[znane_do − N + 1, znane_do]`. Mają więc pełną długość, tak jak okna telemetrii.
- **Stany zmienne w czasie** (umowa, NPS) to ostatni znany stan: `ASOF LEFT JOIN` po biurze z warunkiem
  `znane_do >= data_zdarzenia` (umowa) albo `znane_do >= data_odpowiedzi` (NPS). ASOF JOIN dołącza najwyżej jeden
  wiersz, ale przy dwóch wierszach z tego samego dnia nie określa, który. Dlatego zdarzenia umowy są najpierw
  zredukowane do jednego na biuro i dzień: wygrywa downgrade (2 takie dni w danych, downgrade i odnowienie). Dwóch
  odpowiedzi NPS biura z jednego dnia w danych nie ma.
- **Odstęp od zdarzenia** (`dni_od_ostatniego_zamowienia`) liczymy od t0, ale tylko do znanej faktury.
- **`cena_mies`** jest pusta, gdy ostatnie znane zdarzenie jest starsze niż 366 dni przed t0, tak jak dotąd.

Opóźnienie jest zapisane w każdym pliku jako `CAST($t0 AS DATE) - 2 AS znane_do`. Zmiana założenia dla źródła to
zmiana tej stałej w jego plikach: CRM w `umowa.sql` i `relacja.sql`, helpdesk w `serwis.sql`, ERP w `zamowienia.sql`
i `platnosci.sql`. Granice sprawdzają testy `api/tests/ai/features/test_build.py`. Rekord z t0 − 1 nie zmienia cech,
a rekord z t0 − 2 je zmienia.

## 6. Wpływ na cechy

Porównanie z poprzednią wersją bez opóźnień (`cechy_snapszotu.sql`, wszystkie zdarzenia z dat < t0) na 41 190
wierszach `snapshoty`. Każda cecha pochodzi z jednego źródła, więc zmiana pokazuje wpływ opóźnienia tego źródła.
Kontrola: te same pliki z opóźnieniem 0 (`znane_do = t0 − 1`) dają co do wartości wynik `cechy_snapszotu.sql`, także
w brakach. Przejście na ASOF JOIN nie zmienia więc logiki, a różnice w tabeli wynikają wyłącznie z opóźnień.
AUC samej cechy liczę na wszystkich wierszach, brak zastępuję medianą i podaję `max(AUC, 1 − AUC)`, jak w
`docs/przecieki.md`.

| Cecha | Źródło | Zmienione wiersze | Braki przed → po | AUC samej cechy przed → po |
|---|---|---:|---:|---:|
| `dni_od_ostatniego_zamowienia` | ERP | 14 204 (34,5%) | 5 172 → 6 705 | 0,700 → 0,660 |
| `kontakty_am_90d` | CRM | 685 (1,7%) | 0 → 0 | 0,515 → 0,514 |
| `awarie_60d` | helpdesk | 360 (0,9%) | 0 → 0 | 0,540 → 0,541 |
| `cena_mies` | CRM | 129 (0,3%) | 7 033 → 7 094 | 0,536 → 0,535 |
| `sr_opoznienie_platnosci` | ERP | 56 (0,1%) | 6 113 → 6 115 | 0,587 → 0,587 |
| `plan` | CRM | 26 (0,1%) | 14 → 32 | — |
| `nps_ostatni` | CRM | 1 (0,0%) | 8 643 → 8 643 | 0,567 → 0,567 |
| telemetria, `staz_mies`, `dni_do_rocznicy`, firmografia, `am_id` | — | 0 | bez zmian | bez zmian |

`dni_od_ostatniego_zamowienia` zmienia się, bo faktury ERP wystawia się głównie na koniec miesiąca: 31 955 z 46 162
faktur (69%) ma datę ostatniego dnia miesiąca. Snapszot przypada 1. dnia, więc faktura z poprzedniego dnia jeszcze nie
dotarła. Wszystkie 14 204 zmienione wiersze miały wcześniej wartość 1, czyli fakturę z t0 − 1. W 12 671 z nich cecha
rośnie do poprzedniej znanej faktury, o 28–820 dni (mediana 33). Pozostałe 1 533 dostają brak, bo była to pierwsza
faktura z kawą. Spadek AUC z 0,700 do 0,660 to sygnał, którego w t0 na produkcji by nie było.

Ten wynik zależy od chwili liczenia cech. Gdyby wynik modelu liczyć 1. dnia miesiąca po 6:00, po dostawie ERP, faktura
z t0 − 1 byłaby znana. Wtedy ERP miałby `znane_do = t0 − 1`. Obecna umowa „stan na początek dnia t0” jest
ostrożniejsza.

## 7. Czego opóźnienie nie obejmuje i otwarte pytania

- **Populacja** (kto jest w t0 klientem) dalej liczy wypowiedzenia złożone przed t0, także w t0 − 1, choć przy D+1
  dotrą dopiero w t0. To definicja zmiennej celu w `snapshoty` (`docs/target.md`), a nie cecha. `build.py` wymaga
  zgodności z `snapshoty`. Na produkcji biuro, które złożyło wypowiedzenie wczoraj, dostanie jeszcze wynik modelu.
- **`crm_biura` i `iot_ekspresy`** to migawki z dnia eksportu bez historii, więc opóźnienia nie da się do nich
  zastosować: `miasto`, `branza`, `liczba_pracownikow`, `am_id`, przypisanie ekspresu do biura.
- **Nocne zadanie** (`api/api/inngest_app.py`) startuje o 3:00 i przetwarza dostawę za poprzedni dzień, a kontrakt
  ERP pozwala dostarczyć ją do 6:00. Dostawa w terminie, ale po 3:00, nie zostanie wczytana tej nocy, a następna noc
  przetwarza już kolejny dzień. Bez ręcznego ponowienia nie trafi do bazy wcale. Do ustalenia z zespołem danych.
- **Pytania do właścicieli systemów:** jak i kiedy dane CRM (umowy, kontakty, ankiety) i helpdesku trafiają do
  hurtowni? Czy właściciel ERP akceptuje termin D+1 do 6:00?
- Model `v2_bez_przeciekow` uczono na cechach bez opóźnień (`cechy_snapszotu.sql`). Nie przeuczałem go, więc jego AUC
  nie uwzględnia tej zmiany.
