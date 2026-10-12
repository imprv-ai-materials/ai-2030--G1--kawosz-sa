"""Reguły jakości e-commerce: ecom_zamowienia, ecom_pozycje, ecom_produkty, ecom_subskrypcje, karty_podarunkowe.

Opisy, poziomy, właściciele, słowniki i progi reguł są w kontrakcie kontrakty/ecom_zamowienia.yaml.
Tu jest tylko SQL, który przygotowuje ramkę, i warunki, które ją sprawdzają.

Sklep zapisuje czas w UTC (`data_utc`, `data_platnosci`), a dzień biznesowy to Europe/Warsaw — zakres
liczymy po dniu polskim. Kwoty są brutto w walucie zamówienia (PLN lub EUR).
"""

import pandera.pandas as pa

from api.data_platform.kontrakty.kontrakt import wczytaj
from api.data_platform.reguly.regula import Regula, warunek

KONTRAKT = wczytaj("ecom_zamowienia")
METODY_PLATNOSCI = KONTRAKT.kolumna("metoda_platnosci").dozwolone
PLANY, GODZINY_BATCHA_UTC = (KONTRAKT.parametry("ECOM-09")[p] for p in ("plany", "godziny_batcha_utc"))
NOTATKA_TESTOWA, DOMENA_WEWNETRZNA = (
    KONTRAKT.parametry("ECOM-05")[p] for p in ("notatka_testowa", "domena_wewnetrzna")
)
MAKS_WIEK_KURSU_DNI, KURS_MIN, KURS_MAX = (
    KONTRAKT.parametry("ECOM-04")[p] for p in ("maks_wiek_kursu_dni", "kurs_min", "kurs_max")
)
WZORZEC_EMAIL = KONTRAKT.parametry("ECOM-06")["wzorzec_email"]
OSTATNIA_GODZINA_MIN = KONTRAKT.parametry("ECOM-11")["ostatnia_godzina_min"]
WOLUMEN_MIN, WOLUMEN_MAX, DNI_HISTORII, MIN_DNI_HISTORII = (
    KONTRAKT.parametry("ECOM-12")[p] for p in ("wolumen_min", "wolumen_max", "dni_historii", "min_dni_historii")
)

DZIEN_ZAMOWIENIA = "timezone('Europe/Warsaw', data_utc::TIMESTAMP AT TIME ZONE 'UTC')::DATE"
CZAS_PL_SUBSKRYPCJI = "timezone('Europe/Warsaw', data_platnosci AT TIME ZONE 'UTC')"
ZAMOWIENIA_W_ZAKRESIE = f"SELECT * FROM ecom_zamowienia WHERE {DZIEN_ZAMOWIENIA} BETWEEN $od AND $dzien"

ECOM_01 = Regula(
    sql=ZAMOWIENIA_W_ZAKRESIE,
    schemat=KONTRAKT.schemat(
        "ECOM-01",
        KONTRAKT.kolumny_pandera(),
        checks=[
            warunek("pobranie tylko w PLN", lambda d: (d["metoda_platnosci"] != "pobranie") | (d["waluta"] == "PLN"))
        ],
        strict=True,
    ),
)

ECOM_02 = Regula(
    sql=f"""
        SELECT z.id, z.waluta, z.brutto, coalesce(sum(p.ilosc * p.cena_brutto), 0) AS suma_pozycji
        FROM ecom_zamowienia z LEFT JOIN ecom_pozycje p ON p.id_zamowienia = z.id
        WHERE {DZIEN_ZAMOWIENIA} BETWEEN $od AND $dzien GROUP BY ALL
    """,
    schemat=KONTRAKT.schemat(
        "ECOM-02",
        checks=[warunek("brutto = Σ ilosc × cena_brutto", lambda d: (d["brutto"] - d["suma_pozycji"]).abs() < 0.005)],
    ),
)

