"""Reguły jakości POS: pos_paragony (dzienne pliki z kas), pos_pozycje, pos_produkty, lokale.

Dzień paragonu to data z `data_czas` (czas lokalny kasy). `pos_pozycje` nie ma daty, więc dzień
pozycji odczytujemy z `nr_paragonu` (RRMMDD + numer kolejny).
"""

import pandas as pd
import pandera.pandas as pa
from dateutil.easter import easter

from api.data_platform.reguly.regula import Poziom, Regula, Wlasciciel, meta, warunek

METODY_PLATNOSCI = ["gotówka", "karta", "BLIK", "aplikacja", "karta podarunkowa"]
KANALY = ["sala", "wynos", "aplikacja"]
STAWKI_VAT = [5, 8, 23]
# P0999 „Kawa ziarnista na wagę” ma w cenniku 0,00 — cenę wpisuje sprzedawca. Ziarno kosztuje 149–169 zł/kg.
CENA_RECZNA_MAX = 500.0
MAX_SZTUK = 20
# Liczba paragonów lokalu w dniu względem mediany z 28 poprzednich dni (w historii: 0,43–1,71 poza duplikatami).
WOLUMEN_MIN, WOLUMEN_MAX = 0.4, 1.8

DZIEN_POZYCJI = "strptime((nr_paragonu // 10000)::VARCHAR, '%y%m%d')::DATE"
PARAGONY_W_ZAKRESIE = "SELECT * FROM pos_paragony WHERE data_czas::DATE BETWEEN $od AND $dzien"


def _dzien_zamkniety(dni: pd.Series) -> pd.Series:
    """Lokale są zamknięte 1.01, w Wielkanoc i 25.12."""
    wielkanoc = [pd.Timestamp(easter(rok)) for rok in dni.dt.year.unique()]
    return (dni.dt.month.eq(1) & dni.dt.day.eq(1)) | (dni.dt.month.eq(12) & dni.dt.day.eq(25)) | dni.isin(wielkanoc)


POS_01 = Regula(
    sql=PARAGONY_W_ZAKRESIE,
    schemat=pa.DataFrameSchema(
        {
            "lokal": pa.Column("int32", pa.Check.ge(1)),
            "nr_paragonu": pa.Column("int64", pa.Check.in_range(10**9, 10**10 - 1)),
            "data_czas": pa.Column("datetime64[us]"),
            "kwota_brutto": pa.Column("float64"),
            "metoda_platnosci": pa.Column(str, pa.Check.isin(METODY_PLATNOSCI), nullable=True),
            "storno": pa.Column("int32", pa.Check.isin([0, 1])),
            "kanal": pa.Column(str, pa.Check.isin(KANALY), nullable=True),
            "plik": pa.Column(str),
        },
        strict=True,
        name="POS-01",
        description="Paragon ma oczekiwane kolumny i typy, a storno, kanał i metoda płatności są ze słowników",
        metadata=meta(Poziom.BLOKUJE, Wlasciciel.ZESPOL_DANYCH),
    ),
)

POS_02 = Regula(
    sql=f"SELECT lokal, nr_paragonu, data_czas, kwota_brutto, plik FROM ({PARAGONY_W_ZAKRESIE})",
    schemat=pa.DataFrameSchema(
        {"lokal": pa.Column("int32"), "nr_paragonu": pa.Column("int64")},
        unique=["lokal", "nr_paragonu"],
        report_duplicates="exclude_first",
        name="POS-02",
        description="Paragon (lokal, nr_paragonu) występuje w danych raz",
        metadata=meta(Poziom.BLOKUJE, Wlasciciel.ZESPOL_DANYCH, 15),
    ),
)

