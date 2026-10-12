"""Sprawdza dane źródła z kontraktem miesiąc po miesiącu i mówi prostym językiem, co złamano.

Każdy miesiąc zakresu sprawdzają osobno wszystkie reguły kontraktu, te same, które działają co noc.
Dla każdego naruszenia komunikat podaje kontrakt i jego wersję, regułę, kolumnę, dzień, od którego
trwa naruszenie, skalę w miesiącu, właściciela i to, co zrobić (wg kontraktu). Złamanie reguły
blokującej oznacza złamany kontrakt, a reguły ostrzegającej — ostrzeżenie.

    PYTHONPATH=api poetry run python -m api.data_platform.kontrakty.sprawdz pos_paragony \
        --od 2026-01-01 --do 2026-09-30 --raport docs/kontrakt_pos_2026.md

Kod wyjścia 1 oznacza, że w którymś miesiącu kontrakt został złamany.
"""

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from api.adapters.duckdb_conn import DB_PATH, connect
from api.data_platform.kontrakty.kontrakt import PLIK, Kontrakt, wczytaj
from api.data_platform.reguly import ecom, erp, pos
from api.data_platform.reguly.raport import liczba
from api.data_platform.reguly.regula import Poziom, Regula, Wynik

REGULY = {"pos_paragony": pos.REGULY, "ecom_zamowienia": ecom.REGULY, "erp_faktury": erp.REGULY}
MIESIACE = [
    "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
    "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
]  # fmt: skip
RZYMSKIE = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
# Etykiety Pandery z nazwą kolumny na końcu (patrz reguly/regula.py: _etykieta).
_KOLUMNA_Z_ETYKIETY = re.compile(r"^(?:brak kolumny|nieoczekiwana kolumna) (\S+)$")
# Wbudowane testy Pandery po polsku: „isin([0, 1])” → „wartość spoza listy [0, 1]”.
_TESTY_PO_POLSKU = [
    (re.compile(r"^isin\((.*)\)$"), "wartość spoza listy {}"),
    (re.compile(r"^equal_to\((.*)\)$"), "wartość inna niż {}"),
    (re.compile(r"^not_equal_to\((.*)\)$"), "wartość równa {}"),
    (re.compile(r"^greater_than\((.*)\)$"), "wartość nie większa niż {}"),
    (re.compile(r"^greater_than_or_equal_to\((.*)\)$"), "wartość mniejsza niż {}"),
    (re.compile(r"^less_than\((.*)\)$"), "wartość nie mniejsza niż {}"),
    (re.compile(r"^less_than_or_equal_to\((.*)\)$"), "wartość większa niż {}"),
    (re.compile(r"^in_range\((.*), (.*)\)$"), "wartość spoza zakresu {}–{}"),
    (re.compile(r"^str_matches\((.*)\)$"), "wartość niezgodna ze wzorcem {}"),
]