ECOM_03 = Regula(
    sql=f"""
        WITH z AS (SELECT id FROM ecom_zamowienia WHERE {DZIEN_ZAMOWIENIA} BETWEEN $od AND $dzien),
        p AS (SELECT id_zamowienia AS id, count(*) AS pozycje,
                     count(*) FILTER (WHERE sku <> 'DOSTAWA' AND sku NOT IN (SELECT sku FROM ecom_produkty))
                         AS pozycje_spoza_cennika,
                     count(*) FILTER (WHERE sku = 'DOSTAWA') AS wiersze_dostawy
              FROM ecom_pozycje GROUP BY 1)
        SELECT id, true AS ma_zamowienie, coalesce(p.pozycje, 0) AS pozycje,
               coalesce(p.pozycje_spoza_cennika, 0) AS pozycje_spoza_cennika,
               coalesce(p.wiersze_dostawy, 0) AS wiersze_dostawy
        FROM z LEFT JOIN p USING (id)
        UNION ALL  -- pozycje bez zamówienia (cała tabela, bo nie mają własnej daty)
        SELECT id, false, pozycje, pozycje_spoza_cennika, wiersze_dostawy FROM p ANTI JOIN ecom_zamowienia USING (id)
    """,
    schemat=KONTRAKT.schemat(
        "ECOM-03",
        {
            "ma_zamowienie": pa.Column(bool, pa.Check.eq(True, error="pozycja bez zamówienia")),
            "pozycje": pa.Column("int64", pa.Check.ge(1, error="zamówienie bez pozycji")),
            "pozycje_spoza_cennika": pa.Column("int64", pa.Check.eq(0, error="SKU spoza ecom_produkty (poza DOSTAWA)")),
            "wiersze_dostawy": pa.Column("int64", pa.Check.le(1, error="więcej niż jeden wiersz DOSTAWA")),
        },
    ),
)

ECOM_04 = Regula(
    sql=f"""
        SELECT z.id, {DZIEN_ZAMOWIENIA} AS dzien, z.brutto, k.data AS data_kursu, k.eur_pln
        FROM ecom_zamowienia z ASOF LEFT JOIN kursy_nbp k ON {DZIEN_ZAMOWIENIA} > k.data
        WHERE z.waluta = 'EUR' AND {DZIEN_ZAMOWIENIA} BETWEEN $od AND $dzien
    """,
    schemat=KONTRAKT.schemat(
        "ECOM-04",
        {"eur_pln": pa.Column("float64", pa.Check.in_range(KURS_MIN, KURS_MAX))},
        checks=[
            warunek(
                f"kurs z poprzedniego dnia roboczego, najwyżej {MAKS_WIEK_KURSU_DNI} dni wstecz",
                lambda d: (d["dzien"] - d["data_kursu"]).dt.days <= MAKS_WIEK_KURSU_DNI,
            )
        ],
    ),
)

ECOM_05 = Regula(
    sql=f"""
        WITH z AS ({ZAMOWIENIA_W_ZAKRESIE}),
        c AS (SELECT p.id_zamowienia AS id, count(*) AS ceny_spoza_cennika
              FROM ecom_pozycje p JOIN ecom_produkty pr USING (sku) JOIN z ON z.id = p.id_zamowienia
              WHERE z.waluta = 'PLN' AND abs(p.cena_brutto - pr.cena_brutto_pln) > 0.005 GROUP BY 1)
        SELECT z.id, z.waluta, z.brutto, z.email, z.notatka, coalesce(c.ceny_spoza_cennika, 0) AS ceny_spoza_cennika
        FROM z LEFT JOIN c USING (id)
    """,
    schemat=KONTRAKT.schemat(
        "ECOM-05",
        {
            "email": pa.Column(
                str,
                pa.Check(
                    lambda s: ~s.str.lower().str.endswith(DOMENA_WEWNETRZNA),
                    error=f"e-mail w domenie {DOMENA_WEWNETRZNA}",
                ),
                nullable=True,
            ),
            "notatka": pa.Column(
                str,
                pa.Check(lambda s: ~s.str.contains(NOTATKA_TESTOWA, case=False), error="notatka testowa"),
                nullable=True,
            ),
            "ceny_spoza_cennika": pa.Column("int64", pa.Check.eq(0, error="cena PLN inna niż w cenniku")),
        },
    ),
)

ECOM_06 = Regula(
    sql=f"SELECT id, metoda_platnosci, brutto, email FROM ({ZAMOWIENIA_W_ZAKRESIE})",
    schemat=KONTRAKT.schemat(
        "ECOM-06",
        {"email": pa.Column(str, pa.Check.str_matches(WZORZEC_EMAIL))},
    ),
)

