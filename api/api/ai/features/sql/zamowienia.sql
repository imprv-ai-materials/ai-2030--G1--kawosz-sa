-- Rodzina „zamówienia”: zamówienia kawy biura w ERP przed dniem t0.
-- Parametr $t0 (DATE). Wynik: 1 wiersz na biuro z populacji w t0. Opisy cech: ../katalog.yaml.
--
-- dni_od_ostatniego_zamowienia: t0 − data ostatniej faktury sprzed t0 z pozycją kawy (indeks '10.*'); korekty się
--   nie liczą. Agencja liczyła do dnia eksportu, a nie do snapszotu (docs/przecieki.md, 6.1). Kontrahenta łączymy
--   z biurem przez mapa_kontrahentow, bo to samo biuro bywa w ERP pod kilkoma ID. Brak, gdy nie ma takiej faktury.

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
    SELECT s.id_biura, s.t0 - max(f.data) AS dni_od_ostatniego_zamowienia
    FROM biura s
    JOIN faktury f ON f.id_biura = s.id_biura AND f.data < s.t0
    WHERE EXISTS (SELECT 1 FROM erp_pozycje p WHERE p.nr_faktury = f.nr_faktury AND p.indeks LIKE '10.%')
    GROUP BY s.id_biura, s.t0
)
SELECT
    s.id_biura,
    s.t0,
    z.dni_od_ostatniego_zamowienia
FROM biura s
LEFT JOIN zamowienia_kawy z USING (id_biura)
