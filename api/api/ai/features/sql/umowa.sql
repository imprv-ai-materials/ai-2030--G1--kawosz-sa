-- Rodzina „umowa”: plan, cena i wiek umowy biura na początek dnia t0, tylko z rekordów znanych w t0.
-- Parametr $t0 (DATE). Wynik: 1 wiersz na biuro z populacji w t0. Opisy cech: ../katalog.yaml.
--
-- Zastępuje dni_do_konca_umowy i status_crm agencji: oba powstają dopiero po wypowiedzeniu (docs/przecieki.md, 6–7).
-- Opóźnienie CRM: D+1 (docs/opoznienia_danych.md), więc w t0 znane są zdarzenia do znane_do = t0 − 2.
-- plan, cena_mies: ostatni stan umowy znany w t0, czyli ostatnie zdarzenie crm_umowy_historia z dnia <= znane_do
--   (ASOF JOIN; każde zdarzenie niesie plan i cenę). Dwa zdarzenia jednego dnia: wygrywa downgrade. Historia przed
--   2024 ma tylko 'start', a odnowienie co roku zmienia cenę, więc cena jest znana tylko wtedy, gdy to zdarzenie jest
--   z ostatnich 366 dni przed t0.
-- staz_mies: (t0 − data_startu) / 30,44.
-- dni_do_rocznicy: dni od t0 do najbliższej rocznicy data_startu (>= t0). Umowa odnawia się albo kończy w rocznicę
--   (docs/target.md). Start 29.02 → rocznica 28.02 w latach nieprzestępnych.

WITH p AS (SELECT CAST($t0 AS DATE) AS t0, CAST($t0 AS DATE) - 2 AS znane_do),
biura AS (
    -- Populacja w t0, ta sama we wszystkich plikach sql/ i w snapshoty: umowa trwa w t0 i biuro nie złożyło
    -- wypowiedzenia przed t0. data_konca_umowy (stan z eksportu) mówi tu tylko, czy umowa skończyła się przed t0.
    SELECT b.id_biura, p.t0
    FROM crm_biura b, p
    WHERE b.data_startu <= p.t0
      AND b.data_konca_umowy >= p.t0
      AND NOT EXISTS (
          SELECT 1 FROM crm_umowy_historia u
          WHERE u.id_biura = b.id_biura AND u.typ = 'wypowiedzenie' AND u.data_zdarzenia < p.t0
      )
),
start AS (
    SELECT s.id_biura, s.t0, p.znane_do, b.data_startu, date_diff('year', b.data_startu, s.t0) AS lata
    FROM biura s
    JOIN crm_biura b USING (id_biura)
    CROSS JOIN p
),
rocznice AS (
    SELECT
        id_biura,
        CASE WHEN CAST(data_startu + to_years(lata) AS DATE) >= t0
             THEN CAST(data_startu + to_years(lata) AS DATE)
             ELSE CAST(data_startu + to_years(lata + 1) AS DATE) END AS rocznica
    FROM start
),
zdarzenia AS (
    -- jeden stan na biuro i dzień, żeby ASOF JOIN nie wybierał losowo między zdarzeniami z tego samego dnia
    SELECT id_biura, data_zdarzenia, plan, cena
    FROM crm_umowy_historia
    QUALIFY row_number() OVER (PARTITION BY id_biura, data_zdarzenia ORDER BY typ = 'downgrade' DESC, typ) = 1
)
SELECT
    s.id_biura,
    s.t0,
    u.plan,
    CASE WHEN u.data_zdarzenia >= s.t0 - 366 THEN u.cena END AS cena_mies,
    (s.t0 - s.data_startu) / 30.44 AS staz_mies,
    r.rocznica - s.t0 AS dni_do_rocznicy
FROM start s
JOIN rocznice r USING (id_biura)
ASOF LEFT JOIN zdarzenia u ON u.id_biura = s.id_biura AND s.znane_do >= u.data_zdarzenia
