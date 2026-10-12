-- Rodzina „płatności”: terminowość płatności biura w ERP znana w dniu t0.
-- Parametr $t0 (DATE). Wynik: 1 wiersz na biuro z populacji w t0. Opisy cech: ../katalog.yaml.
--
-- Opóźnienie ERP: D+1 (kontrakt erp_faktury, docs/opoznienia_danych.md), więc w t0 znane są faktury i płatności do
-- znane_do = t0 − 2.
-- sr_opoznienie_platnosci: średnio (data płatności − data faktury − 14) dla płatności z 90 ostatnich znanych dni,
--   [znane_do − 89, znane_do]. 14 dni to mediana czasu zapłaty w ERP; termin nie jest zapisany. Kontrahent przez
--   mapa_kontrahentow, jak w zamowienia.sql. Brak, gdy w oknie nie ma płatności.

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
platnosci AS (
    SELECT s.id_biura, avg(pl.data_platnosci - f.data - 14) AS sr_opoznienie_platnosci
    FROM biura s
    CROSS JOIN p
    JOIN faktury f ON f.id_biura = s.id_biura AND f.data <= p.znane_do
    JOIN erp_platnosci pl
      ON pl.nr_faktury = f.nr_faktury AND pl.data_platnosci BETWEEN p.znane_do - 89 AND p.znane_do
    GROUP BY s.id_biura
)
SELECT
    s.id_biura,
    s.t0,
    o.sr_opoznienie_platnosci
FROM biura s
LEFT JOIN platnosci o USING (id_biura)
