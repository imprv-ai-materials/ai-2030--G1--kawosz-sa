-- Rodzina „relacja”: opiekun klienta, kontakty AM i NPS biura znane w dniu t0.
-- Parametr $t0 (DATE). Wynik: 1 wiersz na biuro z populacji w t0. Opisy cech: ../katalog.yaml.
--
-- Opóźnienie CRM (kontakty, ankiety): nieznane, przyjęte D+1 jak w innych nocnych dostawach
-- (docs/opoznienia_danych.md), więc w t0 znane są rekordy do znane_do = t0 − 2.
-- am_id: z crm_biura, czyli stan z dnia eksportu. Historii przypisań nie ma, a cecha nie rozdziela klas
--   (AUC 0,51, docs/przecieki.md, sekcja 2).
-- kontakty_am_90d: kontakty AM w 90 ostatnich znanych dniach, [znane_do − 89, znane_do].
-- nps_ostatni: ostatni znany stan NPS, czyli wynik odpowiedzi z największą data_odpowiedzi <= znane_do (ASOF JOIN).
--   Liczy się dzień odpowiedzi, nie wysyłki: wysłana ankieta bez odpowiedzi nic nie mówi. Brak, gdy biuro jeszcze
--   nie odpowiedziało. Dwóch odpowiedzi biura z jednego dnia w danych nie ma.
-- Bez rabat_retencyjny_max agencji: rabat retencyjny AM daje 1–25 dni po wypowiedzeniu, a liczony z rekordów sprzed
-- t0 byłby zawsze 0 (docs/przecieki.md, 6.2 i 7).

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
kontakty AS (
    SELECT s.id_biura, count(*) AS kontakty_am_90d
    FROM biura s
    CROSS JOIN p
    JOIN crm_kontakty_am k ON k.id_biura = s.id_biura AND k.data BETWEEN p.znane_do - 89 AND p.znane_do
    GROUP BY s.id_biura
),
odpowiedzi AS (
    SELECT id_biura, data_odpowiedzi, wynik FROM ankiety_nps WHERE data_odpowiedzi IS NOT NULL
)
SELECT
    s.id_biura,
    s.t0,
    b.am_id,
    coalesce(k.kontakty_am_90d, 0) AS kontakty_am_90d,
    n.wynik AS nps_ostatni
FROM biura s
CROSS JOIN p
JOIN crm_biura b USING (id_biura)
LEFT JOIN kontakty k USING (id_biura)
ASOF LEFT JOIN odpowiedzi n ON n.id_biura = s.id_biura AND p.znane_do >= n.data_odpowiedzi
