"""Reguły jakości ERP: erp_faktury, erp_pozycje, erp_platnosci, erp_kartoteka, erp_kontrahenci (+ archiwum).

Kwoty ERP są netto w PLN, `vat` to kwota podatku, płatność to brutto. Dzień dokumentu to `data`.
Kartotekę i kontrahentów sprawdzamy przez dokumenty z zakresu: co noc tylko to, czego dotyczą nowe faktury.
"""

import pandas as pd
import pandera.pandas as pa

from api.data_platform.reguly.regula import Poziom, Regula, Wlasciciel, meta, warunek

STAWKA_PODSTAWOWA = 23
# Indeksy ze stawką inną niż podstawowa. Kartoteka nie ma kolumny ze stawką, więc listę prowadzi księgowość.
STAWKI_VAT_INDEKSOW = {
    "20.01.0001": 5,  # MLEKO UHT 3,2% 1L — stawka obniżona do potwierdzenia (skala #12)
}
WAGI_NIP = (6, 5, 7, 2, 3, 4, 5, 6, 7)
# Faktura większa niż 8 × mediana faktur klienta z 365 dni (w historii: jedna, następna ma 5,6 ×).
KROTNOSC_MEDIANY_KLIENTA = 8
# Liczba faktur w miesiącu względem mediany z 3 poprzednich miesięcy (w historii: 1 359–1 431 faktur).
WOLUMEN_MIN, WOLUMEN_MAX = 0.9, 1.1

FAKTURY_W_ZAKRESIE = "SELECT * FROM erp_faktury WHERE data BETWEEN $od AND $dzien"
KONTRAHENCI = """
    SELECT id_kontrahenta, nazwa, nip, id_biura_crm, regexp_replace(nip, '[^0-9]', '', 'g') AS nip10,
           trim(regexp_replace(upper(adres), '\\s+', ' ', 'g')) || '|' || kod_pocztowy AS adres_kod
    FROM erp_kontrahenci
    UNION ALL
    SELECT id_kontrahenta, nazwa, nip, id_biura_crm, regexp_replace(nip, '[^0-9]', '', 'g'),
           trim(regexp_replace(upper(adres), '\\s+', ' ', 'g')) || '|' || kod_pocztowy
    FROM erp_kontrahenci_archiwum
"""


def _nip_poprawny(nip10: pd.Series) -> pd.Series:
    """10 cyfr i suma kontrolna: Σ cyfra × waga mod 11 = ostatnia cyfra."""
    dziesiec_cyfr = nip10.str.fullmatch(r"\d{10}").fillna(False).astype(bool)
    cyfry = nip10.where(dziesiec_cyfr, "0" * 10)
    suma = sum(cyfry.str[i].astype(int) * waga for i, waga in enumerate(WAGI_NIP))
    return dziesiec_cyfr & (suma % 11 == cyfry.str[9].astype(int))


ERP_01 = Regula(
    sql=FAKTURY_W_ZAKRESIE,
    schemat=pa.DataFrameSchema(
        {
            "nr_faktury": pa.Column(
                str, pa.Check.str_matches(r"^(FV/\d{4}/\d{2}/\d{5}|KOR/\d{4}/\d{2}/\d{4})$"), unique=True
            ),
            "id_kontrahenta": pa.Column("int64"),
            "data": pa.Column("datetime64[us]"),
            "typ": pa.Column(str, pa.Check.isin(["faktura", "korekta"])),
            "waluta": pa.Column(str, pa.Check.eq("PLN")),
            "kwota_netto": pa.Column("float64"),
            "vat": pa.Column("float64"),
        },
        checks=[
            warunek(
                "rok i miesiąc w numerze = data",
                lambda d: d["nr_faktury"].str.split("/").str[1:3].str.join("-") == d["data"].dt.strftime("%Y-%m"),
            ),
            warunek(
                "FV/ ⇔ faktura, KOR/ ⇔ korekta",
                lambda d: d["nr_faktury"].str.startswith("FV/") == (d["typ"] == "faktura"),
            ),
            warunek("faktura > 0, korekta < 0", lambda d: (d["kwota_netto"] > 0) == (d["typ"] == "faktura")),
        ],
        strict=True,
        name="ERP-01",
        description=(
            "Dokument ma oczekiwane kolumny i typy, unikalny numer FV/KOR zgodny z datą, PLN i znak kwoty wg typu"
        ),
        metadata=meta(Poziom.BLOKUJE, Wlasciciel.FINANSE),
    ),
)

