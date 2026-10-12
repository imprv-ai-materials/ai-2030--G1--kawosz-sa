"""Reguły jakości POS: pos_paragony (pliki z kas), pos_pliki (rejestr plików), pos_pozycje, pos_produkty, lokale.

Opisy, poziomy, właściciele, słowniki i progi reguł są w kontrakcie kontrakty/pos_paragony.yaml.
Tu jest tylko SQL, który przygotowuje ramkę, i warunki, które ją sprawdzają.

Dzień paragonu to data z `data_czas` (czas lokalny kasy). `pos_pozycje` nie ma daty, więc dzień
pozycji odczytujemy z `nr_paragonu` (RRMMDD + numer kolejny). Dzień pliku jest w jego nazwie.
"""

import pandas as pd
import pandera.pandas as pa
from dateutil.easter import easter

from api.data_platform.kontrakty.kontrakt import wczytaj
from api.data_platform.reguly.regula import Regula, warunek

KONTRAKT = wczytaj("pos_paragony")
METODY_PLATNOSCI = KONTRAKT.kolumna("metoda_platnosci").dozwolone
STAWKI_VAT, CENA_RECZNA_MAX, MAX_SZTUK = (
    KONTRAKT.parametry("POS-06")[p] for p in ("stawki_vat", "cena_reczna_max", "max_sztuk")
)
DNI_ZAMKNIETE = KONTRAKT.parametry("POS-10")["dni_zamkniete"]
WOLUMEN_MIN, WOLUMEN_MAX, DNI_HISTORII, MIN_DNI_HISTORII = (
    KONTRAKT.parametry("POS-11")[p] for p in ("wolumen_min", "wolumen_max", "dni_historii", "min_dni_historii")
)

DZIEN_POZYCJI = "strptime((nr_paragonu // 10000)::VARCHAR, '%y%m%d')::DATE"
PARAGONY_W_ZAKRESIE = "SELECT * FROM pos_paragony WHERE data_czas::DATE BETWEEN $od AND $dzien"


def _lista_sql(wartosci: list[str]) -> str:
    return "[" + ", ".join(f"'{w}'" for w in wartosci) + "]"


def _plik_sql(kolumna_dnia: str) -> str:
    """Nazwa pliku wg wzorca z kontraktu, np. pos_paragony_{lokal}_{dzien}.csv, jako wyrażenie SQL."""
    wzorzec = KONTRAKT.dostawa.plik.replace("{lokal}", "' || lokal || '")
    return "'" + wzorzec.replace("{dzien}", f"' || strftime({kolumna_dnia}, '%Y-%m-%d') || '") + "'"


def _dzien_zamkniety(dni: pd.Series) -> pd.Series:
    """Dni zamknięte lokali z kontraktu (POS-10): „D.MM” albo „Wielkanoc”."""
    zamkniety = pd.Series(False, index=dni.index)
    for dzien in DNI_ZAMKNIETE:
        if dzien == "Wielkanoc":
            zamkniety |= dni.isin([pd.Timestamp(easter(rok)) for rok in dni.dt.year.unique()])
        else:
            d, m = map(int, dzien.split("."))
            zamkniety |= dni.dt.day.eq(d) & dni.dt.month.eq(m)
    return zamkniety


POS_01 = Regula(
    sql=PARAGONY_W_ZAKRESIE,
    # Kolumny spoza kontraktu (np. `kanal`) są w tabeli, bo loader łączy pliki po nazwach kolumn. Tu nie są
    # błędem: to, który plik je przysłał, sprawdza POS-12 na rejestrze plików.
    schemat=KONTRAKT.schemat("POS-01", {**KONTRAKT.kolumny_pandera(), "plik": pa.Column(str)}),
)

POS_02 = Regula(
    # Duplikatem jest drugi wiersz z kolei; kopia pliku ma dopisek w nazwie („… (1).csv”), więc idzie druga.
    sql=f"""
        SELECT lokal, nr_paragonu, data_czas, kwota_brutto, plik FROM ({PARAGONY_W_ZAKRESIE})
        ORDER BY lokal, nr_paragonu, length(plik), plik
    """,
    schemat=KONTRAKT.schemat(
        "POS-02",
        {"lokal": pa.Column("int32"), "nr_paragonu": pa.Column("int64")},
        unique=["lokal", "nr_paragonu"],
        report_duplicates="exclude_first",
    ),
)

