-- Rodzina „użycie”: telemetria ekspresów biura przed dniem t0.
-- Parametr $t0 (DATE). Wynik: 1 wiersz na biuro z populacji w t0. Opisy cech: ../katalog.yaml.
--
-- Telemetria dociera 2 dni po dniu pomiaru (data_dostarczenia = data + 2), więc w dniu t0 ostatni znany dzień to
-- t0 − 3. Agencja sumowała 30 dni PO snapszocie (docs/przecieki.md, 6.1); tu okna kończą się na t0 − 3:
-- zaparzenia_30d: suma ze wszystkich ekspresów biura z dni [t0 − 32, t0 − 3].
-- trend_zaparzen: zaparzenia_30d / zaparzenia z dni [t0 − 62, t0 − 33]; brak, gdy mianownik = 0 albo brak telemetrii.
-- bledy_60d: suma błędów z dni [t0 − 62, t0 − 3].

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
telemetria AS (
    SELECT
        s.id_biura,
        sum(t.zaparzenia) FILTER (WHERE t.data >= s.t0 - 32) AS zaparzenia_30d,
        sum(t.zaparzenia) FILTER (WHERE t.data < s.t0 - 32) AS zaparzenia_poprzednie_30d,
        sum(t.bledy) AS bledy_60d
    FROM biura s
    JOIN iot_ekspresy e ON e.id_biura = s.id_biura
    JOIN iot_telemetria t
      ON t.id_ekspresu = e.id_ekspresu
     AND t.data BETWEEN s.t0 - 62 AND s.t0 - 3
     AND t.data_dostarczenia < s.t0
    GROUP BY s.id_biura
)
SELECT
    s.id_biura,
    s.t0,
    coalesce(t.zaparzenia_30d, 0) AS zaparzenia_30d,
    t.zaparzenia_30d / nullif(t.zaparzenia_poprzednie_30d, 0) AS trend_zaparzen,
    coalesce(t.bledy_60d, 0) AS bledy_60d
FROM biura s
LEFT JOIN telemetria t USING (id_biura)