ERP_02 = Regula(
    sql="""
        SELECT f.nr_faktury, f.typ, f.data, f.kwota_netto, f.vat, p.kwota AS platnosc, p.data_platnosci,
               count(p.nr_faktury) OVER (PARTITION BY f.nr_faktury) AS platnosci
        FROM erp_faktury f LEFT JOIN erp_platnosci p USING (nr_faktury)
        WHERE f.data BETWEEN $od AND $dzien
    """,
    schemat=pa.DataFrameSchema(
        {"platnosci": pa.Column("int64", pa.Check.le(1, error="więcej niż jedna płatność za fakturę"))},
        checks=[
            warunek(
                f"VAT ma znak netto i nie przekracza {STAWKA_PODSTAWOWA}% netto",
                lambda d: (d["vat"] * d["kwota_netto"] >= 0)
                & (d["vat"].abs() <= d["kwota_netto"].abs() * STAWKA_PODSTAWOWA / 100 + 0.01),
            ),
            warunek(
                "płatność = netto + VAT",
                lambda d: d["platnosc"].isna() | ((d["platnosc"] - d["kwota_netto"] - d["vat"]).abs() <= 0.01),
            ),
            warunek(
                "płatność nie wcześniej niż faktura",
                lambda d: d["data_platnosci"].isna() | (d["data_platnosci"] >= d["data"]),
            ),
        ],
        name="ERP-02",
        description="Netto + VAT = brutto: VAT w granicach stawki, jedna płatność równa netto + VAT, nie przed fakturą",
        metadata=meta(Poziom.BLOKUJE, Wlasciciel.FINANSE, 3),
    ),
)

_STAWKI_SQL = ", ".join(f"('{indeks}', {stawka})" for indeks, stawka in STAWKI_VAT_INDEKSOW.items())
ERP_03 = Regula(
    sql=f"""
        WITH s(indeks, stawka) AS (VALUES {_STAWKI_SQL}),
        p AS (SELECT nr_faktury, count(*) AS pozycje,
                     string_agg(DISTINCT indeks, ', ') FILTER (WHERE s.stawka IS NOT NULL) AS indeksy_stawka_inna,
                     sum(ilosc * cena * coalesce(s.stawka, {STAWKA_PODSTAWOWA}) / 100) AS vat_wg_stawek
              FROM erp_pozycje LEFT JOIN s USING (indeks) GROUP BY 1)
        SELECT f.nr_faktury, f.data, f.kwota_netto, f.vat, p.vat_wg_stawek, p.indeksy_stawka_inna
        FROM erp_faktury f JOIN p USING (nr_faktury) WHERE f.data BETWEEN $od AND $dzien
    """,
    schemat=pa.DataFrameSchema(
        checks=[
            warunek("VAT = Σ netto pozycji × stawka indeksu", lambda d: (d["vat"] - d["vat_wg_stawek"]).abs() <= 0.02)
        ],
        name="ERP-03",
        description="VAT dokumentu zgadza się ze stawkami indeksów (stawki inne niż 23% wpisuje księgowość)",
        metadata=meta(Poziom.OSTRZEGA, Wlasciciel.FINANSE, 12),
    ),
)

ERP_04 = Regula(
    sql="""
        WITH p AS (SELECT nr_faktury, sum(ilosc * cena) AS suma_pozycji FROM erp_pozycje GROUP BY 1)
        SELECT f.nr_faktury, f.typ, f.kwota_netto, coalesce(p.suma_pozycji, 0) AS suma_pozycji
        FROM erp_faktury f LEFT JOIN p USING (nr_faktury) WHERE f.data BETWEEN $od AND $dzien
    """,
    schemat=pa.DataFrameSchema(
        checks=[
            warunek(
                "kwota_netto = Σ ilosc × cena (±1 gr)", lambda d: (d["kwota_netto"] - d["suma_pozycji"]).abs() <= 0.01
            )
        ],
        name="ERP-04",
        description="Kwota netto dokumentu równa się sumie jego pozycji",
        metadata=meta(Poziom.BLOKUJE, Wlasciciel.ZESPOL_DANYCH, 25),
    ),
)

