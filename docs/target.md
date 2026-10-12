# Zmienna celu: odejdzie_90d

Cel modelu: wskazać biura, które odejdą w ciągu 90 dni. Tabela `snapshoty` w `kawosz.duckdb` (SQL:
[`api/api/ai/features/snapshoty.sql`](../api/api/ai/features/snapshoty.sql)) ma jeden wiersz na biuro z aktywną umową × 1. dzień
miesiąca, od 2024-01-01 do 2026-06-01. Ma 30 snapszotów, **41 190 wierszy**, 1 873 biura i **1 441 jedynek
(3,50%)**. Kolumny: `data_snapszotu`, `id_biura`, `odejdzie_90d`.

## 1. Jak działają umowy w CRM

- Umowa jest roczna i odnawia się w rocznicę startu. Wszystkie 3 342 wpisy `odnowienie` wypadają dokładnie w dniu
  i miesiącu `data_startu`.
- **Wypowiedzenie** kończy umowę z końcem następnego miesiąca. Dotyczy to wszystkich 261 wypowiedzeń: 241 biur
  ma status `zakończony`, a 20 `w wypowiedzeniu`. Żadne wypowiedzenie nie zostało cofnięte.
- **Brak odnowienia**: 276 biur ma status `zakończony` bez wypowiedzenia. Ich `data_konca_umowy` to zawsze dzień przed
  rocznicą startu (275 dokładnie, a 1 to start 29 lutego).
- `crm_umowy_historia` zawiera zdarzenia dopiero od 2024-01-01 (poza `start`). Biura zakończone przed 2024 nie
  występują w `crm_biura`.
- **Anomalia:** 51 biur ma wpis `odnowienie` *po* wypowiedzeniu, a mimo to umowa skończyła się zgodnie z
  wypowiedzeniem. Traktuję to jako automatyczny wpis systemu i go pomijam.

## 2. Definicja przyjęta w tabeli

| Element | Definicja |
|---|---|
| Moment snapszotu | początek dnia `data_snapszotu`; znane są tylko zdarzenia sprzed tego dnia |
| Aktywna umowa | `data_startu <= data_snapszotu <= data_konca_umowy` |
| Wykluczone | biura, które złożyły wypowiedzenie **przed** snapszotem i są w okresie wypowiedzenia (od 0 do 15 na snapszot, kolumna „w wypowiedzeniu” w sekcji 5). Ich odejście jest już znane, więc nie ma czego przewidywać. |
| Okno | `[data_snapszotu, data_snapszotu + 90 dni)` |
| `odejdzie_90d = 1` | w oknie jest data wypowiedzenia **albo** termin odnowienia bez odnowienia (`data_konca_umowy + 1`) |
| Zawieszenie, downgrade, fuzja, przeprowadzka | **nie są odejściem, tylko cechami** (decyzja 2026-10-12, sekcja 3) |
| Biura `zawieszony` (7 dziś) | są w populacji jako biura z aktywną umową |

Kontrola: każde z 520 odejść z datą w zasięgu okien (2024-01-01 – 2026-08-29: 253 wypowiedzenia i 267 braków
odnowienia) ma co najmniej jedną jedynkę. 433 biura mają 3 jedynki, 55 dwie, a 32 jedną (umowa zaczęła się niedawno
albo odejście wypadło na brzegu zakresu). Okna ostatniego snapszotu kończą się 2026-08-29, a dane sięgają
2026-09-30, więc etykiety nie są ucięte.

## 3. Zdarzenia do decyzji

Bazowy odsetek odejść w 90 dniach to 3,5% na snapszot. Kolumna „odejście ≤90 dni po” mówi, jaka część zdarzeń
(do 2026-06-01) skończyła się wypowiedzeniem lub brakiem odnowienia w ciągu 90 dni. Kolumna „+ jedynek” mówi, ile
wierszy `snapshoty` zmieniłoby etykietę z 0 na 1, gdyby zdarzenie w oknie liczyć jako odejście.

| Zdarzenie | Wpisy (biura) | Co jest w danych | Odejście ≤90 dni po | + jedynek (biur) |
|---|---:|---|---:|---:|
| downgrade | 315 (302) | plan spada o jeden stopień (XL→L 26, L→M 107, M→S 182), cena ok. 0,55–0,6× | 28 z 280 (10,0%) | +792 (284) |
| zawieszenie | 123 (121) | plan i cena bez zmian; **brak zdarzenia „wznowienie”** | 5 z 101 (5,0%) | +316 (114) |
| fuzja | 120 (117) | plan i cena bez zmian, umowa trwa pod tym samym `id_biura`; brak drugiego biura z tym NIP-em | 6 z 106 (5,7%) | +302 (108) |
| przeprowadzka | 166 (156) | plan i cena bez zmian; `crm_biura` ma tylko obecny adres, bez historii | 6 z 138 (4,3%) | +429 (151) |

