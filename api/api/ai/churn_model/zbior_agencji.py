"""Zbiór agencji i jej sposób oceny: agencja_features ⋈ snapshoty, losowy podział wierszy 80/20.

Wszystkie wersje oceniane „tak jak agencja” biorą dane i podział stąd, więc mają ten sam zbiór testowy.
"""

import pandas as pd
from sklearn.model_selection import train_test_split

from api.adapters.duckdb_conn import connect

ZIARNO = 42
SPOSOB_OCENY = "losowy podział wierszy 80/20, stratyfikowany, random_state=42"
SQL = """
SELECT a.* EXCLUDE (odejdzie_90d), s.odejdzie_90d
FROM agencja_features a
JOIN snapshoty s ON s.id_biura = a.id_biura AND s.data_snapszotu = a.data_migawki
ORDER BY a.data_migawki, a.id_biura
"""


def dane() -> pd.DataFrame:
    """Wiersze agencji z naszą etykietą odejdzie_90d (kolumnę agencji pomijamy; na wspólnych wierszach jest ta sama)."""
    con = connect(read_only=True)
    try:
        return con.sql(SQL).df()
    finally:
        con.close()


def podzial(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(uczący, testowy) jak u agencji."""
    uczacy, testowy = train_test_split(
        df, test_size=0.2, random_state=ZIARNO, stratify=df["odejdzie_90d"]
    )
    return uczacy, testowy