@dataclass
class Komunikat:
    kontrakt: Kontrakt
    regula: Regula
    naruszenie: str
    kolumny: list[str]
    od: date | None  # pierwszy i ostatni dzień z naruszeniem w miesiącu
    do: date | None
    rekordy: int
    pliki: int | None = None
    lokale: tuple[int, ...] = ()
    pierwszy_dzien: date | None = None  # od kiedy trwa naruszenie (pierwszy dzień w całym zakresie)

    @property
    def klucz(self) -> tuple:
        return self.regula.id, self.naruszenie, tuple(self.kolumny)

    @property
    def blokuje(self) -> bool:
        return self.regula.poziom == Poziom.BLOKUJE

    def opis_kolumn(self) -> str:
        nazwy = ", ".join("nazwa pliku" if k == PLIK else f"`{k}`" for k in self.kolumny)
        if self.kolumny == [PLIK]:
            return nazwy
        return f"kolumna {nazwy}" if len(self.kolumny) == 1 else f"kolumny {nazwy}"

    def tekst(self) -> str:
        """Komunikat w Markdown, do raportu i na ekran."""
        k, r = self.kontrakt, self.regula
        regula_k = k.reguly[r.id]
        wstep = "Złamany kontrakt" if self.blokuje else "Ostrzeżenie z kontraktu"
        skutek = "dane z tych dni nie trafiają do raportów" if self.blokuje else "dane idą dalej"
        if self.od is None:
            dni = "— (rekordy bez daty)"
        else:
            w_miesiacu = f"{self.od}" if self.od == self.do else f"{self.od} – {self.do}"
            pierwszy = self.pierwszy_dzien or self.od
            dni = f"**{pierwszy}**" + (" (pierwszy raz w sprawdzanym okresie)" if pierwszy < self.od else "")
            dni += f"; w tym miesiącu: {w_miesiacu}"
        skala = [f"rekordy: {liczba(self.rekordy)} ({r.jednostka})"]
        if self.pliki is not None:
            skala.append(f"pliki: {liczba(self.pliki)}")
        if self.lokale:
            if len(self.lokale) == 1:
                skala.append(f"lokal {self.lokale[0]}")
            else:
                lokale = ", ".join(map(str, self.lokale)) if len(self.lokale) <= 5 else str(len(self.lokale))
                skala.append(f"lokale: {lokale}")
        return "\n".join(
            [
                f"**{r.id} · {r.poziom} · {self.opis_kolumn()}**",
                "",
                f"{wstep} „{k.nazwa}” (`{k.plik_yaml}`, wersja {k.wersja}), reguła {r.id}: „{r.opis}”."
                f" Naruszenie: {self.naruszenie}. Poziom {r.poziom}: {skutek}.",
                "",
                f"- Od dnia: {dni}",
                f"- Skala w miesiącu: {'; '.join(skala)}",
                f"- Co zrobić: {regula_k.co_zrobic}",
                f"- Odpowiada: {r.wlasciciel}",
            ]
        )


@dataclass
class Miesiac:
    od: date
    do: date
    wyniki: list[Wynik]
    komunikaty: list[Komunikat]

    @property
    def nazwa(self) -> str:
        return f"{MIESIACE[self.od.month - 1]} {self.od.year}"

    @property
    def zlamany(self) -> bool:
        return any(k.blokuje for k in self.komunikaty)

    @property
    def wynik(self) -> str:
        ostrzezenia = sum(not k.blokuje for k in self.komunikaty)
        if self.zlamany:
            return "kontrakt złamany"
        return f"zgodny, ostrzeżenia: {ostrzezenia}" if ostrzezenia else "zgodny"


def miesiace(od: date, do: date) -> list[tuple[date, date]]:
    """Zakres pocięty na miesiące kalendarzowe (pierwszy i ostatni może być niepełny)."""
    wynik, poczatek = [], od
    while poczatek <= do:
        nastepny = (poczatek.replace(day=1) + timedelta(days=32)).replace(day=1)
        wynik.append((poczatek, min(nastepny - timedelta(days=1), do)))
        poczatek = nastepny
    return wynik


