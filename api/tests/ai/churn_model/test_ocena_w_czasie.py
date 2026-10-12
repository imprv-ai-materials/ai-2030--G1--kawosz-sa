"""Podział w czasie: test od 2026-01-01, a w uczeniu tylko snapszoty, których okno etykiety kończy się przed testem."""

from datetime import date

import pandas as pd

from api.ai.churn_model.ocena_w_czasie import podzial_w_czasie


def test_okno_etykiety_snapszotu_uczacego_nie_zachodzi_na_test():
    snapszoty = [
        date(2025, 9, 1),
        date(2025, 10, 3),  # okno [10-03, 2026-01-01) kończy się 2025-12-31: ostatni dopuszczalny dzień
        date(2025, 10, 4),  # okno [10-04, 2026-01-02) obejmuje 2026-01-01: zachodzi na test
        date(2025, 11, 1),
        date(2025, 12, 1),
        date(2026, 1, 1),
        date(2026, 4, 1),
    ]
    df = pd.DataFrame({"data_snapszotu": pd.to_datetime(snapszoty)}, index=range(10, 17))

    uczacy, testowy = podzial_w_czasie(df, "data_snapszotu")

    assert uczacy.index.tolist() == [10, 11]
    assert testowy.index.tolist() == [15, 16]