POS_03 = Regula(
    sql="""
        SELECT lokal, nr_paragonu, data_czas, storno, kwota_brutto, plik,
               format('pos_paragony_{}_{}.csv', lokal, strftime(data_czas, '%Y-%m-%d')) AS plik_oczekiwany,
               nr_paragonu // 10000 AS data_w_numerze,
               strftime(data_czas, '%y%m%d')::BIGINT AS data_paragonu,
               -- storna kasa dopisuje na końcu dnia, więc kolejność sprawdzamy tylko dla pozostałych paragonów
               CASE WHEN storno = 0 THEN max(data_czas) FILTER (WHERE storno = 0) OVER (
                   PARTITION BY lokal, data_czas::DATE ORDER BY nr_paragonu
                   ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) END AS najpozniej_wczesniejszy
        FROM pos_paragony WHERE data_czas::DATE BETWEEN $od AND $dzien
    """,
    schemat=pa.DataFrameSchema(
        checks=[
            warunek("plik = pos_paragony_{lokal}_{dzień}.csv", lambda d: d["plik"] == d["plik_oczekiwany"]),
            warunek("data w numerze paragonu = data paragonu", lambda d: d["data_w_numerze"] == d["data_paragonu"]),
            warunek(
                "numer paragonu rośnie z czasem",
                lambda d: d["najpozniej_wczesniejszy"].isna() | (d["data_czas"] >= d["najpozniej_wczesniejszy"]),
            ),
        ],
        name="POS-03",
        description="Nazwa pliku, numer paragonu i czas są spójne; numeracja w dniu rośnie razem z czasem",
        metadata=meta(Poziom.BLOKUJE, Wlasciciel.ZESPOL_DANYCH, 15, 24),
    ),
)

POS_04 = Regula(
    sql=f"""
        WITH n AS (SELECT lokal, data_czas::DATE AS dzien, count(*) AS paragony,
                          sum(kwota_brutto)::DOUBLE AS suma_naglowkow
                   FROM pos_paragony WHERE data_czas::DATE BETWEEN $od AND $dzien GROUP BY ALL),
        p AS (SELECT lokal, {DZIEN_POZYCJI} AS dzien, count(DISTINCT nr_paragonu) AS paragony_w_pozycjach,
                     sum(ilosc * cena_brutto) AS suma_pozycji
              FROM pos_pozycje WHERE {DZIEN_POZYCJI} BETWEEN $od AND $dzien GROUP BY ALL)
        SELECT lokal, dzien, coalesce(n.paragony, 0) AS paragony,
               coalesce(p.paragony_w_pozycjach, 0) AS paragony_w_pozycjach,
               coalesce(n.suma_naglowkow, 0) AS suma_naglowkow, coalesce(p.suma_pozycji, 0) AS suma_pozycji
        FROM n FULL JOIN p USING (lokal, dzien)
    """,
    schemat=pa.DataFrameSchema(
        checks=[
            warunek(
                "Σ kwota_brutto = Σ ilosc × cena_brutto",
                lambda d: (d["suma_naglowkow"] - d["suma_pozycji"]).abs() < 0.005,
            ),
            warunek(
                "liczba paragonów = liczba paragonów w pozycjach", lambda d: d["paragony"] == d["paragony_w_pozycjach"]
            ),
        ],
        name="POS-04",
        description="Suma nagłówków paragonów lokalu w dniu równa się sumie ich pozycji",
        metadata=meta(Poziom.BLOKUJE, Wlasciciel.ZESPOL_DANYCH, 15, 25),
    ),
)

