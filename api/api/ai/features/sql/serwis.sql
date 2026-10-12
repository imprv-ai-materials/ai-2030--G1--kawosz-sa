-- Rodzina „serwis”: zgłoszenia biura w helpdesku przed dniem t0.
-- Parametr $t0 (DATE). Wynik: 1 wiersz na biuro z populacji w t0. Opisy cech: ../katalog.yaml.
--
-- awarie_60d: zgłoszenia kategorii 'awaria' utworzone w [t0 − 60, t0).
-- Bez zgloszenia_odbior_ekspresu agencji: odbiór ekspresu biuro zgłasza 1–20 dni po wypowiedzeniu, a liczony
-- z rekordów sprzed t0 byłby zawsze 0 (docs/przecieki.md, 6.2 i 7).

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
awarie AS (
    SELECT s.id_biura, count(*) AS awarie_60d
    FROM biura s
    JOIN helpdesk_zgloszenia z
      ON z.id_biura = s.id_biura AND z.kategoria = 'awaria'
     AND CAST(z.utworzono AS DATE) >= s.t0 - 60 AND CAST(z.utworzono AS DATE) < s.t0
    GROUP BY s.id_biura
)
SELECT
    s.id_biura,
    s.t0,
    coalesce(a.awarie_60d, 0) AS awarie_60d
FROM biura s
LEFT JOIN awarie a USING (id_biura)