def _dni(ramka: pd.DataFrame, strefa: str) -> pd.Series:
    """Dzień każdego wiersza: `dzien`, `data_czas`, `data`, `data_utc` (na czas lokalny) albo data z numeru paragonu."""
    dni = pd.Series(pd.NaT, index=ramka.index, dtype="datetime64[us]")
    for kolumna in ("dzien", "data_czas", "data"):
        if kolumna in ramka:
            dni = dni.fillna(pd.to_datetime(ramka[kolumna]).dt.normalize().astype("datetime64[us]"))
    if "data_utc" in ramka:
        lokalnie = pd.to_datetime(ramka["data_utc"]).dt.tz_localize("UTC").dt.tz_convert(strefa).dt.tz_localize(None)
        dni = dni.fillna(lokalnie.dt.normalize().astype("datetime64[us]"))
    if "nr_paragonu" in ramka:
        rrmmdd = (ramka["nr_paragonu"] // 10000).astype("Int64").astype(str)
        z_numeru = pd.to_datetime(rrmmdd, format="%y%m%d", errors="coerce")
        dni = dni.fillna(z_numeru.astype("datetime64[us]"))
    return dni


def _kolumny(etykieta: str, kolumny_reguly: list[str], kontrakt: Kontrakt) -> list[str]:
    """Kolumna z etykiety naruszenia („storno: isin([0, 1])”, „brak kolumny X”), a gdy jej tam nie ma — z kontraktu."""
    if dopasowanie := _KOLUMNA_Z_ETYKIETY.match(etykieta):
        return [dopasowanie[1]]
    pierwsze_slowo = re.split(r"[ :=]", etykieta)[0]  # „storno: isin(…)”, „plik = pos_paragony_…”
    if pierwsze_slowo in [k.nazwa for k in kontrakt.kolumny]:
        return [pierwsze_slowo]
    return [k for k in kolumny_reguly if k.split(".")[-1] == pierwsze_slowo] or kolumny_reguly


def _po_polsku(etykieta: str, kolumny: list[str]) -> str:
    """Naruszenie bez nazwy kolumny (komunikat już ją podaje) i bez nazw testów Pandery."""
    if len(kolumny) == 1 and etykieta.startswith(f"{kolumny[0].split('.')[-1]}: "):
        etykieta = etykieta.split(": ", 1)[1]
    for wzorzec, tekst in _TESTY_PO_POLSKU:
        if dopasowanie := wzorzec.match(etykieta):
            return tekst.format(*dopasowanie.groups())
    return etykieta


def komunikaty(kontrakt: Kontrakt, wynik: Wynik) -> list[Komunikat]:
    """Komunikaty z wyniku reguły: jeden na kolumnę (albo zestaw kolumn reguły) ze wszystkimi jej naruszeniami."""
    regula = wynik.regula
    kolumny_reguly = kontrakt.reguly[regula.id].kolumny
    if wynik.blad:
        naruszenie = f"reguły nie udało się wykonać ({wynik.blad})"
        return [Komunikat(kontrakt, regula, naruszenie, kolumny_reguly, None, None, 0)]
    ramka = wynik.bledne_wiersze
    if ramka is None:
        return []
    dni = _dni(ramka, kontrakt.dostawa.strefa)
    etykiety = ramka["naruszenie"].str.split("; ")
    # Jeden komunikat na kolumnę (albo zestaw kolumn reguły), ze wszystkimi naruszeniami, które jej dotyczą.
    grupy: dict[tuple[str, ...], tuple[list[str], set]] = {}
    for etykieta in sorted(wynik.naruszenia):
        wiersze = ramka[etykiety.apply(lambda e: etykieta in e)]
        if "kolumna" in wiersze:  # reguła, która sprawdza kolumny pliku (POS-12): wiersz = plik × kolumna
            podgrupy = [((kolumna,), grupa.index) for kolumna, grupa in wiersze.groupby("kolumna", sort=True)]
        else:
            podgrupy = [(tuple(_kolumny(etykieta, kolumny_reguly, kontrakt)), wiersze.index)]
        for kolumny, indeks in podgrupy:
            naruszenia, wiersze_grupy = grupy.setdefault(kolumny, ([], set()))
            naruszenia.append(_po_polsku(etykieta, list(kolumny)))
            wiersze_grupy.update(indeks)
    wynik_k = []
    for kolumny, (naruszenia, wiersze_grupy) in grupy.items():
        grupa = ramka.loc[sorted(wiersze_grupy)]
        naruszenie = "; ".join(naruszenia)
        if "po_kolumnie" in grupa and grupa["po_kolumnie"].nunique() == 1:  # gdzie w pliku wstawiono kolumnę
            naruszenie += f" (w pliku po kolumnie `{grupa['po_kolumnie'].dropna().iloc[0]}`)"
        dni_grupy = dni.loc[grupa.index].dropna()
        wynik_k.append(
            Komunikat(
                kontrakt,
                regula,
                naruszenie,
                list(kolumny),
                dni_grupy.min().date() if len(dni_grupy) else None,
                dni_grupy.max().date() if len(dni_grupy) else None,
                len(grupa),
                grupa["plik"].nunique() if "plik" in grupa else None,
                tuple(sorted(grupa["lokal"].dropna().astype(int).unique())) if "lokal" in grupa else (),
            )
        )
    return wynik_k


def sprawdz(con: duckdb.DuckDBPyConnection, kontrakt: Kontrakt, od: date, do: date) -> list[Miesiac]:
    reguly = REGULY[kontrakt.kontrakt]
    wynik, pierwsze_dni = [], {}
    for poczatek, koniec in miesiace(od, do):
        wyniki = [r.sprawdz(con, poczatek, koniec) for r in reguly]
        lista = [k for w in wyniki for k in komunikaty(kontrakt, w)]
        for k in lista:
            k.pierwszy_dzien = pierwsze_dni.setdefault(k.klucz, k.od)
        lista.sort(key=lambda k: (not k.blokuje, k.regula.id, k.naruszenie, k.kolumny))
        wynik.append(Miesiac(poczatek, koniec, wyniki, lista))
    return wynik


def _macierz(miesiace_: list[Miesiac]) -> list[str]:
    """Reguła × miesiąc: liczba rekordów z naruszeniem (pogrubiona, gdy reguła blokuje)."""
    linie = [
        "| Reguła | Poziom | Jednostka | " + " | ".join(RZYMSKIE[m.od.month - 1] for m in miesiace_) + " |",
        "|---|---|---|" + "---:|" * len(miesiace_),
    ]
    for i, regula in enumerate(r.regula for r in miesiace_[0].wyniki):
        komorki = []
        for m in miesiace_:
            w = m.wyniki[i]
            if w.blad:
                komorki.append("**błąd**" if w.regula.poziom == Poziom.BLOKUJE else "błąd")
            elif w.wiersze == 0:
                komorki.append("—")
            elif w.ok:
                komorki.append("0")
            else:
                komorki.append(f"**{liczba(w.bledne)}**" if w.blokuje else liczba(w.bledne))
        linie.append(f"| {regula.id} | {regula.poziom} | {regula.jednostka} | " + " | ".join(komorki) + " |")
    return linie


def markdown(kontrakt: Kontrakt, miesiace_: list[Miesiac], polecenie: str) -> str:
    od, do = miesiace_[0].od, miesiace_[-1].do
    zlamane = [m for m in miesiace_ if m.zlamany]
    blokujace = [k for m in zlamane for k in m.komunikaty if k.blokuje]
    pierwsze = min(blokujace, key=lambda k: k.od or date.max, default=None)
    linie = [
        f"# Kontrakt „{kontrakt.nazwa}”: sprawdzenie {od} – {do} miesiąc po miesiącu",
        "",
        f"Kontrakt [`{kontrakt.plik_yaml}`](../api/api/data_platform/kontrakty/{kontrakt.plik_yaml})"
        f" w wersji {kontrakt.wersja}."
        f" Właściciel: {kontrakt.wlasciciel}, odbiorca: {kontrakt.odbiorca}, termin dostawy: {kontrakt.dostawa.termin}"
        f" ({kontrakt.dostawa.strefa}).",
        "",
        f"Każdy miesiąc sprawdzono osobno wszystkimi {len(miesiace_[0].wyniki)} regułami kontraktu na `kawosz.duckdb`."
        " To te same reguły, które działają co noc. Naruszenie reguły blokującej oznacza złamany kontrakt: dane"
        " z tych dni nie powinny trafić do raportów. Naruszenie reguły ostrzegającej to ostrzeżenie: dane idą dalej,"
        " a właściciel dostaje listę.",
        "",
        f"Raport wygenerowano {date.today()} poleceniem:",
        "",
        "```bash",
        polecenie,
        "```",
        "",
        "## Podsumowanie",
        "",
    ]
    if zlamane:
        linie.append(
            f"- **Kontrakt złamany w {len(zlamane)} z {len(miesiace_)} miesięcy:**"
            f" {', '.join(m.nazwa for m in zlamane)}."
        )
        linie.append(
            f"- **Pierwsze złamanie:** {pierwsze.od}, {pierwsze.regula.id}, {pierwsze.opis_kolumn()}:"
            f" {pierwsze.naruszenie}."
        )
    else:
        linie.append(f"- **Kontrakt nie został złamany w żadnym z {len(miesiace_)} miesięcy.**")
    linie += [
        "",
        "| Miesiąc | Wynik | Złamane reguły (blokujące) | Ostrzeżenia (reguły) |",
        "|---|---|---|---|",
    ]
    for m in miesiace_:
        blokujace = sorted({k.regula.id for k in m.komunikaty if k.blokuje})
        ostrzegajace = sorted({k.regula.id for k in m.komunikaty if not k.blokuje})
        wynik = f"**{m.wynik}**" if m.zlamany else m.wynik
        linie.append(f"| {m.nazwa} | {wynik} | {', '.join(blokujace) or '—'} | {', '.join(ostrzegajace) or '—'} |")
    linie += [
        "",
        "Rekordy z naruszeniem według reguły i miesiąca (pogrubione: reguła blokująca, „—”: nie było czego sprawdzić):",
        "",
        *_macierz(miesiace_),
        "",
        "## Komunikaty miesiąc po miesiącu",
    ]
    for m in miesiace_:
        linie += ["", f"### {m.nazwa.capitalize()}: {m.wynik}", ""]
        if not m.komunikaty:
            linie.append("Bez naruszeń.")
        for k in m.komunikaty:
            linie += [k.tekst(), ""]
    puste = [
        w.regula
        for i, w in enumerate(miesiace_[0].wyniki)
        if all(m.wyniki[i].wiersze == 0 and not m.wyniki[i].blad for m in miesiace_)
    ]
    if puste:
        linie += ["", "## Czego nie dało się sprawdzić", ""]
        for r in puste:
            linie.append(f"- **{r.id}** ({r.opis}): w żadnym miesiącu nie było czego sprawdzić ({r.jednostka}).")
            if kontrakt.reguly[r.id].bez_danych:
                linie[-1] += f" {kontrakt.reguly[r.id].bez_danych}"
    return "\n".join(linie).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("kontrakt", choices=REGULY, help="nazwa kontraktu (plik kontrakty/{nazwa}.yaml)")
    parser.add_argument("--od", type=date.fromisoformat, required=True, help="pierwszy dzień zakresu")
    parser.add_argument("--do", type=date.fromisoformat, required=True, help="ostatni dzień zakresu")
    parser.add_argument("--baza", type=Path, default=DB_PATH, help="plik DuckDB (domyślnie kawosz.duckdb)")
    parser.add_argument("--raport", type=Path, help="zapisz raport w Markdown do tego pliku")
    args = parser.parse_args()

    kontrakt = wczytaj(args.kontrakt)
    con = connect(read_only=True, db_path=args.baza)
    try:
        wynik = sprawdz(con, kontrakt, args.od, args.do)
    finally:
        con.close()

    for m in wynik:
        print(f"\n=== {m.nazwa}: {m.wynik}")
        for k in m.komunikaty:
            print("\n" + k.tekst())
    if args.raport:
        argumenty = sys.argv[1:]
        if "--baza" in argumenty:  # ścieżka do kopii bazy nie należy do raportu
            del argumenty[argumenty.index("--baza") : argumenty.index("--baza") + 2]
        polecenie = "PYTHONPATH=api poetry run python -m api.data_platform.kontrakty.sprawdz " + " ".join(argumenty)
        args.raport.write_text(markdown(kontrakt, wynik, polecenie))
        print(f"\nRaport: {args.raport}")
    sys.exit(1 if any(m.zlamany for m in wynik) else 0)


if __name__ == "__main__":
    main()
