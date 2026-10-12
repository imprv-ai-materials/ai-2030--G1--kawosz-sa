-- snapshoty: 1 wiersz = biuro z aktywną umową × 1. dzień miesiąca (2024-01-01 … 2026-06-01)
-- Źródła: crm_biura, crm_umowy_historia. Definicje i otwarte pytania: docs/target.md.
--
-- Snapszot to stan na początek dnia data_snapszotu: znane są tylko zdarzenia sprzed tego dnia.
-- Aktywna umowa: data_startu <= data_snapszotu <= data_konca_umowy i brak wypowiedzenia złożonego
-- przed data_snapszotu (biura w okresie wypowiedzenia już odchodzą, więc nie ma czego przewidywać).
--
-- odejdzie_90d = 1, gdy w oknie [data_snapszotu, data_snapszotu + 90 dni):
--   * biuro złoży wypowiedzenie (data_zdarzenia typu 'wypowiedzenie'), albo
--   * minie termin odnowienia bez odnowienia: umowa zakończona bez wypowiedzenia, termin = data_konca_umowy + 1
--     (rocznica startu, w której odnowienie by nastąpiło).
-- Zawieszenie, downgrade, fuzja i przeprowadzka NIE są odejściem, tylko cechami (decyzja 2026-10-12, docs/target.md).
-- Wpisy 'odnowienie' po wypowiedzeniu (51 biur) są ignorowane: wszystkie te umowy i tak się kończą.

CREATE OR REPLACE TABLE snapshoty AS
WITH dni AS (
    SELECT CAST(d AS DATE) AS data_snapszotu
    FROM generate_series(DATE '2024-01-01', DATE '2026-06-01', INTERVAL 1 MONTH) AS t(d)
),
wypowiedzenia AS (
    -- w danych każde biuro ma najwyżej jedno wypowiedzenie
    SELECT id_biura, data_zdarzenia AS data_wypowiedzenia
    FROM crm_umowy_historia
    WHERE typ = 'wypowiedzenie'
),
biura AS (
    SELECT
        b.id_biura,
        b.data_startu,
        b.data_konca_umowy,
        w.data_wypowiedzenia,
        CASE WHEN b.status = 'zakończony' AND w.data_wypowiedzenia IS NULL
             THEN b.data_konca_umowy + 1 END AS data_braku_odnowienia
    FROM crm_biura b
    LEFT JOIN wypowiedzenia w USING (id_biura)
)
SELECT
    d.data_snapszotu,
    b.id_biura,
    CAST(
        coalesce(b.data_wypowiedzenia >= d.data_snapszotu
                 AND b.data_wypowiedzenia < d.data_snapszotu + INTERVAL 90 DAY, FALSE)
        OR coalesce(b.data_braku_odnowienia < d.data_snapszotu + INTERVAL 90 DAY, FALSE)
    AS INTEGER) AS odejdzie_90d
FROM dni d
JOIN biura b
  ON b.data_startu <= d.data_snapszotu
 AND b.data_konca_umowy >= d.data_snapszotu
 AND coalesce(b.data_wypowiedzenia >= d.data_snapszotu, TRUE)
ORDER BY d.data_snapszotu, b.id_biura;