POS_05 = Regula(
    sql=f"""
        WITH r AS (SELECT DISTINCT lokal, nr_paragonu, data_czas::DATE AS dzien FROM pos_paragony
                   WHERE data_czas::DATE BETWEEN $od AND $dzien),
        p AS (SELECT lokal, nr_paragonu, count(*) AS pozycje,
                     count(*) FILTER (WHERE pr.kod_produktu IS NULL) AS pozycje_spoza_cennika
              FROM pos_pozycje LEFT JOIN pos_produkty pr USING (kod_produktu)
              WHERE {DZIEN_POZYCJI} BETWEEN $od AND $dzien GROUP BY ALL)
        SELECT lokal, nr_paragonu, r.dzien, r.lokal IS NOT NULL AS ma_naglowek,
               coalesce(p.pozycje, 0) AS pozycje, coalesce(p.pozycje_spoza_cennika, 0) AS pozycje_spoza_cennika,
               l.lokal IS NOT NULL AS lokal_w_slowniku, l.data_otwarcia
        FROM r FULL JOIN p USING (lokal, nr_paragonu) LEFT JOIN lokale l USING (lokal)
    """,
    schemat=pa.DataFrameSchema(
        {
            "ma_naglowek": pa.Column(bool, pa.Check.eq(True, error="pozycja bez paragonu")),
            "pozycje": pa.Column("int64", pa.Check.ge(1, error="paragon bez pozycji")),
            "pozycje_spoza_cennika": pa.Column("int64", pa.Check.eq(0, error="kod produktu spoza pos_produkty")),
            "lokal_w_slowniku": pa.Column(bool, pa.Check.eq(True, error="lokal spoza tabeli lokale")),
        },
        checks=[
            warunek(
                "paragon nie wcześniej niż otwarcie lokalu",
                lambda d: d["dzien"].isna() | d["data_otwarcia"].isna() | (d["dzien"] >= d["data_otwarcia"]),
            )
        ],
        name="POS-05",
        description="Paragon ma pozycje, pozycja ma paragon i produkt z cennika, lokal istnieje i był już otwarty",
        metadata=meta(Poziom.BLOKUJE, Wlasciciel.ZESPOL_DANYCH),
    ),
)

POS_06 = Regula(
    sql=f"""
        SELECT p.lokal, p.nr_paragonu, p.kod_produktu, p.ilosc, p.cena_brutto, p.vat,
               pr.cena_brutto AS cena_cennik, pr.vat AS vat_cennik
        FROM pos_pozycje p JOIN pos_produkty pr USING (kod_produktu)
        WHERE {DZIEN_POZYCJI} BETWEEN $od AND $dzien
    """,
    schemat=pa.DataFrameSchema(
        {
            "ilosc": pa.Column("int64", [pa.Check.ne(0), pa.Check.in_range(-MAX_SZTUK, MAX_SZTUK)]),
            "vat": pa.Column("int64", pa.Check.isin(STAWKI_VAT)),
        },
        checks=[
            warunek("stawka VAT = stawka z cennika", lambda d: d["vat"] == d["vat_cennik"]),
            warunek(
                "cena = cena z cennika",
                lambda d: (d["cena_cennik"] == 0) | ((d["cena_brutto"] - d["cena_cennik"]).abs() < 0.005),
            ),
            warunek(
                f"cena ręczna w zakresie 0–{CENA_RECZNA_MAX:.0f} zł",
                lambda d: (d["cena_cennik"] != 0) | d["cena_brutto"].between(0, CENA_RECZNA_MAX, inclusive="right"),
            ),
        ],
        name="POS-06",
        description=f"Cena i VAT z cennika, cena ręczna do {CENA_RECZNA_MAX:.0f} zł, ilość niezerowa do {MAX_SZTUK}",
        metadata=meta(Poziom.BLOKUJE, Wlasciciel.OPERACJE_LOKALI, 24, 3),
    ),
)

POS_07 = Regula(
    sql=f"SELECT lokal, nr_paragonu, data_czas, kwota_brutto, metoda_platnosci FROM ({PARAGONY_W_ZAKRESIE})",
    schemat=pa.DataFrameSchema(
        {"metoda_platnosci": pa.Column(str, pa.Check.isin(METODY_PLATNOSCI))},
        name="POS-07",
        description="Paragon ma metodę płatności",
        metadata=meta(Poziom.OSTRZEGA, Wlasciciel.OPERACJE_LOKALI, 21),
    ),
)