ERP_05 = Regula(
    sql="""
        WITH f AS (SELECT * FROM erp_faktury WHERE data BETWEEN $od AND $dzien),
        p AS (SELECT nr_faktury, count(*) AS pozycje,
                     count(*) FILTER (WHERE k.indeks IS NULL) AS pozycje_spoza_kartoteki
              FROM erp_pozycje LEFT JOIN erp_kartoteka k USING (indeks) GROUP BY 1)
        SELECT f.nr_faktury, true AS ma_dokument, coalesce(p.pozycje, 0) AS pozycje,
               coalesce(p.pozycje_spoza_kartoteki, 0) AS pozycje_spoza_kartoteki,
               (f.id_kontrahenta IN (SELECT id_kontrahenta FROM erp_kontrahenci))::INT
             + (f.id_kontrahenta IN (SELECT id_kontrahenta FROM erp_kontrahenci_archiwum))::INT AS kontrahent_w_tabelach
        FROM f LEFT JOIN p USING (nr_faktury)
        UNION ALL  -- pozycje i płatności bez dokumentu (cała tabela, bo nie mają własnej daty)
        SELECT nr_faktury, false, NULL, NULL, NULL FROM (
            SELECT nr_faktury FROM erp_pozycje UNION SELECT nr_faktury FROM erp_platnosci)
        ANTI JOIN erp_faktury USING (nr_faktury)
    """,
    schemat=pa.DataFrameSchema(
        {"ma_dokument": pa.Column(bool, pa.Check.eq(True, error="pozycja lub płatność bez dokumentu"))},
        checks=[
            warunek("dokument ma pozycje", lambda d: ~d["ma_dokument"] | (d["pozycje"] >= 1)),
            warunek(
                "indeks pozycji jest w kartotece", lambda d: ~d["ma_dokument"] | (d["pozycje_spoza_kartoteki"] == 0)
            ),
            warunek(
                "kontrahent jest w dokładnie jednej z tabel: aktywni, archiwum",
                lambda d: ~d["ma_dokument"] | (d["kontrahent_w_tabelach"] == 1),
            ),
        ],
        name="ERP-05",
        description=(
            "Dokument ma pozycje z kartoteki i kontrahenta (aktywni "
            "albo archiwum); pozycje i płatności mają dokument"
        ),
        metadata=meta(Poziom.BLOKUJE, Wlasciciel.ZESPOL_DANYCH, 32),
    ),
)

ERP_06 = Regula(
    sql="""
        SELECT p.nr_faktury, p.indeks, k.nazwa, k.kategoria, p.ilosc * p.cena AS netto
        FROM erp_pozycje p JOIN erp_faktury f USING (nr_faktury) JOIN erp_kartoteka k USING (indeks)
        WHERE f.data BETWEEN $od AND $dzien
    """,
    schemat=pa.DataFrameSchema(
        {"kategoria": pa.Column(str)},
        name="ERP-06",
        description="Indeks sprzedany na dokumencie ma kategorię w kartotece",
        metadata=meta(Poziom.BLOKUJE, Wlasciciel.KARTOTEKA, 1),
    ),
)

ERP_07 = Regula(
    sql="""
        WITH k AS (SELECT *, count(*) OVER (PARTITION BY trim(regexp_replace(upper(nazwa), '\\s+', ' ', 'g')))
                                 AS indeksy_o_tej_nazwie
                   FROM erp_kartoteka)
        SELECT p.nr_faktury, p.indeks, k.nazwa, k.kategoria, k.indeksy_o_tej_nazwie
        FROM erp_pozycje p JOIN erp_faktury f USING (nr_faktury) JOIN k USING (indeks)
        WHERE f.data BETWEEN $od AND $dzien
    """,
    schemat=pa.DataFrameSchema(
        {"indeksy_o_tej_nazwie": pa.Column("int64", pa.Check.eq(1))},
        name="ERP-07",
        description="Nazwa sprzedanego indeksu jest w kartotece jedna (bez drugiego indeksu o tej samej nazwie)",
        metadata=meta(Poziom.OSTRZEGA, Wlasciciel.KARTOTEKA, 20),
    ),
)

