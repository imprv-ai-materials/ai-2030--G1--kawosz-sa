-- Cechy modelu churnu dla każdego wiersza snapshoty, liczone na stan z początku dnia d = data_snapszotu:
-- tylko z rekordów, które istniały przed d. Zastępują cechy agencji (docs/przecieki.md, sekcje 6–8).
--
-- Usunięte, bo powstają dopiero po wypowiedzeniu: dni_do_konca_umowy, status_crm, zgloszenia_odbior_ekspresu,
-- rabat_retencyjny_max. miasto_te nie jest liczone tutaj: to kodowanie etykietą, więc uczy się go model, tylko na
-- zbiorze uczącym (kodowanie_celu.py).
--
-- dni_do_rocznicy: dni od d do najbliższej rocznicy data_startu (>= d). Umowa odnawia się albo kończy w rocznicę
--   (docs/target.md); crm_biura.data_konca_umowy to stan z dnia eksportu, po wypowiedzeniu albo odnowieniach.
-- plan, cena_mies: z ostatniego zdarzenia crm_umowy_historia przed d (każde zdarzenie niesie plan i cenę).
--   Historia przed 2024 ma tylko 'start', a odnowienie co roku zmienia cenę, więc cena jest znana tylko wtedy, gdy
--   ostatnie zdarzenie jest z ostatnich 366 dni. Dwa zdarzenia jednego dnia: wygrywa downgrade.
-- miasto, branza, liczba_pracownikow, am_id: z crm_biura, czyli stan z dnia eksportu. Historii nie ma, a cechy nie
--   rozdzielają klas (AUC 0,48–0,54, docs/przecieki.md, sekcja 2).
-- zaparzenia_30d, bledy_60d: suma ze wszystkich ekspresów biura z 30 / 60 ostatnich znanych dni. Telemetria
--   dociera 2 dni po dniu pomiaru, więc w dniu d ostatni znany dzień to d − 3: okna [d − 32, d − 3] i [d − 62, d − 3].
-- trend_zaparzen: zaparzenia_30d / zaparzenia z poprzednich 30 dni [d − 62, d − 33]; brak, gdy mianownik = 0.
-- awarie_60d: zgłoszenia helpdesku 'awaria' utworzone w [d − 60, d).
-- kontakty_am_90d: kontakty AM w [d − 90, d).
-- nps_ostatni: wynik ostatniej odpowiedzi na ankietę NPS sprzed d.
-- dni_od_ostatniego_zamowienia: d − data ostatniej faktury sprzed d z pozycją kawy (indeks '10.*'). Kontrahenta
--   łączymy z biurem przez mapa_kontrahentow, bo to samo biuro bywa w ERP pod kilkoma ID.
-- sr_opoznienie_platnosci: średnio (data płatności − data faktury − 14) dla faktur zapłaconych w [d − 90, d).
--   14 dni to mediana czasu zapłaty w ERP; termin nie jest zapisany.

