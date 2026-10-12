"""Scala kontrahentów ERP zapisanych kilka razy i zapisuje w kawosz.duckdb tabelę mapa_kontrahentow (stary → nowy ID).

Każdy rekord z erp_kontrahenci porównujemy z każdym innym według trzech kryteriów:
- nazwa po ujednoliceniu: wielkie litery, bez polskich znaków i interpunkcji, jedna forma prawna;
- NIP: same cyfry (bez myślników);
- kod pocztowy.

Parą-kandydatem jest każda para z tą samą nazwą albo tym samym NIP-em. Klasy par:
- pewna (scalamy): ten sam NIP i ten sam kod pocztowy;
- wątpliwa (decyduje człowiek, patrz DECYZJE): ten sam NIP przy innym kodzie (np. oddział) albo ta sama nazwa
  i kod przy innym NIP-ie. Scalenie oznacza wtedy też poprawkę NIP-u w ERP;
- odrzucona: tylko ta sama nazwa, a NIP i kod są różne. Są to różne firmy o tej samej nazwie.

Grupa to spójna składowa par pewnych i zatwierdzonych. Nowy ID to najmniejszy (najstarszy) ID w grupie, czyli
rekord, który ma historię i zwykle ID z CRM. Archiwum porównujemy razem z aktywnymi i dopisujemy do mapy. Dzięki
temu mapa obejmuje każdy dokument z erp_faktury, a złączenie z nią niczego nie gubi.

Uruchomienie: PYTHONPATH=api poetry run python -m api.data_platform.mapa_kontrahentow
"""

import duckdb
import pandas as pd

from api.adapters.duckdb_conn import connect

TABELA = "mapa_kontrahentow"

# Decyzje dla par wątpliwych: (id_a, id_b) z id_a < id_b → True scala, False zostawia osobno.
# Pary bez decyzji zostają osobno, a ich rekordy mają w mapie do_decyzji = true.
DECYZJE: dict[tuple[int, int], bool] = {}

MAKRA = r"""
CREATE OR REPLACE TEMP MACRO nip_cyfry(x) AS regexp_replace(x, '[^0-9]', '', 'g');
-- Wielkie litery, bez polskich znaków, interpunkcja → spacja. Spacje na brzegach pozwalają podmieniać całe słowa.
CREATE OR REPLACE TEMP MACRO nazwa_slowa(x) AS
    ' ' || trim(regexp_replace(translate(upper(x), 'ĄĆĘŁŃÓŚŹŻ', 'ACELNOSZZ'), '[^A-Z0-9]+', ' ', 'g')) || ' ';
-- Jedna forma prawna: „Sp. z o.o.”, „spółka z o.o.”, „SP Z OO” → SPZOO; „S.A.”, „Spółka Akcyjna” → SA; itd.
CREATE OR REPLACE TEMP MACRO nazwa_ujednolicona(x) AS trim(
    regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(nazwa_slowa(x),
        ' (SPOLKA Z OGRANICZONA ODPOWIEDZIALNOSCIA|SPOLKA Z O O|SPOLKA Z OO|SP Z O O|SP Z OO) ', ' SPZOO ', 'g'),
        ' (SPOLKA AKCYJNA|S A) ', ' SA ', 'g'),
        ' (SPOLKA KOMANDYTOWA|SP K|S K) ', ' SPK ', 'g'),
        ' (SPOLKA JAWNA|SP J|S J) ', ' SPJ ', 'g'),
        ' (SPOLKA CYWILNA|S C) ', ' SC ', 'g'));
"""

KONTRAHENCI = """
    SELECT 'erp_kontrahenci' AS zrodlo, *, nazwa_ujednolicona(nazwa) AS nazwa_u, nip_cyfry(nip) AS nip_c
    FROM erp_kontrahenci
    UNION ALL
    SELECT 'erp_kontrahenci_archiwum', *, nazwa_ujednolicona(nazwa), nip_cyfry(nip)
    FROM erp_kontrahenci_archiwum
"""

