"""Losowanie grupy kontrolnej: stałe dla biura w kwartale, udział biur w kontroli bliski zadanemu."""

from datetime import date

from api.contexts_boundaries.retention_bc import kontrola


def test_kwartal_z_daty():
    assert [kontrola.kwartal(date(2026, m, 15)) for m in (1, 3, 4, 9, 10, 12)] == [
        "2026-Q1", "2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4", "2026-Q4",
    ]


def test_biuro_ma_ten_sam_los_przez_caly_kwartal_a_w_innym_kwartale_inny():
    assert kontrola.los("2026-Q4", 11521) == kontrola.los("2026-Q4", 11521)
    assert kontrola.los("2026-Q4", 11521) != kontrola.los("2027-Q1", 11521)


def test_udzial_biur_w_kontroli_jest_bliski_zadanemu():
    w = [kontrola.w_kontroli(b, "2026-Q4", 0.1) for b in range(10_000, 20_000)]
    assert 0.09 < sum(w) / len(w) < 0.11


def test_zerowy_udzial_to_brak_kontroli():
    assert not any(kontrola.w_kontroli(b, "2026-Q4", 0.0) for b in range(10_000, 11_000))