POS_08 = Regula(
    sql="""
        SELECT lokal, nr_paragonu, data_czas, storno, kwota_brutto FROM pos_paragony
        WHERE data_czas::DATE BETWEEN $od AND $dzien AND (storno = 1 OR kwota_brutto < 0)
    """,
    schemat=pa.DataFrameSchema(
        checks=[warunek("kwota ujemna ⇔ storno = 1", lambda d: (d["kwota_brutto"] < 0) == (d["storno"] == 1))],
        name="POS-08",
        description="Paragon z ujemną kwotą jest oznaczony jako storno (zwrot), a storno ma ujemną kwotę",
        metadata=meta(Poziom.OSTRZEGA, Wlasciciel.OPERACJE_LOKALI, 22),
    ),
)

POS_09 = Regula(
    sql="SELECT * FROM pos_paragony WHERE storno = 1 AND data_czas::DATE BETWEEN $od AND $dzien",
    schemat=pa.DataFrameSchema(
        # Kolumny dziś nie ma w pliku z kasy — reguła jest wymaganiem wobec dostawcy POS.
        {"nr_paragonu_stornowanego": pa.Column("int64", pa.Check.in_range(10**9, 10**10 - 1))},
        name="POS-09",
        description="Storno wskazuje numer paragonu, który stornuje",
        metadata=meta(Poziom.OSTRZEGA, Wlasciciel.OPERACJE_LOKALI, 19),
    ),
)

POS_10 = Regula(
    sql="""
        WITH dni AS (SELECT unnest(generate_series($od::DATE, $dzien::DATE, INTERVAL 1 DAY))::DATE AS dzien),
        p AS (SELECT lokal, data_czas::DATE AS dzien, count(*) AS paragony FROM pos_paragony
              WHERE data_czas::DATE BETWEEN $od AND $dzien GROUP BY ALL)
        SELECT l.lokal, d.dzien, coalesce(p.paragony, 0) AS paragony
        FROM lokale l JOIN dni d ON d.dzien >= l.data_otwarcia
        LEFT JOIN p ON p.lokal = l.lokal AND p.dzien = d.dzien
    """,
    schemat=pa.DataFrameSchema(
        checks=[
            warunek(
                "lokal ma paragony z dnia (poza 1.01, Wielkanocą i 25.12)",
                lambda d: (d["paragony"] > 0) | _dzien_zamkniety(d["dzien"]),
            )
        ],
        name="POS-10",
        description="Każdy otwarty lokal przysłał paragony za każdy dzień do dnia eksportu",
        metadata=meta(Poziom.BLOKUJE, Wlasciciel.ZESPOL_DANYCH),
    ),
)

POS_11 = Regula(
    sql="""
        WITH d AS (SELECT lokal, data_czas::DATE AS dzien, count(*) AS paragony FROM pos_paragony
                   WHERE data_czas::DATE BETWEEN $od::DATE - 28 AND $dzien GROUP BY ALL)
        SELECT * FROM (
            SELECT *, median(paragony) OVER w AS mediana_28_dni, count(*) OVER w AS dni_historii FROM d
            WINDOW w AS (PARTITION BY lokal ORDER BY dzien
                         RANGE BETWEEN INTERVAL 28 DAY PRECEDING AND INTERVAL 1 DAY PRECEDING))
        WHERE dzien >= $od AND dni_historii >= 14
    """,
    schemat=pa.DataFrameSchema(
        checks=[
            warunek(
                f"paragony = {WOLUMEN_MIN}–{WOLUMEN_MAX} × mediana z 28 dni",
                lambda d: (d["paragony"] / d["mediana_28_dni"]).between(WOLUMEN_MIN, WOLUMEN_MAX),
            )
        ],
        name="POS-11",
        description=f"Liczba paragonów lokalu w dniu to {WOLUMEN_MIN}–{WOLUMEN_MAX} × mediany z 28 poprzednich dni",
        metadata=meta(Poziom.OSTRZEGA, Wlasciciel.ZESPOL_DANYCH, 15),
    ),
)

REGULY = [POS_01, POS_02, POS_03, POS_04, POS_05, POS_06, POS_07, POS_08, POS_09, POS_10, POS_11]
