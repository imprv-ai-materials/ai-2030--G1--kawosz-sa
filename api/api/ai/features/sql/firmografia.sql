-- Rodzina „firmografia”: atrybuty biura z CRM.
-- Parametr $t0 (DATE). Wynik: 1 wiersz na biuro z populacji w t0. Opisy cech: ../katalog.yaml.
--
-- liczba_pracownikow, branza, miasto: z crm_biura, czyli stan z dnia eksportu, bo historii nie ma. Cechy nie
--   rozdzielają klas (AUC 0,48–0,54, docs/przecieki.md, sekcja 2), więc zostały z tą adnotacją (decyzja 2026-10-12).
-- Bez miasto_te agencji: to kodowanie miasta średnią etykiety, więc uczy się go model, tylko na zbiorze uczącym
--   (kodowanie_celu.py).

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
)
SELECT
    s.id_biura,
    s.t0,
    b.liczba_pracownikow,
    b.branza,
    b.miasto
FROM biura s
JOIN crm_biura b USING (id_biura)
