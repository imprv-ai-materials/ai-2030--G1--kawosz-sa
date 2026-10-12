-- Cechy reguły opiekunów dla każdego wiersza snapshoty, liczone na stan z dnia snapszotu d (bez przyszłości).
--
-- dni_do_konca_okresu: dni od d do końca bieżącego rocznego okresu umowy. Umowa odnawia się w rocznicę data_startu
--   (docs/target.md), więc koniec okresu = najbliższa rocznica po d minus 1 dzień. Nie bierzemy
--   crm_biura.data_konca_umowy: to stan z dnia eksportu, po odnowieniach (przeciek, evals/v0_agencja.md).
-- zaparzenia_30d_iot / zaparzenia_90d_iot: suma zaparzeń wszystkich ekspresów biura z 30 / 90 ostatnich znanych dni.
--   Telemetria dociera 2 dni po dniu pomiaru (data_dostarczenia = data + 2), więc w dniu d ostatni znany dzień
--   to d − 3: okna [d − 32, d − 3] i [d − 92, d − 3]. Okno 90 dni obejmuje okno 30 dni.

WITH s AS (
    SELECT
        s.id_biura,
        s.data_snapszotu,
        CAST(b.data_startu + to_years(date_diff('year', b.data_startu, s.data_snapszotu)) AS DATE) AS rocznica
    FROM snapshoty s
    JOIN crm_biura b USING (id_biura)
),
okres AS (
    SELECT
        id_biura,
        data_snapszotu,
        CAST(CASE WHEN rocznica <= data_snapszotu THEN rocznica + INTERVAL 1 YEAR ELSE rocznica END AS DATE) - 1
            AS koniec_okresu
    FROM s
),
telemetria AS (
    SELECT e.id_biura, t.data, t.data_dostarczenia, t.zaparzenia
    FROM iot_telemetria t
    JOIN iot_ekspresy e USING (id_ekspresu)
)
SELECT
    o.id_biura,
    o.data_snapszotu,
    o.koniec_okresu - o.data_snapszotu AS dni_do_konca_okresu,
    coalesce(sum(t.zaparzenia) FILTER (WHERE t.data >= o.data_snapszotu - 32), 0) AS zaparzenia_30d_iot,
    coalesce(sum(t.zaparzenia), 0) AS zaparzenia_90d_iot
FROM okres o
LEFT JOIN telemetria t
  ON t.id_biura = o.id_biura
 AND t.data BETWEEN o.data_snapszotu - 92 AND o.data_snapszotu - 3
 AND t.data_dostarczenia < o.data_snapszotu
GROUP BY o.id_biura, o.data_snapszotu, o.koniec_okresu