PARY = f"""
    WITH k AS ({KONTRAHENCI}),
    p AS (
        SELECT a.id_kontrahenta AS id_a, b.id_kontrahenta AS id_b,
               a.nazwa_u = b.nazwa_u AS nazwa_zgodna, a.nip_c = b.nip_c AS nip_zgodny,
               a.kod_pocztowy = b.kod_pocztowy AS kod_zgodny
        FROM k a JOIN k b ON a.id_kontrahenta < b.id_kontrahenta AND (a.nazwa_u = b.nazwa_u OR a.nip_c = b.nip_c)
    )
    SELECT *, CASE WHEN nip_zgodny AND kod_zgodny THEN 'pewna'
                   WHEN nip_zgodny OR (nazwa_zgodna AND kod_zgodny) THEN 'wątpliwa'
                   ELSE 'odrzucona' END AS klasa
    FROM p ORDER BY id_a, id_b
"""

# Dowody do decyzji o parze: dane obu rekordów i to, czego nie widać w trzech kryteriach.
# Rekordy tej samej firmy pod tym samym adresem i nie dostają faktury w tym samym miesiącu (ERP fakturuje
# klienta raz w miesiącu). Rekordy różnych firm zwykle dostają.
DOWODY = f"""
    WITH k AS ({KONTRAHENCI}),
    mies AS (SELECT id_kontrahenta, list(DISTINCT date_trunc('month', data)) AS m
             FROM erp_faktury WHERE typ = 'faktura' GROUP BY 1)
    SELECT p.id_a, p.id_b, p.klasa, a.nazwa AS nazwa_a, b.nazwa AS nazwa_b, a.nip AS nip_a, b.nip AS nip_b,
           a.kod_pocztowy AS kod_a, b.kod_pocztowy AS kod_b, a.adres AS adres_a, b.adres AS adres_b,
           a.id_biura_crm AS crm_a, b.id_biura_crm AS crm_b,
           EXISTS (SELECT 1 FROM range(1, 11) r(i)
                   WHERE substr(a.nip_c, 1, i - 1) || substr(a.nip_c, i + 1) = b.nip_c
                      OR substr(b.nip_c, 1, i - 1) || substr(b.nip_c, i + 1) = a.nip_c) AS nip_bez_jednej_cyfry,
           len(ma.m) AS miesiace_z_faktura_a, len(mb.m) AS miesiace_z_faktura_b,
           len(list_intersect(ma.m, mb.m)) AS wspolne_miesiace
    FROM pary p JOIN k a ON a.id_kontrahenta = p.id_a JOIN k b ON b.id_kontrahenta = p.id_b
    LEFT JOIN mies ma ON ma.id_kontrahenta = p.id_a LEFT JOIN mies mb ON mb.id_kontrahenta = p.id_b
    ORDER BY p.id_a, p.id_b
"""

# Kontrola: suma faktur w każdym miesiącu przed scaleniem i po nim (przez mapę) musi być taka sama.
SUMY_MIESIECZNE = f"""
    SELECT date_trunc('month', f.data)::DATE AS miesiac, count(*) AS dokumenty,
           count(DISTINCT f.id_kontrahenta) AS kontrahenci_przed, count(DISTINCT m.id_nowy) AS kontrahenci_po,
           round(sum(f.kwota_netto), 2) AS netto_przed,
           round(sum(f.kwota_netto) FILTER (WHERE m.id_nowy IS NOT NULL), 2) AS netto_po
    FROM erp_faktury f LEFT JOIN {TABELA} m ON m.id_stary = f.id_kontrahenta
    GROUP BY 1 ORDER BY 1
"""


