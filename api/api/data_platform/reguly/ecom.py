"""Reguły jakości e-commerce: ecom_zamowienia, ecom_pozycje, ecom_produkty, ecom_subskrypcje, karty_podarunkowe.

Sklep zapisuje czas w UTC (`data_utc`, `data_platnosci`), a dzień biznesowy to Europe/Warsaw — zakres
liczymy po dniu polskim. Kwoty są brutto w walucie zamówienia (PLN lub EUR).
"""

import pandera.pandas as pa

from api.data_platform.reguly.regula import Poziom, Regula, Wlasciciel, meta, warunek

WALUTY = ["PLN", "EUR"]
METODY_PLATNOSCI = ["BLIK", "karta", "przelew", "pobranie", "karta podarunkowa"]
PLANY = {"miesięczny": 39.0, "roczny": 399.0}
# Subskrypcje obciąża nocny batch 00:00–03:00 czasu polskiego, czyli 22:00–01:59 UTC.
GODZINY_BATCHA_UTC = [22, 23, 0, 1]
NOTATKA_TESTOWA = r"test|nie realiz|nie wysyłać"
DOMENA_WEWNETRZNA = "@kawosz.pl"
MAKS_WIEK_KURSU_DNI = 7
# Liczba zamówień w dniu względem mediany z 28 dni (w historii: 0,37 w święta – 3,14 w Black Friday).
WOLUMEN_MIN, WOLUMEN_MAX = 0.3, 3.5

DZIEN_ZAMOWIENIA = "timezone('Europe/Warsaw', data_utc::TIMESTAMP AT TIME ZONE 'UTC')::DATE"
CZAS_PL_SUBSKRYPCJI = "timezone('Europe/Warsaw', data_platnosci AT TIME ZONE 'UTC')"
ZAMOWIENIA_W_ZAKRESIE = f"SELECT * FROM ecom_zamowienia WHERE {DZIEN_ZAMOWIENIA} BETWEEN $od AND $dzien"

ECOM_01 = Regula(
    sql=ZAMOWIENIA_W_ZAKRESIE,
    schemat=pa.DataFrameSchema(
        {
            "id": pa.Column("int64", unique=True),
            "data_utc": pa.Column("datetime64[ns]"),
            "waluta": pa.Column(str, pa.Check.isin(WALUTY)),
            "brutto": pa.Column("float64", pa.Check.gt(0)),
            "email": pa.Column(str, nullable=True),
            "notatka": pa.Column(str, nullable=True),
            "zwrot": pa.Column(bool),
            "metoda_platnosci": pa.Column(str, pa.Check.isin(METODY_PLATNOSCI)),
            # pola, których wymaga ECOM-07; gdy sklep je doda, typy dalej się zgadzają
            "data_zwrotu": pa.Column(pa.DateTime, nullable=True, required=False, coerce=True),
            "kwota_zwrotu": pa.Column(float, nullable=True, required=False, coerce=True),
        },
        checks=[
            warunek("pobranie tylko w PLN", lambda d: (d["metoda_platnosci"] != "pobranie") | (d["waluta"] == "PLN"))
        ],
        strict=True,
        name="ECOM-01",
        description="Zamówienie ma oczekiwane kolumny i typy, unikalne id, kwotę > 0, walutę i metodę ze słownika",
        metadata=meta(Poziom.BLOKUJE, Wlasciciel.ZESPOL_DANYCH, jednostka="zamówienie"),
    ),
)