WITH s AS (
    SELECT
        s.id_biura,
        s.data_snapszotu AS d,
        b.data_startu,
        date_diff('year', b.data_startu, s.data_snapszotu) AS lata
    FROM snapshoty s
    JOIN crm_biura b USING (id_biura)
),
rocznice AS (
    SELECT
        id_biura,
        d,
        CASE WHEN CAST(data_startu + to_years(lata) AS DATE) >= d
             THEN CAST(data_startu + to_years(lata) AS DATE)
             ELSE CAST(data_startu + to_years(lata + 1) AS DATE) END AS rocznica
    FROM s
),
umowa AS (
    SELECT s.id_biura, s.d, u.plan, u.data_zdarzenia, u.cena
    FROM s
    JOIN crm_umowy_historia u ON u.id_biura = s.id_biura AND u.data_zdarzenia < s.d
    QUALIFY row_number() OVER (
        PARTITION BY s.id_biura, s.d ORDER BY u.data_zdarzenia DESC, u.typ = 'downgrade' DESC, u.typ
    ) = 1
),
telemetria AS (
    SELECT
        s.id_biura,
        s.d,
        sum(t.zaparzenia) FILTER (WHERE t.data >= s.d - 32) AS zaparzenia_30d,
        sum(t.zaparzenia) FILTER (WHERE t.data < s.d - 32) AS zaparzenia_poprzednie_30d,
        sum(t.bledy) AS bledy_60d
    FROM s
    JOIN iot_ekspresy e ON e.id_biura = s.id_biura
    JOIN iot_telemetria t
      ON t.id_ekspresu = e.id_ekspresu
     AND t.data BETWEEN s.d - 62 AND s.d - 3
     AND t.data_dostarczenia < s.d
    GROUP BY s.id_biura, s.d
),
awarie AS (
    SELECT s.id_biura, s.d, count(*) AS awarie_60d
    FROM s
    JOIN helpdesk_zgloszenia z
      ON z.id_biura = s.id_biura AND z.kategoria = 'awaria'
     AND CAST(z.utworzono AS DATE) >= s.d - 60 AND CAST(z.utworzono AS DATE) < s.d
    GROUP BY s.id_biura, s.d
),
kontakty AS (
    SELECT s.id_biura, s.d, count(*) AS kontakty_am_90d
    FROM s
    JOIN crm_kontakty_am k ON k.id_biura = s.id_biura AND k.data >= s.d - 90 AND k.data < s.d
    GROUP BY s.id_biura, s.d
),
nps AS (
    SELECT s.id_biura, s.d, arg_max(n.wynik, n.data_odpowiedzi) AS nps_ostatni
    FROM s
    JOIN ankiety_nps n ON n.id_biura = s.id_biura AND n.data_odpowiedzi < s.d
    GROUP BY s.id_biura, s.d
),
kontrahent_biura AS (
    SELECT m.id_stary AS id_kontrahenta, CAST(k.id_biura_crm AS BIGINT) AS id_biura
    FROM mapa_kontrahentow m
    JOIN (
        SELECT id_kontrahenta, id_biura_crm FROM erp_kontrahenci
        UNION ALL
        SELECT id_kontrahenta, id_biura_crm FROM erp_kontrahenci_archiwum
    ) k ON k.id_kontrahenta = m.id_nowy
    WHERE k.id_biura_crm IS NOT NULL
),
faktury AS (
    SELECT f.nr_faktury, f.data, kb.id_biura
    FROM erp_faktury f
    JOIN kontrahent_biura kb USING (id_kontrahenta)
    WHERE f.typ = 'faktura'
),
zamowienia_kawy AS (
    SELECT s.id_biura, s.d, s.d - max(f.data) AS dni_od_ostatniego_zamowienia
    FROM s
    JOIN faktury f ON f.id_biura = s.id_biura AND f.data < s.d
    WHERE EXISTS (SELECT 1 FROM erp_pozycje p WHERE p.nr_faktury = f.nr_faktury AND p.indeks LIKE '10.%')
    GROUP BY s.id_biura, s.d
),
platnosci AS (
    SELECT s.id_biura, s.d, avg(p.data_platnosci - f.data - 14) AS sr_opoznienie_platnosci
    FROM s
    JOIN faktury f ON f.id_biura = s.id_biura
    JOIN erp_platnosci p ON p.nr_faktury = f.nr_faktury AND p.data_platnosci >= s.d - 90 AND p.data_platnosci < s.d
    GROUP BY s.id_biura, s.d
)
SELECT
    s.id_biura,
    s.d AS data_snapszotu,
    u.plan,
    CASE WHEN u.data_zdarzenia >= s.d - 366 THEN u.cena END AS cena_mies,
    b.liczba_pracownikow,
    b.branza,
    b.miasto,
    b.am_id,
    (s.d - b.data_startu) / 30.44 AS staz_mies,
    r.rocznica - s.d AS dni_do_rocznicy,
    coalesce(t.zaparzenia_30d, 0) AS zaparzenia_30d,
    t.zaparzenia_30d / nullif(t.zaparzenia_poprzednie_30d, 0) AS trend_zaparzen,
    coalesce(t.bledy_60d, 0) AS bledy_60d,
    coalesce(a.awarie_60d, 0) AS awarie_60d,
    coalesce(k.kontakty_am_90d, 0) AS kontakty_am_90d,
    p.sr_opoznienie_platnosci,
    z.dni_od_ostatniego_zamowienia,
    n.nps_ostatni
FROM s
JOIN crm_biura b USING (id_biura)
JOIN rocznice r USING (id_biura, d)
LEFT JOIN umowa u USING (id_biura, d)
LEFT JOIN telemetria t USING (id_biura, d)
LEFT JOIN awarie a USING (id_biura, d)
LEFT JOIN kontakty k USING (id_biura, d)
LEFT JOIN nps n USING (id_biura, d)
LEFT JOIN zamowienia_kawy z USING (id_biura, d)
LEFT JOIN platnosci p USING (id_biura, d)
ORDER BY s.d, s.id_biura
