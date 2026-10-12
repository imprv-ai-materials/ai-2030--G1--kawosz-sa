"""Wiersz cechy_treningowe da się odtworzyć z samej przeszłości: 5 losowych par (biuro, t0) na kawosz.duckdb.

Dla każdej pary budujemy w pamięci bazę, w której są wyłącznie rekordy sprzed t0 (telemetria: dostarczona przed t0,
NPS: odpowiedzi sprzed t0), liczymy na niej pliki sql/ i porównujemy z wierszem tabeli. Różnica znaczy, że cecha
korzysta z danych z t0 albo późniejszych, albo że tabela nie odpowiada obecnym plikom sql/
(python -m api.ai.features.build). Bez stanu z przeszłości zostają crm_biura, kontrahenci ERP i mapa_kontrahentow,
bo nie mają historii (docs/opoznienia_danych.md, sekcja 7).

Pary są losowane przy każdym uruchomieniu. Ziarno jest w nazwie testu, a CECHY_ZIARNO=<ziarno> powtarza losowanie.
Bez kawosz.duckdb albo tabeli cechy_treningowe test jest pomijany. Uruchamia go hook pre-commit (cechy-z-przeszlosci).
"""

import math
import os
import random

import duckdb
import pytest

from api.adapters.duckdb_conn import DB_PATH
from api.ai.features.build import KATALOG_SQL, KLUCZ, RODZINY

PARY = 5
ZIARNO = int(os.environ.get("CECHY_ZIARNO", random.SystemRandom().randrange(10**6)))

# tabela → SELECT ze źródła (src) z samymi rekordami znanymi przed $t0
STAN_PRZED_T0 = {
    "crm_biura": "SELECT * FROM src.crm_biura",
    "crm_umowy_historia": "SELECT * FROM src.crm_umowy_historia WHERE data_zdarzenia < $t0",
    "crm_kontakty_am": "SELECT * FROM src.crm_kontakty_am WHERE data < $t0",
    # ankieta wysłana przed t0, a odpowiedź przyszła później: w t0 to ankieta bez odpowiedzi
    "ankiety_nps": """
        SELECT id_biura, data_wysylki,
               CASE WHEN data_odpowiedzi < $t0 THEN data_odpowiedzi END AS data_odpowiedzi,
               CASE WHEN data_odpowiedzi < $t0 THEN wynik END AS wynik
        FROM src.ankiety_nps WHERE data_wysylki < $t0""",
    "helpdesk_zgloszenia": """
        SELECT * REPLACE (CASE WHEN rozwiazano < $t0 THEN rozwiazano END AS rozwiazano)
        FROM src.helpdesk_zgloszenia WHERE utworzono < $t0""",
    "iot_ekspresy": "SELECT * FROM src.iot_ekspresy WHERE data_instalacji < $t0",
    "iot_telemetria": "SELECT * FROM src.iot_telemetria WHERE data_dostarczenia < $t0",
    "erp_faktury": "SELECT * FROM src.erp_faktury WHERE data < $t0",
    "erp_pozycje": "SELECT * FROM src.erp_pozycje SEMI JOIN (SELECT nr_faktury FROM src.erp_faktury WHERE data < $t0)"
    " USING (nr_faktury)",
    "erp_platnosci": "SELECT * FROM src.erp_platnosci WHERE data_platnosci < $t0",
    "erp_kontrahenci": "SELECT * FROM src.erp_kontrahenci",
    "erp_kontrahenci_archiwum": "SELECT * FROM src.erp_kontrahenci_archiwum",
    "mapa_kontrahentow": "SELECT * FROM src.mapa_kontrahentow",
}


def _losowe_pary() -> list[tuple[int, object]]:
    if not DB_PATH.exists():
        return []
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        if not con.sql("SELECT 1 FROM duckdb_tables() WHERE table_name = 'cechy_treningowe'").fetchall():
            return []
        klucze = con.sql("SELECT id_biura, t0 FROM cechy_treningowe ORDER BY t0, id_biura").fetchall()
    finally:
        con.close()
    return random.Random(ZIARNO).sample(klucze, PARY)


_PARY = _losowe_pary()


def _rowne(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
    return a == b


@pytest.mark.skipif(not _PARY, reason="brak kawosz.duckdb albo cechy_treningowe (python -m api.ai.features.build)")
@pytest.mark.parametrize("id_biura, t0", _PARY, ids=[f"ziarno{ZIARNO}-biuro{b}-{t}" for b, t in _PARY])
def test_wiersz_cechy_treningowe_z_danych_sprzed_t0(id_biura, t0):
    con = duckdb.connect()
    con.execute(f"ATTACH '{DB_PATH}' AS src (READ_ONLY)")
    for tabela, sql in STAN_PRZED_T0.items():
        con.execute(f"CREATE TABLE {tabela} AS {sql}", {"t0": t0} if "$t0" in sql else None)

    przeliczone = {}
    for rodzina in RODZINY:
        rel = con.execute((KATALOG_SQL / f"{rodzina}.sql").read_text(), {"t0": t0})
        kolumny = [d[0] for d in rel.description]
        wiersze = [w for w in rel.fetchall() if w[0] == id_biura]
        assert len(wiersze) == 1, f"{rodzina}: biuro {id_biura} nie jest w populacji t0 = {t0} liczonej z przeszłości"
        przeliczone.update(dict(zip(kolumny, wiersze[0])))
    tabela = con.execute(
        "SELECT * EXCLUDE (odejdzie_90d) FROM src.cechy_treningowe WHERE id_biura = ? AND t0 = ?", [id_biura, t0]
    )
    zapisane = dict(zip([d[0] for d in tabela.description], tabela.fetchone()))

    rozne = {
        c: (zapisane[c], przeliczone[c]) for c in zapisane if c not in KLUCZ and not _rowne(zapisane[c], przeliczone[c])
    }
    assert przeliczone.keys() == zapisane.keys()
    assert not rozne, f"cechy różne od przeliczonych z danych sprzed t0 (tabela, przeliczone): {rozne}"