ECOM_07 = Regula(
    sql=f"SELECT * FROM ecom_zamowienia WHERE zwrot AND {DZIEN_ZAMOWIENIA} BETWEEN $od AND $dzien",
    schemat=KONTRAKT.schemat(
        "ECOM-07",
        # Kolumny są w kontrakcie jako opcjonalne, ale zwrot musi je mieć: dziś sklep ich nie przysyła.
        {k: KONTRAKT.kolumna(k).pandera(nullable=False, required=True) for k in ("data_zwrotu", "kwota_zwrotu")},
    ),
)

ECOM_08 = Regula(
    sql=f"""
        WITH pr AS (SELECT sku, nazwa, count(*) OVER (PARTITION BY lower(trim(nazwa))) AS sku_o_tej_nazwie
                    FROM ecom_produkty)
        SELECT p.id_zamowienia, p.sku, pr.nazwa, pr.sku_o_tej_nazwie
        FROM ecom_pozycje p JOIN pr USING (sku) JOIN ecom_zamowienia z ON z.id = p.id_zamowienia
        WHERE {DZIEN_ZAMOWIENIA} BETWEEN $od AND $dzien
    """,
    schemat=KONTRAKT.schemat(
        "ECOM-08",
        {"sku_o_tej_nazwie": pa.Column("int64", pa.Check.eq(1))},
    ),
)

_PLANY_ETYKIETA = " / ".join(f"{cena:g}" for cena in PLANY.values())
_POZA_BATCHEM = f"godzina zapisu poza nocnym batchem w UTC ({GODZINY_BATCHA_UTC[0]:02d}–{GODZINY_BATCHA_UTC[-1]:02d})"
_PLANY_SQL = ", ".join(f"('{plan}', {kwota})" for plan, kwota in PLANY.items())
ECOM_09 = Regula(
    sql=f"""
        WITH s AS (SELECT *, {CZAS_PL_SUBSKRYPCJI} AS czas_pl FROM ecom_subskrypcje),
        m AS (SELECT *, count(*) OVER (PARTITION BY id, date_trunc('month', czas_pl)) AS obciazenia_w_miesiacu FROM s)
        SELECT m.id, m.plan, m.kwota, c.kwota AS kwota_planu, m.data_platnosci, m.czas_pl,
               hour(m.data_platnosci) AS godzina_zapisu, m.obciazenia_w_miesiacu
        FROM m LEFT JOIN (VALUES {_PLANY_SQL}) c(plan, kwota) USING (plan)
        WHERE m.czas_pl::DATE BETWEEN $od AND $dzien
    """,
    schemat=KONTRAKT.schemat(
        "ECOM-09",
        {
            "plan": pa.Column(str, pa.Check.isin(list(PLANY))),
            "obciazenia_w_miesiacu": pa.Column("int64", pa.Check.eq(1, error="więcej niż jedno obciążenie w miesiącu")),
            "godzina_zapisu": pa.Column(
                "int64",
                pa.Check.isin(GODZINY_BATCHA_UTC, error=_POZA_BATCHEM),
            ),
        },
        checks=[warunek(f"kwota = cena planu ({_PLANY_ETYKIETA})", lambda d: d["kwota"] == d["kwota_planu"])],
    ),
)