POS_03 = Regula(
    sql=f"""
        SELECT lokal, nr_paragonu, data_czas, storno, kwota_brutto, plik,
               {_plik_sql("data_czas")} AS plik_oczekiwany,
               nr_paragonu // 10000 AS data_w_numerze,
               strftime(data_czas, '%y%m%d')::BIGINT AS data_paragonu,
               -- storna kasa dopisuje na końcu dnia, więc kolejność sprawdzamy tylko dla pozostałych paragonów
               CASE WHEN storno = 0 THEN max(data_czas) FILTER (WHERE storno = 0) OVER (
                   PARTITION BY lokal, data_czas::DATE ORDER BY nr_paragonu
                   ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) END AS najpozniej_wczesniejszy
        FROM pos_paragony WHERE data_czas::DATE BETWEEN $od AND $dzien
    """,
    schemat=KONTRAKT.schemat(
        "POS-03",
        checks=[
            warunek(
                f"plik = {KONTRAKT.dostawa.plik.replace('{dzien}', '{dzień}')}",
                lambda d: d["plik"] == d["plik_oczekiwany"],
            ),
            warunek("data w numerze paragonu = data paragonu", lambda d: d["data_w_numerze"] == d["data_paragonu"]),
            warunek(
                "numer paragonu rośnie z czasem",
                lambda d: d["najpozniej_wczesniejszy"].isna() | (d["data_czas"] >= d["najpozniej_wczesniejszy"]),
            ),
        ],
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
    schemat=KONTRAKT.schemat(
        "POS-04",
        checks=[
            warunek(
                "Σ kwota_brutto = Σ ilosc × cena_brutto",
                lambda d: (d["suma_naglowkow"] - d["suma_pozycji"]).abs() < 0.005,
            ),
            warunek(
                "liczba paragonów = liczba paragonów w pozycjach", lambda d: d["paragony"] == d["paragony_w_pozycjach"]
            ),
        ],
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
    schemat=KONTRAKT.schemat(
        "POS-05",
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
    ),
)

POS_06 = Regula(
    sql=f"""
        SELECT p.lokal, p.nr_paragonu, {DZIEN_POZYCJI} AS dzien, p.kod_produktu, p.ilosc, p.cena_brutto, p.vat,
               pr.cena_brutto AS cena_cennik, pr.vat AS vat_cennik
        FROM pos_pozycje p JOIN pos_produkty pr USING (kod_produktu)
        WHERE {DZIEN_POZYCJI} BETWEEN $od AND $dzien
    """,
    schemat=KONTRAKT.schemat(
        "POS-06",
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
    ),
)

POS_07 = Regula(
    sql=f"SELECT lokal, nr_paragonu, data_czas, kwota_brutto, metoda_platnosci FROM ({PARAGONY_W_ZAKRESIE})",
    schemat=KONTRAKT.schemat(
        "POS-07", {"metoda_platnosci": KONTRAKT.kolumna("metoda_platnosci").pandera(nullable=False)}
    ),
)

POS_08 = Regula(
    sql=f"""
        WITH p AS (SELECT lokal, nr_paragonu, count(*) FILTER (WHERE ilosc < 0) AS pozycje_ujemne
                   FROM pos_pozycje WHERE {DZIEN_POZYCJI} BETWEEN $od AND $dzien GROUP BY ALL)
        SELECT r.lokal, r.nr_paragonu, r.data_czas, r.storno, r.kwota_brutto,
               coalesce(p.pozycje_ujemne, 0) AS pozycje_ujemne
        FROM pos_paragony r LEFT JOIN p USING (lokal, nr_paragonu)
        WHERE r.data_czas::DATE BETWEEN $od AND $dzien AND (r.storno = 1 OR r.kwota_brutto < 0 OR p.pozycje_ujemne > 0)
    """,
    schemat=KONTRAKT.schemat(
        "POS-08",
        checks=[
            # zwrot towaru to pozycja z ujemną ilością — także w paragonie z dodatnią sumą (zakup + zwrot)
            warunek(
                "ujemna ilość lub kwota bez storno = 1",
                lambda d: (d["storno"] == 1) | ((d["pozycje_ujemne"] == 0) & (d["kwota_brutto"] >= 0)),
            ),
            warunek("storno = 1 z kwotą nieujemną", lambda d: (d["storno"] == 0) | (d["kwota_brutto"] < 0)),
        ],
    ),
)

POS_09 = Regula(
    sql="SELECT * FROM pos_paragony WHERE storno = 1 AND data_czas::DATE BETWEEN $od AND $dzien",
    # Kolumna jest w kontrakcie jako opcjonalna, ale storno musi ją mieć: dziś kasa jej nie przysyła.
    schemat=KONTRAKT.schemat(
        "POS-09",
        {
            "nr_paragonu_stornowanego": KONTRAKT.kolumna("nr_paragonu_stornowanego").pandera(
                nullable=False, required=True
            )
        },
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
    schemat=KONTRAKT.schemat(
        "POS-10",
        checks=[
            warunek(
                f"lokal ma paragony z dnia (dni zamknięte: {', '.join(DNI_ZAMKNIETE)})",
                lambda d: (d["paragony"] > 0) | _dzien_zamkniety(d["dzien"]),
            )
        ],
    ),
)

POS_11 = Regula(
    sql=f"""
        WITH d AS (SELECT lokal, data_czas::DATE AS dzien, count(*) AS paragony FROM pos_paragony
                   WHERE data_czas::DATE BETWEEN $od::DATE - {DNI_HISTORII} AND $dzien GROUP BY ALL)
        SELECT * FROM (
            SELECT *, median(paragony) OVER w AS mediana, count(*) OVER w AS dni_historii FROM d
            WINDOW w AS (PARTITION BY lokal ORDER BY dzien
                         RANGE BETWEEN INTERVAL {DNI_HISTORII} DAY PRECEDING AND INTERVAL 1 DAY PRECEDING))
        WHERE dzien >= $od AND dni_historii >= {MIN_DNI_HISTORII}
    """,
    schemat=KONTRAKT.schemat(
        "POS-11",
        checks=[
            warunek(
                f"paragony = {WOLUMEN_MIN}–{WOLUMEN_MAX} × mediana z {DNI_HISTORII} dni",
                lambda d: (d["paragony"] / d["mediana"]).between(WOLUMEN_MIN, WOLUMEN_MAX),
            )
        ],
    ),
)

_KOLUMNY = _lista_sql([k.nazwa for k in KONTRAKT.kolumny])
POS_12 = Regula(
    # Jeden wiersz na plik × kolumnę: kolumny z nagłówka pliku i wymagane kolumny kontraktu. Kolejność
    # porównujemy tylko między kolumnami z kontraktu, więc wstawiona obca kolumna nie oznacza całego pliku.
    sql=f"""
        WITH p AS (SELECT plik, lokal, dzien, kolumny,
                          list_filter(kolumny, c -> list_contains({_KOLUMNY}, c)) AS kontraktowe_wg_pliku,
                          list_filter({_KOLUMNY}, c -> list_contains(kolumny, c)) AS kontraktowe_wg_kontraktu
                   FROM pos_pliki WHERE dzien BETWEEN $od AND $dzien)
        SELECT plik, lokal, dzien, kolumna,
               list_contains({_KOLUMNY}, kolumna) AS w_kontrakcie,
               list_contains(kolumny, kolumna) AS w_pliku,
               list_position(kontraktowe_wg_pliku, kolumna)
                   IS NOT DISTINCT FROM list_position(kontraktowe_wg_kontraktu, kolumna) AS kolejnosc_zgodna,
               kolumny[list_position(kolumny, kolumna) - 1] AS po_kolumnie,
               array_to_string(kolumny, '{KONTRAKT.dostawa.separator}') AS naglowek_pliku
        FROM p, unnest(list_distinct(list_concat(kolumny, {_lista_sql(KONTRAKT.wymagane)}))) AS k(kolumna)
    """,
    schemat=KONTRAKT.schemat(
        "POS-12",
        {
            "w_kontrakcie": pa.Column(bool, pa.Check.eq(True, error="kolumna spoza kontraktu")),
            "w_pliku": pa.Column(bool, pa.Check.eq(True, error="brak kolumny z kontraktu")),
            "kolejnosc_zgodna": pa.Column(bool, pa.Check.eq(True, error="kolumna w innej kolejności niż w kontrakcie")),
        },
    ),
)

POS_13 = Regula(
    # Pliki bez czasu dostawy (archiwum) pomijamy: nie wiadomo, kiedy dotarły. Czas dostawy jest lokalny (Warszawa).
    sql=f"""
        SELECT plik, lokal, dzien, czas_dostawy,
               (dzien + {KONTRAKT.dostawa.dni_po}) + TIME '{KONTRAKT.dostawa.godzina}' AS termin
        FROM pos_pliki WHERE dzien BETWEEN $od AND $dzien AND czas_dostawy IS NOT NULL
    """,
    schemat=KONTRAKT.schemat(
        "POS-13",
        checks=[
            warunek(
                f"plik dotarł w terminie ({KONTRAKT.dostawa.termin})", lambda d: d["czas_dostawy"] <= d["termin"]
            )
        ],
    ),
)

REGULY = [POS_01, POS_02, POS_03, POS_04, POS_05, POS_06, POS_07, POS_08, POS_09, POS_10, POS_11, POS_12, POS_13]