Obecnie jest 1 441 jedynek. Gdyby doliczyć wszystkie cztery zdarzenia, liczba jedynek wzrosłaby mniej więcej
dwukrotnie (biura z kilkoma zdarzeniami liczą się raz).

### Zawieszenie

Biuro wstrzymuje usługę, ale umowa trwa. Spośród 121 zawieszonych biur 7 ma dziś status `zawieszony`, 84 `aktywny`, a 30
`zakończony`. Brak daty wznowienia oznacza, że nie wiadomo, czy biuro było zawieszone w danym
snapszocie. 1 140 wierszy (98 biur) dotyczy biur, które miały zawieszenie przed snapszotem. Przychód w czasie
zawieszenia mógłby pokazać ERP (faktury za abonament), ale tego nie sprawdzałem.

Możliwości: (a) nie odejście, tylko cecha „było zawieszenie” (stan obecny); (b) odejście w dniu zawieszenia;
(c) biuro zawieszone wyłączyć z populacji do wznowienia, co wymaga ustalenia daty wznowienia, np. z ERP.

### Downgrade

To utrata ok. 40–45% przychodu z abonamentu przy zachowanej umowie. Ma najsilniejszy związek z późniejszym
odejściem: 10% odchodzi w ciągu 90 dni, czyli prawie 3× więcej niż bazowe 3,5%.

Możliwości: (a) nie odejście, tylko cecha i ewentualnie osobny cel „spadek przychodu”; (b) odejście, ale wtedy
model przewiduje „utratę przychodu”, a nie utratę klienta; (c) odejście tylko przy spadku o więcej niż jeden plan,
czego w danych nie ma (zawsze jest to jeden stopień).

### Fuzja

Klient połączył się z inną firmą. W CRM umowa trwa bez zmian, a nowe biuro z tym NIP-em nie powstaje. 6 z 106
fuzji skończyło się odejściem w ciągu 90 dni. Nie wiem, czy fuzja oznacza przejęcie przez firmę z innym
dostawcą kawy (ryzyko), czy wchłonięcie innej firmy przez klienta.

Możliwości: (a) nie odejście, tylko cecha; (b) odejście.

### Przeprowadzka

Biuro zmienia lokalizację przy tej samej umowie. Ma najsłabszy związek z odejściem (4,3% vs 3,5%). Ponieważ CRM
nie trzyma historii adresów, cechy „miasto / kod pocztowy” w snapszocie pokazują adres z dnia eksportu, a nie z dnia
snapszotu.

Możliwości: (a) nie odejście, tylko cecha; (b) odejście tylko przy przeprowadzce poza obsługiwany region, ale
danych o regionie przed przeprowadzką nie ma.

## 4. Decyzje i otwarte pytania

**Decyzja (2026-10-12):** zawieszenie, downgrade, fuzja i przeprowadzka to **cechy, nie odejścia** (wariant (a) w
każdym przypadku). `odejdzie_90d` liczy tylko wypowiedzenie i brak odnowienia. Biura po tych zdarzeniach zostają w
populacji. Cechy z tych zdarzeń wolno liczyć tylko ze zdarzeń sprzed `data_snapszotu`.

Nadal otwarte:

1. **Zawieszenie:** czy jest gdzieś data wznowienia? Bez niej cecha może mówić tylko „było zawieszenie”, a nie
   „jest zawieszone”.
2. **Fuzja:** co oznacza w CRM (klient przejęty czy przejmujący)? Od tego zależy, jak budować cechę.
3. **Biura w okresie wypowiedzenia** wykluczyłem z populacji. Zgoda, czy chcesz je jako wiersze z etykietą 1?
4. **Okno:** przyjąłem `[dzień snapszotu, +90 dni)`, a dla braku odnowienia datą odejścia jest termin odnowienia
   (`data_konca_umowy + 1`). Czy datą „nie odnowi” ma być raczej koniec umowy albo ostatni dzień na
   wypowiedzenie?

## 5. Biura i odejścia w każdym snapszocie

„W wypowiedzeniu” to biura z aktywną umową wykluczone z populacji, bo wypowiedziały umowę przed snapszotem.

