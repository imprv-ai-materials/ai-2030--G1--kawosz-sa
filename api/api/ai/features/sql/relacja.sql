-- Rodzina „relacja”: opiekun klienta, kontakty AM i NPS biura przed dniem t0.
-- Parametr $t0 (DATE). Wynik: 1 wiersz na biuro z populacji w t0. Opisy cech: ../katalog.yaml.
--
-- am_id: z crm_biura, czyli stan z dnia eksportu. Historii przypisań nie ma, a cecha nie rozdziela klas
--   (AUC 0,51, docs/przecieki.md, sekcja 2).
-- kontakty_am_90d: kontakty AM w [t0 − 90, t0).
-- nps_ostatni: wynik ostatniej odpowiedzi na ankietę NPS sprzed t0; brak, gdy biuro nie odpowiedziało.
-- Bez rabat_retencyjny_max agencji: rabat retencyjny AM daje 1–25 dni po wypowiedzeniu, a liczony z rekordów sprzed
-- t0 byłby zawsze 0 (docs/przecieki.md, 6.2 i 7).

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
kontakty AS (
    SELECT s.id_biura, count(*) AS kontakty_am_90d
    FROM biura s
    JOIN crm_kontakty_am k ON k.id_biura = s.id_biura AND k.data >= s.t0 - 90 AND k.data < s.t0
    GROUP BY s.id_biura
),
nps AS (
    SELECT s.id_biura, arg_max(n.wynik, n.data_odpowiedzi) AS nps_ostatni
    FROM biura s
    JOIN ankiety_nps n ON n.id_biura = s.id_biura AND n.data_odpowiedzi < s.t0
    GROUP BY s.id_biura
)
SELECT
    s.id_biura,
    s.t0,
    b.am_id,
    coalesce(k.kontakty_am_90d, 0) AS kontakty_am_90d,
    n.nps_ostatni
FROM biura s
JOIN crm_biura b USING (id_biura)
LEFT JOIN kontakty k USING (id_biura)
LEFT JOIN nps n USING (id_biura)
