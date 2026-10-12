"""Raport naruszeń reguł jakości w Markdown, np. docs/naruszenia_2026-09.md (opcja --raport w uruchom.py)."""

from datetime import date

import numpy as np
import pandas as pd

from api.data_platform.reguly.regula import Wynik

PRZYKLADY = 5


def liczba(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _komorka(wartosc) -> str:
    if pd.isna(wartosc):
        return "—"
    if isinstance(wartosc, bool | np.bool_):
        return "tak" if wartosc else "nie"
    if isinstance(wartosc, pd.Timestamp):
        return wartosc.strftime("%Y-%m-%d" if wartosc == wartosc.normalize() else "%Y-%m-%d %H:%M:%S")
    if isinstance(wartosc, float):
        return f"{wartosc:,.2f}".replace(",", " ").replace(".", ",")
    return str(wartosc).replace("|", "\\|").replace("\n", " ")


def _tabela(ramka: pd.DataFrame) -> list[str]:
    naglowek = ["| " + " | ".join(ramka.columns) + " |", "|" + "---|" * len(ramka.columns)]
    return naglowek + [
        "| " + " | ".join(_komorka(v) for v in wiersz) + " |" for wiersz in ramka.itertuples(index=False)
    ]


def _skala(wynik: Wynik) -> str:
    return ", ".join(f"#{n}" for n in wynik.regula.skala) or "—"


def _blokuje(wynik: Wynik) -> str:
    return "**tak**" if wynik.blokuje else "nie (ostrzega)"


def markdown(wyniki: list[Wynik], od: date, dzien: date, polecenie: str) -> str:
    naruszone = [w for w in wyniki if not w.ok]
    blokujace = [w.regula.id for w in naruszone if w.blokuje]
    ostrzegajace = [w for w in naruszone if not w.blokuje]
    niewykonane = [w.regula.id for w in wyniki if w.blad]

    linie = [
        f"# Naruszenia reguł jakości: {od} – {dzien}",
        "",
        f"Wynik uruchomienia {len(wyniki)} reguł z [`reguly.md`](reguly.md) na danych od {od} do {dzien}"
        " (`kawosz.duckdb`). Każda reguła sprawdza wszystkie rekordy z zakresu, a Pandera zbiera wszystkie"
        " naruszenia naraz (`lazy=True`). Błąd jednej reguły nie przerywa pozostałych.",
        "",
        f"Raport wygenerowano {date.today()} poleceniem:",
        "",
        "```bash",
        polecenie,
        "```",
        "",
        "## Podsumowanie",
        "",
        f"- **Wsad zablokowany: {'tak' if blokujace else 'nie'}.**"
        + (f" Reguły blokujące z naruszeniami: {', '.join(blokujace)}." if blokujace else ""),
        f"- Reguły z naruszeniami: {len(naruszone)} z {len(wyniki)}"
        f" ({len(blokujace)} blokujących, {len(ostrzegajace)} ostrzegających)."
        f" Bez naruszeń: {len(wyniki) - len(naruszone)}.",
    ]
    if niewykonane:
        linie.append(f"- **Nie udało się wykonać:** {', '.join(niewykonane)} (szczegóły niżej).")
    linie += [
        "- „Rekordy” to wiersze ramki, którą sprawdza reguła (kolumna „Jednostka”: paragon, pozycja, lokal × dzień…)."
        " Ten sam rekord źródłowy może łamać kilka reguł, więc liczb z różnych reguł nie należy sumować.",
        "",
        "| Reguła | Blokuje wsad | Właściciel | Rekordy z naruszeniem | Sprawdzone | Jednostka | Pozycja w skali |",
        "|---|---|---|---:|---:|---|---|",
    ]
    linie += [
        f"| {w.regula.id} | {_blokuje(w)} | {w.regula.wlasciciel} | {liczba(w.bledne) if not w.blad else 'błąd'}"
        f" | {liczba(w.wiersze)} | {w.regula.jednostka} | {_skala(w)} |"
        for w in naruszone
    ]

    linie += ["", "## Szczegóły naruszeń"]
    for w in naruszone:
        r = w.regula
        linie += [
            "",
            f"### {r.id}: {'blokuje wsad' if w.blokuje else 'ostrzega'}",
            "",
            f"{r.opis}.",
            "",
            f"- Właściciel: {r.wlasciciel}. Pozycja w `skala_problemu.md`: {_skala(w)}.",
        ]
        if w.blad:
            linie += [f"- **Reguły nie udało się wykonać:** `{w.blad}`"]
            continue
        linie += [f"- Rekordy z naruszeniem: {liczba(w.bledne)} z {liczba(w.wiersze)} (jednostka: {r.jednostka})."]
        linie += ["- Naruszenia (rekord może łamać kilka warunków naraz):"]
        linie += [
            f"  - {nazwa}: {liczba(n)}" for nazwa, n in sorted(w.naruszenia.items(), key=lambda x: (-x[1], x[0]))
        ]
        przyklady = w.przyklady(PRZYKLADY)
        linie += ["", f"Przykłady ({len(przyklady)} z {liczba(w.bledne)}):", ""] + _tabela(przyklady)

    linie += [
        "",
        "## Reguły bez naruszeń",
        "",
        "| Reguła | Poziom | Sprawdzone | Jednostka | Pozycja w skali |",
        "|---|---|---:|---|---|",
    ]
    linie += [
        f"| {w.regula.id} | {w.regula.poziom} | {liczba(w.wiersze)} | {w.regula.jednostka} | {_skala(w)} |"
        for w in wyniki
        if w.ok
    ]
    return "\n".join(linie) + "\n"
