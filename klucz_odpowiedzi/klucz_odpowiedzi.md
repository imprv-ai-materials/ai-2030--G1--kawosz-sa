# Kawosz S.A. — klucz odpowiedzi (NIE dla uczestników)

Ziarno losowania: **2030**. Pełne dane: `klucz_odpowiedzi.json`.

## Przychód netto — wrzesień 2026

| Raport | mln PLN |
|---|---|
| bi | 8.3102 |
| sprzedaz | 8.0600 |
| ksiegowosc | 7.9196 |
| definicja | 7.6912 |

### Most BI → definicja

| Pozycja | Wpływ (mln PLN) |
|---|---|
| VAT w POS i e-commerce | −0.4006 |
| Zwroty i korekty nieodjęte | −0.0902 |
| Fan-out na zdublowanych kontrahentach | −0.0596 |
| Subskrypcje roczne w miesiącu płatności | −0.0498 |
| Zdublowane pliki POS lokalu 17 (3 dni) | −0.0300 |
| Karty podarunkowe przy sprzedaży | −0.0200 |
| Zamówienia testowe | −0.0089 |
| EUR zapisane jako PLN | +0.0300 |
| Granica doby w UTC | +0.0100 |

Pozycje liczone sekwencyjnie w kolejności: vat, pos_duplikaty, eur, utc, zwroty, fanout, subskrypcje, karty, testowe — dzięki temu sumują się dokładnie, a księgowość = BI − VAT − duplikaty POS + EUR + UTC.

- **bi**: Dashboard BI — surowa suma źródeł: ERP (dokumenty typu 'faktura', złączone z kontrahentami po surowym NIP → fan-out), POS kwota_brutto ze wszystkich plików (z duplikatami), e-commerce `brutto` (kwoty EUR traktowane jak PLN, miesiąc wg UTC, z testowymi i zwrotami), subskrypcje w miesiącu płatności (UTC), karty podarunkowe w dniu sprzedaży.
- **sprzedaz**: Raport sprzedaży — te same źródła co BI, „netto” liczone jedną stawką 8% (stawka gastronomiczna) dla POS i e-commerce; bez odjęcia zwrotów, bez deduplikacji (fan-out, duplikaty plików POS).
- **ksiegowosc**: Księgowość — ERP (widok hurtowni z fan-outem po NIP; korekty i zwroty z września nie są jeszcze zaksięgowane na dzień eksportu) + POS netto z pozycji (bez duplikatów plików) + e-commerce netto (EUR po kursie NBP, doba warszawska, z zamówieniami testowymi opłaconymi bramką), subskrypcje nierozłożone (w miesiącu płatności), karty przy sprzedaży.
- **definicja**: Definicja — netto (POS wg stawek z pozycji, e-commerce/karty/subskrypcje 23%), po odjęciu korekt ERP i zwrotów e-commerce, bez fan-outu, subskrypcje roczne rozłożone na 12 miesięcy, karty w dniu realizacji, EUR po kursie NBP z dnia sprzedaży (dzień bez notowania → ostatni wcześniejszy kurs), bez zamówień testowych (notatka zawiera „test” lub e-mail w domenie kawosz.pl), doba Europe/Warsaw.

## Usterki jakości (projekt Fundament)

- Kontrahenci: 1512 wierszy, 112 rozmytych duplikatów (w tym 20 z identycznym NIP → fan-out w hurtowni).
- NIP z 9 cyframi: 15.
- Kartoteka bez kategorii: 24 (6.0%).
- Pozycje POS z ujemną ilością bez storno: 226.
- Paragon-literówka: lokal 5, 2025-03-14, 48 000 zł.
- Faktura na 40 ekspresów: FV/2025/11/00007 (330,885.20 zł netto) — prawdziwa.
- MCAR lokal 9: 276 z 57231 paragonów bez metody płatności.
- MAR e-mail: brak e-maila przy pobraniu 93.3%, przy innych metodach 1.2%.
- Nowa kolumna POS `kanal` od 2026-06-01.
- Zdublowane pliki: pos_paragony.zip: paragony/pos_paragony_17_2026-09-11 (1).csv, pos_paragony.zip: paragony/pos_paragony_17_2026-09-12 (1).csv, pos_paragony.zip: paragony/pos_paragony_17_2026-09-13 (1).csv.
- Zamówienia testowe: 595 (wrzesień 2026: 74); reguła: notatka zawiera 'test' (bez względu na wielkość liter) LUB e-mail w domenie @kawosz.pl.

## Odejścia (projekt Sygnały)

- Migawka 2026-04-01: 1400 biur, 49 odejść (25 wypowiedzeń, 24 braków odnowienia).
- Uczciwy model (regresja logistyczna na cechach znanych w t0, migawki 2024-04…2025-07, kalibracja Platta na 2025-10 i 2026-01): AUC 0.796; próg 0,5 → 7 biur (TP 7); top 60 → TP 21; próg 0,175 → 40 biur (TP 20).
- Reguła AM (do końca umowy < 90 dni i trend 30/90 ≤ 0,7): AUC 0.687 (37 biur, TP 19).
- Model agencji: AUC 0.999 (migawka testowa), 1.000 (losowy podział).
- Przecieki: `status_crm` — stan z dnia eksportu (2026-09-30), a nie z migawki; `plan, cena_mies, dni_do_konca_umowy` — z eksportu CRM (po downgrade'ach i odnowieniach po t0); `zaparzenia_30d` — okno [t0, t0+30) — przyszłość względem migawki; `zgloszenia_odbior_ekspresu` — zgłoszenie powstaje 1–20 dni PO wypowiedzeniu; liczone do dnia eksportu; `rabat_retencyjny_max` — rabat przyznawany dopiero PO wypowiedzeniu; `dni_od_ostatniego_zamowienia` — liczone od daty eksportu zamiast od t0; `miasto_te` — target encoding policzony na całym zbiorze (także migawka testowa).

## Dryf i wizyty (projekt Decyzja)

- Firmware 2026-05-04–2026-05-29: nowy firmware liczy podwójne espresso jako 1 zaparzenie (wcześniej 2); spożycie bez zmian; PSI zaparzenia_30d = 0.327.
- Wizyty retencyjne: średni efekt 28.4% (1 − Σ hazard z wizytą / Σ hazard bez wizyty (wśród odwiedzonych, w bloku 90 dni)).
- NPS (MNAR): odejścia bez odpowiedzi 0.049 vs z odpowiedzią 0.028 (×1.75).

| Grupa | udział biur | mnożnik hazardu po wizycie | wizyty |
|---|---|---|---|
| przekonywalni | 50.6% | 0.1 | 244 |
| pewni | 21.2% | 1.0 | 98 |
| straceni | 15.6% | 1.0 | 80 |
| nie_budzic | 12.6% | 1.75 | 63 |

Grupa każdego biura: `decyzja.wizyty_retencyjne.grupa_biura` w pliku JSON.