ERP_08 = Regula(
    sql=f"""
        WITH k AS (SELECT *, min(id_kontrahenta) OVER (PARTITION BY nip10) AS najstarszy_z_tym_nip,
                             min(id_kontrahenta) OVER (PARTITION BY adres_kod) AS najstarszy_pod_adresem
                   FROM ({KONTRAHENCI}))
        SELECT f.nr_faktury, f.data, f.kwota_netto, k.id_kontrahenta, k.nazwa, k.nip,
               k.najstarszy_z_tym_nip, k.najstarszy_pod_adresem
        FROM erp_faktury f JOIN k USING (id_kontrahenta) WHERE f.data BETWEEN $od AND $dzien
    """,
    schemat=pa.DataFrameSchema(
        checks=[
            warunek(
                "brak starszego kontrahenta z tym samym NIP-em",
                lambda d: d["id_kontrahenta"] == d["najstarszy_z_tym_nip"],
            ),
            warunek(
                "brak starszego kontrahenta pod tym samym adresem",
                lambda d: d["id_kontrahenta"] == d["najstarszy_pod_adresem"],
            ),
        ],
        name="ERP-08",
        description=(
            "Dokument trafia na główny rekord kontrahenta, a nie na drugi rekord tej samej firmy (NIP lub adres)"
        ),
        metadata=meta(Poziom.BLOKUJE, Wlasciciel.SPRZEDAZ_B2B, 4, 27),
    ),
)

ERP_09 = Regula(
    sql=f"""
        SELECT f.nr_faktury, f.data, k.id_kontrahenta, k.nazwa, k.nip, k.nip10
        FROM erp_faktury f JOIN ({KONTRAHENCI}) k USING (id_kontrahenta) WHERE f.data BETWEEN $od AND $dzien
    """,
    schemat=pa.DataFrameSchema(
        {"nip10": pa.Column(str, pa.Check(_nip_poprawny, error="NIP: 10 cyfr i poprawna suma kontrolna"))},
        name="ERP-09",
        description="Kontrahent dokumentu ma NIP z 10 cyframi i poprawną sumą kontrolną",
        metadata=meta(Poziom.OSTRZEGA, Wlasciciel.FINANSE, 14),
    ),
)

ERP_10 = Regula(
    sql=f"""
        WITH k AS (SELECT *, CASE WHEN id_biura_crm IS NOT NULL THEN count(*) OVER (PARTITION BY id_biura_crm) END
                               AS kontrahenci_z_tym_crm
                   FROM ({KONTRAHENCI}))
        SELECT f.nr_faktury, f.data, f.kwota_netto, k.id_kontrahenta, k.nazwa, k.id_biura_crm, k.kontrahenci_z_tym_crm
        FROM erp_faktury f JOIN k USING (id_kontrahenta) WHERE f.data BETWEEN $od AND $dzien
    """,
    schemat=pa.DataFrameSchema(
        {
            "id_biura_crm": pa.Column(str),
            "kontrahenci_z_tym_crm": pa.Column(
                float, pa.Check.eq(1, error="ID z CRM przypięte do kilku kontrahentów"), nullable=True, coerce=True
            ),
        },
        name="ERP-10",
        description="Kontrahent dokumentu ma ID biura z CRM i jest jedynym kontrahentem z tym ID",
        metadata=meta(Poziom.OSTRZEGA, Wlasciciel.SPRZEDAZ_B2B, 2, 4),
    ),
)

ERP_11 = Regula(
    sql="""
        SELECT * FROM (
            SELECT nr_faktury, id_kontrahenta, data, kwota_netto,
                   median(kwota_netto) OVER w AS mediana_klienta_365_dni, count(*) OVER w AS faktury_klienta_365_dni
            FROM erp_faktury WHERE typ = 'faktura' AND data BETWEEN $od::DATE - 365 AND $dzien
            WINDOW w AS (PARTITION BY id_kontrahenta ORDER BY data
                         RANGE BETWEEN INTERVAL 365 DAY PRECEDING AND INTERVAL 1 DAY PRECEDING))
        WHERE data >= $od
    """,
    schemat=pa.DataFrameSchema(
        checks=[
            warunek(
                f"netto ≤ {KROTNOSC_MEDIANY_KLIENTA} × mediana faktur klienta z 365 dni",
                lambda d: (d["faktury_klienta_365_dni"] < 3)
                | (d["kwota_netto"] <= KROTNOSC_MEDIANY_KLIENTA * d["mediana_klienta_365_dni"]),
            )
        ],
        name="ERP-11",
        description=(
            f"Faktura nie przekracza {KROTNOSC_MEDIANY_KLIENTA} × mediany faktur klienta z 365 dni (do weryfikacji)"
        ),
        metadata=meta(Poziom.OSTRZEGA, Wlasciciel.FINANSE, 23),
    ),
)

