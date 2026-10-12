-- Rodzina „umowa”: plan, cena i wiek umowy biura na początek dnia t0, tylko z rekordów sprzed t0.
-- Parametr $t0 (DATE). Wynik: 1 wiersz na biuro z populacji w t0. Opisy cech: ../katalog.yaml.
--
-- Zastępuje dni_do_konca_umowy i status_crm agencji: oba powstają dopiero po wypowiedzeniu (docs/przecieki.md, 6–7).
-- plan, cena_mies: z ostatniego zdarzenia crm_umowy_historia przed t0 (każde zdarzenie niesie plan i cenę). Historia
--   przed 2024 ma tylko 'start', a odnowienie co roku zmienia cenę, więc cena jest znana tylko wtedy, gdy ostatnie
--   zdarzenie jest z ostatnich 366 dni. Dwa zdarzenia jednego dnia: wygrywa downgrade.
-- staz_mies: (t0 − data_startu) / 30,44.
-- dni_do_rocznicy: dni od t0 do najbliższej rocznicy data_startu (>= t0). Umowa odnawia się albo kończy w rocznicę
--   (docs/target.md). Start 29.02 → rocznica 28.02 w latach nieprzestępnych.

WITH p AS (SELECT CAST($t0 AS DATE) AS t0),
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
    SELECT s.id_biura, s.t0, b.data_startu, date_diff('year', b.data_startu, s.t0) AS lata
    FROM biura s
    JOIN crm_biura b USING (id_biura)
),
rocznice AS (
    SELECT
        id_biura,
        CASE WHEN CAST(data_startu + to_years(lata) AS DATE) >= t0
             THEN CAST(data_startu + to_years(lata) AS DATE)
             ELSE CAST(data_startu + to_years(lata + 1) AS DATE) END AS rocznica
    FROM start
),
umowa AS (
    SELECT s.id_biura, u.plan, u.cena, u.data_zdarzenia
    FROM biura s
    JOIN crm_umowy_historia u ON u.id_biura = s.id_biura AND u.data_zdarzenia < s.t0
    QUALIFY row_number() OVER (
        PARTITION BY s.id_biura ORDER BY u.data_zdarzenia DESC, u.typ = 'downgrade' DESC, u.typ
    ) = 1
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
LEFT JOIN umowa u USING (id_biura)