| Snapszot | Biura | Odejścia (90 dni) | % | W wypowiedzeniu (wykluczone) |
|---|---:|---:|---:|---:|
| 2024-01-01 | 1 335 | 42 | 3,15 | 0 |
| 2024-02-01 | 1 347 | 46 | 3,41 | 8 |
| 2024-03-01 | 1 348 | 48 | 3,56 | 7 |
| 2024-04-01 | 1 347 | 49 | 3,64 | 8 |
| 2024-05-01 | 1 352 | 50 | 3,70 | 7 |
| 2024-06-01 | 1 355 | 50 | 3,69 | 9 |
| 2024-07-01 | 1 353 | 50 | 3,70 | 6 |
| 2024-08-01 | 1 351 | 46 | 3,40 | 9 |
| 2024-09-01 | 1 350 | 40 | 2,96 | 6 |
| 2024-10-01 | 1 357 | 45 | 3,32 | 7 |
| 2024-11-01 | 1 368 | 48 | 3,51 | 8 |
| 2024-12-01 | 1 377 | 57 | 4,14 | 7 |
| 2025-01-01 | 1 363 | 48 | 3,52 | 10 |
| 2025-02-01 | 1 374 | 46 | 3,35 | 4 |
| 2025-03-01 | 1 368 | 42 | 3,07 | 6 |
| 2025-04-01 | 1 371 | 46 | 3,36 | 4 |
| 2025-05-01 | 1 382 | 54 | 3,91 | 6 |
| 2025-06-01 | 1 382 | 58 | 4,20 | 8 |
| 2025-07-01 | 1 377 | 50 | 3,63 | 8 |
| 2025-08-01 | 1 371 | 41 | 2,99 | 15 |
| 2025-09-01 | 1 379 | 36 | 2,61 | 9 |
| 2025-10-01 | 1 387 | 50 | 3,60 | 5 |
| 2025-11-01 | 1 389 | 50 | 3,60 | 9 |
| 2025-12-01 | 1 403 | 54 | 3,85 | 5 |
| 2026-01-01 | 1 393 | 49 | 3,52 | 13 |
| 2026-02-01 | 1 399 | 48 | 3,43 | 5 |
| 2026-03-01 | 1 397 | 46 | 3,29 | 7 |
| 2026-04-01 | 1 401 | 49 | 3,50 | 10 |
| 2026-05-01 | 1 410 | 52 | 3,69 | 8 |
| 2026-06-01 | 1 404 | 51 | 3,63 | 9 |
| **Razem** | **41 190** | **1 441** | **3,50** | |

Wiersze z sąsiednich snapszotów nakładają się: to samo odejście daje zwykle 3 jedynki w kolejnych miesiącach. Przy
podziale na zbiór uczący i testowy trzeba dzielić po czasie, a nie losowo po wierszach.

## 6. SQL do liczb w tym dokumencie

```sql
-- sekcja 5: biura, odejścia i wykluczone w okresie wypowiedzenia
WITH wyp AS (
    SELECT h.id_biura, h.data_zdarzenia AS dw, b.data_konca_umowy
    FROM crm_umowy_historia h JOIN crm_biura b USING (id_biura)
    WHERE typ = 'wypowiedzenie'
),
s AS (SELECT data_snapszotu AS d, count(*) AS biura, sum(odejdzie_90d) AS odejscia FROM snapshoty GROUP BY 1)
SELECT d, biura, odejscia, round(100.0 * odejscia / biura, 2) AS pct,
       (SELECT count(*) FROM wyp WHERE dw < d AND data_konca_umowy >= d) AS w_wypowiedzeniu
FROM s ORDER BY d;

-- sekcja 3, „+ jedynek”: wiersze z danym zdarzeniem w oknie, które dziś mają 0
SELECT h.typ, count(*) FILTER (WHERE s.odejdzie_90d = 0) AS nowe_jedynki,
       count(DISTINCT s.id_biura) FILTER (WHERE s.odejdzie_90d = 0) AS biura
FROM snapshoty s
JOIN crm_umowy_historia h
  ON h.id_biura = s.id_biura
 AND h.typ IN ('zawieszenie', 'downgrade', 'fuzja', 'przeprowadzka')
 AND h.data_zdarzenia >= s.data_snapszotu
 AND h.data_zdarzenia < s.data_snapszotu + INTERVAL 90 DAY
GROUP BY 1;

-- sekcja 3, „odejście ≤90 dni po”: zdarzenia do 2026-06-01
WITH o AS (
    SELECT b.id_biura, coalesce(w.data_zdarzenia, b.data_konca_umowy + 1) AS d_o
    FROM crm_biura b
    LEFT JOIN crm_umowy_historia w ON w.id_biura = b.id_biura AND w.typ = 'wypowiedzenie'
    WHERE b.status IN ('zakończony', 'w wypowiedzeniu')
)
SELECT h.typ, count(*) AS n,
       count(*) FILTER (WHERE o.d_o BETWEEN h.data_zdarzenia AND h.data_zdarzenia + 89) AS odejscie_90
FROM crm_umowy_historia h LEFT JOIN o USING (id_biura)
WHERE h.typ IN ('zawieszenie', 'downgrade', 'fuzja', 'przeprowadzka') AND h.data_zdarzenia < '2026-06-01'
GROUP BY 1;
```