ECOM_10 = Regula(
    sql=f"""
        WITH dni AS (SELECT unnest(generate_series($od::DATE, $dzien::DATE, INTERVAL 1 DAY))::DATE AS dzien),
        r AS (SELECT data_realizacji AS dzien, count(*) AS realizacje, sum(kwota) AS kwota_realizacji
              FROM karty_podarunkowe WHERE data_realizacji BETWEEN $od AND $dzien GROUP BY 1),
        t AS (SELECT data_czas::DATE AS dzien, count(*) AS n FROM pos_paragony
              WHERE metoda_platnosci = 'karta podarunkowa' AND data_czas::DATE BETWEEN $od AND $dzien GROUP BY 1
              UNION ALL
              SELECT {DZIEN_ZAMOWIENIA}, count(*) FROM ecom_zamowienia
              WHERE metoda_platnosci = 'karta podarunkowa' AND {DZIEN_ZAMOWIENIA} BETWEEN $od AND $dzien GROUP BY 1)
        SELECT d.dzien, coalesce(r.realizacje, 0) AS realizacje, coalesce(r.kwota_realizacji, 0) AS kwota_realizacji,
               coalesce(sum(t.n), 0) AS platnosci_karta_podarunkowa
        FROM dni d LEFT JOIN r USING (dzien) LEFT JOIN t USING (dzien) GROUP BY ALL
    """,
    schemat=KONTRAKT.schemat(
        "ECOM-10",
        checks=[
            warunek(
                "realizacje kart = płatności „karta podarunkowa” w POS i sklepie",
                lambda d: d["realizacje"] == d["platnosci_karta_podarunkowa"],
            )
        ],
    ),
)

ECOM_11 = Regula(
    sql=f"""
        WITH dni AS (SELECT unnest(generate_series($od::DATE, $dzien::DATE, INTERVAL 1 DAY))::DATE AS dzien),
        z AS (SELECT {DZIEN_ZAMOWIENIA} AS dzien, count(*) AS zamowienia,
                     max(hour(timezone('Europe/Warsaw', data_utc::TIMESTAMP AT TIME ZONE 'UTC'))) AS ostatnia_godzina_pl
              FROM ecom_zamowienia WHERE {DZIEN_ZAMOWIENIA} BETWEEN $od AND $dzien GROUP BY 1),
        s AS (SELECT {CZAS_PL_SUBSKRYPCJI}::DATE AS dzien, count(*) AS obciazenia FROM ecom_subskrypcje
              WHERE {CZAS_PL_SUBSKRYPCJI}::DATE BETWEEN $od AND $dzien GROUP BY 1)
        SELECT d.dzien, coalesce(z.zamowienia, 0) AS zamowienia, z.ostatnia_godzina_pl,
               coalesce(s.obciazenia, 0) AS obciazenia
        FROM dni d LEFT JOIN z USING (dzien) LEFT JOIN s USING (dzien)
    """,
    schemat=KONTRAKT.schemat(
        "ECOM-11",
        {
            "zamowienia": pa.Column("int64", pa.Check.gt(0, error="brak zamówień z dnia")),
            "obciazenia": pa.Column("int64", pa.Check.gt(0, error="brak obciążeń subskrypcji z dnia")),
            "ostatnia_godzina_pl": pa.Column(
                "int64",
                pa.Check.ge(
                    OSTATNIA_GODZINA_MIN, error=f"ostatnie zamówienie przed {OSTATNIA_GODZINA_MIN}:00 czasu polskiego"
                ),
                coerce=True,
            ),
        },
    ),
)

ECOM_12 = Regula(
    sql=f"""
        WITH d AS (SELECT {DZIEN_ZAMOWIENIA} AS dzien, count(*) AS zamowienia FROM ecom_zamowienia
                   WHERE {DZIEN_ZAMOWIENIA} BETWEEN $od::DATE - {DNI_HISTORII} AND $dzien GROUP BY 1)
        SELECT * FROM (
            SELECT *, median(zamowienia) OVER w AS mediana, count(*) OVER w AS dni_historii FROM d
            WINDOW w AS (ORDER BY dzien
                         RANGE BETWEEN INTERVAL {DNI_HISTORII} DAY PRECEDING AND INTERVAL 1 DAY PRECEDING))
        WHERE dzien >= $od AND dni_historii >= {MIN_DNI_HISTORII}
    """,
    schemat=KONTRAKT.schemat(
        "ECOM-12",
        checks=[
            warunek(
                f"zamówienia = {WOLUMEN_MIN}–{WOLUMEN_MAX} × mediana z {DNI_HISTORII} dni",
                lambda d: (d["zamowienia"] / d["mediana"]).between(WOLUMEN_MIN, WOLUMEN_MAX),
            )
        ],
    ),
)

REGULY = [ECOM_01, ECOM_02, ECOM_03, ECOM_04, ECOM_05, ECOM_06, ECOM_07, ECOM_08, ECOM_09, ECOM_10, ECOM_11, ECOM_12]