ERP_12 = Regula(
    sql="SELECT * FROM erp_faktury WHERE typ = 'korekta' AND data BETWEEN $od AND $dzien",
    schemat=pa.DataFrameSchema(
        # Kolumny dziś nie ma w ERP — reguła jest wymaganiem wobec systemu.
        {"nr_faktury_korygowanej": pa.Column(str, pa.Check.str_matches(r"^FV/\d{4}/\d{2}/\d{5}$"))},
        name="ERP-12",
        description="Korekta wskazuje numer faktury, którą koryguje",
        metadata=meta(Poziom.OSTRZEGA, Wlasciciel.FINANSE, 16),
    ),
)

ERP_13 = Regula(
    sql="""
        SELECT $dzien::DATE AS dzien,
               (SELECT max(data_platnosci) FROM erp_platnosci WHERE data_platnosci <= $dzien) AS ostatnia_platnosc,
               (SELECT max(data) FROM erp_faktury WHERE data <= $dzien) AS ostatni_dokument
    """,
    schemat=pa.DataFrameSchema(
        checks=[
            # Płatności księgowane są w dni robocze; najdłuższa przerwa w historii (święta) to 5 dni.
            warunek(
                "ostatnia płatność nie starsza niż 5 dni", lambda d: (d["dzien"] - d["ostatnia_platnosc"]).dt.days <= 5
            ),
            # Faktury idą hurtem w ostatni dzień roboczy miesiąca, w środku miesiąca pojedyncze.
            warunek(
                "ostatni dokument nie starszy niż 35 dni", lambda d: (d["dzien"] - d["ostatni_dokument"]).dt.days <= 35
            ),
        ],
        name="ERP-13",
        description="Dane ERP są świeże: płatności z ostatnich 5 dni, dokumenty z ostatnich 35 dni",
        metadata=meta(Poziom.BLOKUJE, Wlasciciel.ZESPOL_DANYCH),
    ),
)

ERP_14 = Regula(
    sql="""
        WITH m AS (SELECT unnest(generate_series(date_trunc('month', $od::DATE) - INTERVAL 3 MONTH,
                                                 date_trunc('month', $dzien::DATE), INTERVAL 1 MONTH))::DATE
                              AS miesiac),
        f AS (SELECT date_trunc('month', data)::DATE AS miesiac, count(*) AS faktury
              FROM erp_faktury WHERE typ = 'faktura' AND data <= $dzien GROUP BY 1),
        k AS (SELECT m.miesiac, coalesce(f.faktury, 0) AS faktury,
                     median(coalesce(f.faktury, 0)) OVER (ORDER BY m.miesiac ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING)
                         AS mediana_3_mies,
                     -- faktury idą w ostatni dzień roboczy: sobota i niedziela przesuwają go na piątek
                     last_day(m.miesiac) - CASE dayofweek(last_day(m.miesiac)) WHEN 6 THEN 1 WHEN 0 THEN 2 ELSE 0 END
                         AS ostatni_dzien_roboczy
              FROM m LEFT JOIN f USING (miesiac))
        SELECT * FROM k WHERE ostatni_dzien_roboczy BETWEEN $od AND $dzien
    """,
    schemat=pa.DataFrameSchema(
        checks=[
            # mediana 0 = brak historii (początek danych); przerwę w dostawach łapie ERP-13
            warunek(
                f"faktury = {WOLUMEN_MIN}–{WOLUMEN_MAX} × mediana z 3 miesięcy",
                lambda d: (d["mediana_3_mies"] == 0)
                | (d["faktury"] / d["mediana_3_mies"]).between(WOLUMEN_MIN, WOLUMEN_MAX),
            )
        ],
        name="ERP-14",
        description=(
            f"Liczba faktur miesiąca mieści się w {WOLUMEN_MIN}–{WOLUMEN_MAX} × mediany z 3 poprzednich miesięcy"
        ),
        metadata=meta(Poziom.OSTRZEGA, Wlasciciel.FINANSE),
    ),
)

REGULY = [
    ERP_01,
    ERP_02,
    ERP_03,
    ERP_04,
    ERP_05,
    ERP_06,
    ERP_07,
    ERP_08,
    ERP_09,
    ERP_10,
    ERP_11,
    ERP_12,
    ERP_13,
    ERP_14,
]