ECOM_02 = Regula(
    sql=f"""
        SELECT z.id, z.waluta, z.brutto, coalesce(sum(p.ilosc * p.cena_brutto), 0) AS suma_pozycji
        FROM ecom_zamowienia z LEFT JOIN ecom_pozycje p ON p.id_zamowienia = z.id
        WHERE {DZIEN_ZAMOWIENIA} BETWEEN $od AND $dzien GROUP BY ALL
    """,
    schemat=pa.DataFrameSchema(
        checks=[warunek("brutto = Σ ilosc × cena_brutto", lambda d: (d["brutto"] - d["suma_pozycji"]).abs() < 0.005)],
        name="ECOM-02",
        description="Kwota brutto zamówienia równa się sumie jego pozycji (z dostawą)",
        metadata=meta(Poziom.BLOKUJE, Wlasciciel.ZESPOL_DANYCH, 25, jednostka="zamówienie"),
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
    schemat=pa.DataFrameSchema(
        {
            "ma_zamowienie": pa.Column(bool, pa.Check.eq(True, error="pozycja bez zamówienia")),
            "pozycje": pa.Column("int64", pa.Check.ge(1, error="zamówienie bez pozycji")),
            "pozycje_spoza_cennika": pa.Column("int64", pa.Check.eq(0, error="SKU spoza ecom_produkty (poza DOSTAWA)")),
            "wiersze_dostawy": pa.Column("int64", pa.Check.le(1, error="więcej niż jeden wiersz DOSTAWA")),
        },
        name="ECOM-03",
        description="Zamówienie ma pozycje, pozycja ma zamówienie, SKU jest w cenniku (wyjątek: jeden wiersz DOSTAWA)",
        metadata=meta(Poziom.BLOKUJE, Wlasciciel.ZESPOL_DANYCH, 30, jednostka="zamówienie"),
    ),
)

ECOM_04 = Regula(
    sql=f"""
        SELECT z.id, {DZIEN_ZAMOWIENIA} AS dzien, z.brutto, k.data AS data_kursu, k.eur_pln
        FROM ecom_zamowienia z ASOF LEFT JOIN kursy_nbp k ON {DZIEN_ZAMOWIENIA} > k.data
        WHERE z.waluta = 'EUR' AND {DZIEN_ZAMOWIENIA} BETWEEN $od AND $dzien
    """,
    schemat=pa.DataFrameSchema(
        {"eur_pln": pa.Column("float64", pa.Check.in_range(3.5, 5.5))},
        checks=[
            warunek(
                f"kurs z poprzedniego dnia roboczego, najwyżej {MAKS_WIEK_KURSU_DNI} dni wstecz",
                lambda d: (d["dzien"] - d["data_kursu"]).dt.days <= MAKS_WIEK_KURSU_DNI,
            )
        ],
        name="ECOM-04",
        description="Zamówienie w EUR ma kurs NBP z poprzedniego dnia roboczego, więc da się je przeliczyć na PLN",
        metadata=meta(Poziom.BLOKUJE, Wlasciciel.ZESPOL_DANYCH, 13, 33, jednostka="zamówienie w EUR"),
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
    schemat=pa.DataFrameSchema(
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
        name="ECOM-05",
        description="Zamówienie nie jest testowe: e-mail spoza @kawosz.pl, bez notatki testowej, ceny PLN z cennika",
        metadata=meta(Poziom.OSTRZEGA, Wlasciciel.ECOMMERCE, 18, jednostka="zamówienie"),
    ),
)

ECOM_06 = Regula(
    sql=f"SELECT id, metoda_platnosci, brutto, email FROM ({ZAMOWIENIA_W_ZAKRESIE})",
    schemat=pa.DataFrameSchema(
        {"email": pa.Column(str, pa.Check.str_matches(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$"))},
        name="ECOM-06",
        description="Zamówienie ma e-mail klienta (także przy pobraniu)",
        metadata=meta(Poziom.OSTRZEGA, Wlasciciel.ECOMMERCE, 9, jednostka="zamówienie"),
    ),
)

ECOM_07 = Regula(
    sql=f"SELECT * FROM ecom_zamowienia WHERE zwrot AND {DZIEN_ZAMOWIENIA} BETWEEN $od AND $dzien",
    schemat=pa.DataFrameSchema(
        # Kolumn dziś nie ma w sklepie — reguła jest wymaganiem wobec systemu.
        {
            "data_zwrotu": pa.Column(pa.DateTime, coerce=True),
            "kwota_zwrotu": pa.Column(float, pa.Check.gt(0), coerce=True),
        },
        name="ECOM-07",
        description="Zamówienie ze zwrotem ma datę i kwotę zwrotu",
        metadata=meta(Poziom.OSTRZEGA, Wlasciciel.ECOMMERCE, 7, jednostka="zamówienie ze zwrotem"),
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
    schemat=pa.DataFrameSchema(
        {"sku_o_tej_nazwie": pa.Column("int64", pa.Check.eq(1))},
        name="ECOM-08",
        description="Sprzedany produkt ma w cenniku sklepu nazwę, której nie nosi inny SKU",
        metadata=meta(Poziom.OSTRZEGA, Wlasciciel.ECOMMERCE, 6, jednostka="pozycja"),
    ),
)

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
    schemat=pa.DataFrameSchema(
        {
            "plan": pa.Column(str, pa.Check.isin(list(PLANY))),
            "obciazenia_w_miesiacu": pa.Column("int64", pa.Check.eq(1, error="więcej niż jedno obciążenie w miesiącu")),
            "godzina_zapisu": pa.Column(
                "int64", pa.Check.isin(GODZINY_BATCHA_UTC, error="godzina zapisu poza nocnym batchem w UTC (22–01)")
            ),
        },
        checks=[warunek("kwota = cena planu (39 / 399)", lambda d: d["kwota"] == d["kwota_planu"])],
        name="ECOM-09",
        description="Obciążenie subskrypcji ma kwotę swojego planu, jest jedno w miesiącu i ma czas zapisany w UTC",
        metadata=meta(Poziom.BLOKUJE, Wlasciciel.ECOMMERCE, 17, jednostka="obciążenie"),
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
    schemat=pa.DataFrameSchema(
        checks=[
            warunek(
                "realizacje kart = płatności „karta podarunkowa” w POS i sklepie",
                lambda d: d["realizacje"] == d["platnosci_karta_podarunkowa"],
            )
        ],
        name="ECOM-10",
        description="Każda realizacja karty podarunkowej ma w tym dniu płatność „karta podarunkowa” w POS lub sklepie",
        metadata=meta(Poziom.OSTRZEGA, Wlasciciel.ECOMMERCE, 31, jednostka="dzień"),
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
    schemat=pa.DataFrameSchema(
        {
            "zamowienia": pa.Column("int64", pa.Check.gt(0, error="brak zamówień z dnia")),
            "obciazenia": pa.Column("int64", pa.Check.gt(0, error="brak obciążeń subskrypcji z dnia")),
            # Ostatnie zamówienie dnia zawsze było po 23:00 czasu polskiego; wcześniejsze = dzień ucięty.
            "ostatnia_godzina_pl": pa.Column(
                "int64", pa.Check.ge(22, error="ostatnie zamówienie przed 22:00 czasu polskiego"), coerce=True
            ),
        },
        name="ECOM-11",
        description=(
            "Każdy dzień do dnia eksportu ma zamówienia do późnego wieczora (czas polski) i obciążenia subskrypcji"
        ),
        metadata=meta(Poziom.BLOKUJE, Wlasciciel.ZESPOL_DANYCH, 17, jednostka="dzień"),
    ),
)

ECOM_12 = Regula(
    sql=f"""
        WITH d AS (SELECT {DZIEN_ZAMOWIENIA} AS dzien, count(*) AS zamowienia FROM ecom_zamowienia
                   WHERE {DZIEN_ZAMOWIENIA} BETWEEN $od::DATE - 28 AND $dzien GROUP BY 1)
        SELECT * FROM (
            SELECT *, median(zamowienia) OVER w AS mediana_28_dni, count(*) OVER w AS dni_historii FROM d
            WINDOW w AS (ORDER BY dzien RANGE BETWEEN INTERVAL 28 DAY PRECEDING AND INTERVAL 1 DAY PRECEDING))
        WHERE dzien >= $od AND dni_historii >= 14
    """,
    schemat=pa.DataFrameSchema(
        checks=[
            warunek(
                f"zamówienia = {WOLUMEN_MIN}–{WOLUMEN_MAX} × mediana z 28 dni",
                lambda d: (d["zamowienia"] / d["mediana_28_dni"]).between(WOLUMEN_MIN, WOLUMEN_MAX),
            )
        ],
        name="ECOM-12",
        description=f"Liczba zamówień w dniu mieści się w {WOLUMEN_MIN}–{WOLUMEN_MAX} × mediany z 28 poprzednich dni",
        metadata=meta(Poziom.OSTRZEGA, Wlasciciel.ZESPOL_DANYCH, jednostka="dzień"),
    ),
)

REGULY = [ECOM_01, ECOM_02, ECOM_03, ECOM_04, ECOM_05, ECOM_06, ECOM_07, ECOM_08, ECOM_09, ECOM_10, ECOM_11, ECOM_12]