def pary(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Pary-kandydaci (ta sama nazwa albo NIP) z wynikiem trzech porównań i klasą."""
    con.execute(MAKRA)
    return con.sql(PARY).df()


def grupy(ids: list[int], krawedzie: list[tuple[int, int]]) -> dict[int, int]:
    """Spójne składowe grafu par. Każdy ID wskazuje najmniejszy ID swojej grupy."""
    rodzic = {i: i for i in ids}

    def korzen(i: int) -> int:
        while rodzic[i] != i:
            rodzic[i] = rodzic[rodzic[i]]
            i = rodzic[i]
        return i

    for a, b in krawedzie:
        ra, rb = korzen(a), korzen(b)
        if ra != rb:
            rodzic[max(ra, rb)] = min(ra, rb)
    return {i: korzen(i) for i in ids}


def zbuduj_mape(
    con: duckdb.DuckDBPyConnection, decyzje: dict[tuple[int, int], bool] = DECYZJE
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Zwraca (mapa, pary). Mapa ma jeden wiersz na każdy rekord kontrahenta (aktywni + archiwum)."""
    p = pary(con)
    rekordy = con.sql(f"SELECT zrodlo, id_kontrahenta FROM ({KONTRAHENCI}) ORDER BY 2").df()

    klasy = {(int(a), int(b)): klasa for a, b, klasa in zip(p["id_a"], p["id_b"], p["klasa"])}
    pewne = [para for para, klasa in klasy.items() if klasa == "pewna"]
    zatwierdzone = [para for para, scal in decyzje.items() if scal]
    nowy = grupy(rekordy["id_kontrahenta"].tolist(), pewne + zatwierdzone)

    # Podstawa scalenia rekordu: para, która go łączy z grupą (rekord główny dostaje None niżej).
    podstawa: dict[int, str] = {}
    for krawedzie, opis in ((pewne, "ten sam NIP i kod pocztowy"), (zatwierdzone, "decyzja")):
        for para in krawedzie:
            for i in para:
                podstawa.setdefault(i, opis)
    do_decyzji = {i for para, klasa in klasy.items() if klasa == "wątpliwa" and para not in decyzje for i in para}

    mapa = pd.DataFrame(
        {
            "id_stary": rekordy["id_kontrahenta"],
            "id_nowy": rekordy["id_kontrahenta"].map(nowy),
            "zrodlo": rekordy["zrodlo"],
        }
    )
    mapa["podstawa"] = [podstawa[s] if s != n else None for s, n in zip(mapa["id_stary"], mapa["id_nowy"])]
    mapa["do_decyzji"] = mapa["id_stary"].isin(do_decyzji)
    return mapa, p


def zapisz(con: duckdb.DuckDBPyConnection, mapa: pd.DataFrame) -> None:
    con.register("mapa_df", mapa)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE {TABELA} AS
        SELECT id_stary::BIGINT AS id_stary, id_nowy::BIGINT AS id_nowy, zrodlo, podstawa, do_decyzji
        FROM mapa_df ORDER BY id_stary
        """
    )
    con.unregister("mapa_df")


def dowody(con: duckdb.DuckDBPyConnection, p: pd.DataFrame) -> pd.DataFrame:
    """Dane obu rekordów i dowody spoza trzech kryteriów dla podanych par (np. wątpliwych)."""
    con.execute(MAKRA)
    con.register("pary", p)
    try:
        return con.sql(DOWODY).df()
    finally:
        con.unregister("pary")


def main() -> None:
    con = connect(read_only=False)
    try:
        mapa, p = zbuduj_mape(con)
        zapisz(con, mapa)
        sumy = con.sql(SUMY_MIESIECZNE).df()
        watpliwe = dowody(con, p[p["klasa"] == "wątpliwa"])
    finally:
        con.close()

    print("Pary-kandydaci według klasy:")
    print(p.groupby(["klasa", "nip_zgodny", "nazwa_zgodna", "kod_zgodny"]).size().to_string(), "\n")
    scalone = mapa[mapa["id_stary"] != mapa["id_nowy"]]
    print(
        f"{TABELA}: {len(mapa)} rekordów → {mapa['id_nowy'].nunique()} kontrahentów "
        f"(scalonych {len(scalone)}, do decyzji {mapa['do_decyzji'].sum()})\n"
    )
    print(f"Pary wątpliwe ({len(watpliwe)}):")
    print(watpliwe.to_string(index=False, max_colwidth=36), "\n")

    rozne = sumy[sumy["netto_przed"] != sumy["netto_po"]]
    if not rozne.empty:
        raise SystemExit(f"Suma faktur po scaleniu różni się od sumy przed:\n{rozne.to_string(index=False)}")
    print("Faktury według miesięcy (sumy przed i po scaleniu są równe):")
    print(sumy.tail(3).to_string(index=False))


if __name__ == "__main__":
    main()
