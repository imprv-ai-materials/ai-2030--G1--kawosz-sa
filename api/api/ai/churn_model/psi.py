"""PSI cech modelu churnu: czy rozkład cech w tygodniu t0 odjechał od zbioru uczącego modelu.

Odniesienie: wiersze cechy_treningowe, na których uczył się model produkcyjny v3_katalog (versions/v3_katalog/
trenuj.py): t0 od 2024-04-01, o ile okno etykiety [t0, t0 + 90 dni) kończy się przed 2025-10-01, czyli t0 2024-04 –
2025-07. Cechy tygodnia liczy build.policz_cechy, czyli ten sam kod co cechy_treningowe.

Przedziały ustalone na treningu, te same dla każdego tygodnia:
- cecha liczbowa: 10 przedziałów między decylami treningu (granice 10%, 20%, …, 90%, każda to wartość z treningu;
  przedział (a, b] zawiera prawą granicę; skrajne przedziały otwarte,
  więc wartość spoza zakresu treningu trafia do skrajnego). Cecha z wieloma równymi wartościami (np. awarie_60d,
  w większości 0) ma powtórzone decyle; powtórzenia łączymy, więc przedziałów bywa mniej;
- cecha kategoryczna (plan, branza, miasto, am_id): 9 najczęstszych kategorii treningu i „inne”;
- dodatkowo przedział „brak” na NULL: zmiana udziału braków (np. cena_mies) to też zmiana rozkładu.

PSI = Σ (udział w tygodniu − udział w treningu) · ln(udział w tygodniu / udział w treningu). Udział poniżej 0,0001
podnosimy do 0,0001, żeby pusty przedział nie dawał nieskończoności. PSI > 0,25 to alert: zapis w alerty_psi
i wykres rozkładu przed i po w docs/img/psi/.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import PercentFormatter  # noqa: E402

from api.ai.features.build import KLUCZ, TABELA, policz_cechy  # noqa: E402

# Zbiór uczący v3_katalog (trenuj.py: POCZATEK_UCZENIA, POCZATEK_TESTU, OKNO_ETYKIETY); zgodność pilnuje test.
POCZATEK_UCZENIA = date(2024, 4, 1)
POCZATEK_TESTU = date(2025, 10, 1)
OKNO_ETYKIETY = timedelta(days=90)
KATEGORYCZNE = ["plan", "branza", "miasto", "am_id"]  # jak v3_katalog/model.py; am_id to identyfikator opiekuna
DECYLE = [i / 10 for i in range(1, 10)]
KATEGORIE = 9  # + „inne” = 10 przedziałów
BRAK, INNE = "brak", "inne"
MIN_UDZIAL = 0.0001
PROG = 0.25
TABELA_PSI = "psi_cech"
TABELA_ALERTOW = "alerty_psi"


@dataclass(frozen=True)
class Przedzialy:
    """Przedziały jednej cechy z treningu: granice decyli (liczbowa) albo najczęstsze kategorie (kategoryczna)."""

    cecha: str
    granice: tuple[float, ...] = ()
    kategorie: tuple[str, ...] = ()

    @property
    def kategoryczna(self) -> bool:
        return bool(self.kategorie)

    def etykiety(self) -> list[str]:
        if self.kategoryczna:
            return [*self.kategorie, INNE, BRAK]
        g = [_liczba(x) for x in self.granice]
        srodkowe = [f"{a}–{b}" for a, b in zip(g, g[1:])]
        return [f"≤ {g[0]}", *srodkowe, f"> {g[-1]}", BRAK]

    def przypisz(self, wartosci: pd.Series) -> pd.Series:
        """Etykieta przedziału dla każdej wartości. Przedział liczbowy (a, b] zawiera prawą granicę."""
        etykiety = self.etykiety()
        brak = wartosci.isna()
        if self.kategoryczna:
            tekst = wartosci.astype(str)
            wynik = tekst.where(tekst.isin(self.kategorie), INNE)
        else:
            indeks = np.searchsorted(np.array(self.granice), wartosci.fillna(0).astype(float), side="left")
            wynik = pd.Series([etykiety[i] for i in indeks], index=wartosci.index)
        return wynik.where(~brak, BRAK)

    def udzialy(self, wartosci: pd.Series) -> pd.Series:
        """Udział wierszy w każdym przedziale, w kolejności etykiet (sumuje się do 1)."""
        return self.przypisz(wartosci).value_counts(normalize=True).reindex(self.etykiety(), fill_value=0.0)


def _liczba(x: float) -> str:
    return f"{x:.4g}".replace(".", ",")


def przedzialy_z_treningu(trening: pd.Series) -> Przedzialy:
    cecha = str(trening.name)
    znane = trening.dropna()
    if cecha in KATEGORYCZNE:
        liczby = znane.astype(str).value_counts()
        # przy remisie liczebności kolejność alfabetyczna, żeby przedziały nie zależały od kolejności wierszy
        najczestsze = sorted(liczby.items(), key=lambda kv: (-kv[1], kv[0]))[:KATEGORIE]
        return Przedzialy(cecha, kategorie=tuple(k for k, _ in najczestsze))
    # decyle jako wartości z treningu (bez interpolacji), więc granica cechy całkowitej jest liczbą całkowitą
    granice = np.unique(np.quantile(znane.astype(float), DECYLE, method="inverted_cdf")) if len(znane) else [0.0]
    return Przedzialy(cecha, granice=tuple(float(g) for g in granice))


def psi(trening: pd.Series, tydzien: pd.Series) -> float:
    """PSI dwóch rozkładów udziałów w tych samych przedziałach."""
    r = np.maximum(trening.to_numpy(dtype=float), MIN_UDZIAL)
    t = np.maximum(tydzien.to_numpy(dtype=float), MIN_UDZIAL)
    return float(np.sum((t - r) * np.log(t / r)))


def zbior_uczacy(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Wiersze cechy_treningowe ze zbioru uczącego v3_katalog, bez etykiety."""
    return con.execute(
        f"SELECT * EXCLUDE (odejdzie_90d) FROM {TABELA} WHERE t0 >= ? AND t0 + ? <= ?",
        [POCZATEK_UCZENIA, OKNO_ETYKIETY, POCZATEK_TESTU],
    ).df()


def porownaj(trening: pd.DataFrame, tydzien: pd.DataFrame) -> list[dict]:
    """PSI każdej cechy (kolumny poza kluczem) z przedziałami i udziałami, w kolejności kolumn."""
    wyniki = []
    for cecha in [k for k in trening.columns if k not in KLUCZ]:
        przedzialy = przedzialy_z_treningu(trening[cecha])
        przed, po = przedzialy.udzialy(trening[cecha]), przedzialy.udzialy(tydzien[cecha])
        wyniki.append(
            {
                "cecha": cecha,
                "psi": psi(przed, po),
                "przedzialy": przedzialy.etykiety(),
                "trening": [float(u) for u in przed],
                "tydzien": [float(u) for u in po],
                "wiersze_trening": len(trening),
                "wiersze_tydzien": len(tydzien),
            }
        )
    return wyniki


def policz(con: duckdb.DuckDBPyConnection, t0: date) -> list[dict]:
    """PSI każdej cechy w t0 względem zbioru uczącego."""
    trening = zbior_uczacy(con)
    if trening.empty:
        raise ValueError(f"{TABELA} nie ma wierszy zbioru uczącego ({POCZATEK_UCZENIA} …), zbuduj ją build.py")
    tydzien = policz_cechy(con, [t0]).df()
    if tydzien.empty:
        raise ValueError(f"w t0 = {t0} nie ma żadnego biura z aktywną umową")
    return porownaj(trening, tydzien)


def sciezka_wykresu(katalog: Path, t0: date, cecha: str) -> Path:
    return katalog / f"{t0}_{cecha}.png"


def zapisz(con: duckdb.DuckDBPyConnection, t0: date, wyniki: list[dict], wykresy: dict[str, str]) -> None:
    """PSI każdej cechy w psi_cech i alerty (PSI > PROG) w alerty_psi, w miejsce poprzedniego zapisu tygodnia t0.

    `wykresy`: cecha z alertem → ścieżka jej wykresu, zapisywana przy alercie."""
    zapisano = datetime.now().replace(microsecond=0)
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABELA_PSI} (
            -- przedzialy: liczba przedziałów wartości z treningu, bez przedziału „brak”
            t0 DATE, cecha VARCHAR, psi DOUBLE, przedzialy INTEGER, wiersze_tydzien BIGINT, wiersze_trening BIGINT,
            alert BOOLEAN, zapisano TIMESTAMP);
        CREATE TABLE IF NOT EXISTS {TABELA_ALERTOW} (
            t0 DATE, cecha VARCHAR, psi DOUBLE, prog DOUBLE, wykres VARCHAR, zapisano TIMESTAMP);
    """)
    con.execute("BEGIN")
    try:
        con.execute(f"DELETE FROM {TABELA_PSI} WHERE t0 = ?", [t0])
        con.execute(f"DELETE FROM {TABELA_ALERTOW} WHERE t0 = ?", [t0])
        con.executemany(
            f"INSERT INTO {TABELA_PSI} VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                [t0, w["cecha"], w["psi"], len(w["przedzialy"]) - 1, w["wiersze_tydzien"], w["wiersze_trening"],
                 w["psi"] > PROG, zapisano]
                for w in wyniki
            ],
        )
        alerty = [[t0, w["cecha"], w["psi"], PROG, wykresy[w["cecha"]], zapisano] for w in wyniki if w["psi"] > PROG]
        if alerty:
            con.executemany(f"INSERT INTO {TABELA_ALERTOW} VALUES (?, ?, ?, ?, ?, ?)", alerty)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


# Paleta kategoryczna (sloty 1–2, tryb jasny) z kontrastem ≥ 3:1 na tle i rozróżnialna przy daltonizmie.
KOLOR_TRENING, KOLOR_TYDZIEN = "#2a78d6", "#eb6834"
TEKST, TEKST_POBOCZNY, SIATKA, TLO = "#1f1f1e", "#6b6a63", "#e4e3dc", "#fcfcfb"


def narysuj(wynik: dict, t0: date, sciezka: Path) -> None:
    """Udziały w przedziałach: zbiór uczący i tydzień t0, obok siebie, z PSI w tytule."""
    przedzialy, przed, po = wynik["przedzialy"], wynik["trening"], wynik["tydzien"]
    x = np.arange(len(przedzialy))
    szerokosc = 0.38
    fig, ax = plt.subplots(figsize=(max(6.4, 0.75 * len(przedzialy) + 2), 4), dpi=150)
    fig.patch.set_facecolor(TLO)
    ax.set_facecolor(TLO)
    ax.bar(x - szerokosc / 2 - 0.01, przed, szerokosc, color=KOLOR_TRENING,
           label=f"zbiór uczący v3_katalog ({wynik['wiersze_trening']} wierszy)")
    ax.bar(x + szerokosc / 2 + 0.01, po, szerokosc, color=KOLOR_TYDZIEN,
           label=f"tydzień t0 = {t0} ({wynik['wiersze_tydzien']} biur)")
    psi_tekst = f"{wynik['psi']:.2f}".replace(".", ",")
    ax.set_title(f"{wynik['cecha']}: PSI {psi_tekst} (próg {str(PROG).replace('.', ',')})", loc="left",
                 color=TEKST, fontsize=12)
    ax.set_xticks(x, przedzialy, rotation=30 if len(przedzialy) > 6 else 0, ha="right" if len(przedzialy) > 6
                  else "center", color=TEKST_POBOCZNY, fontsize=8)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=None))
    ax.tick_params(axis="y", colors=TEKST_POBOCZNY, labelsize=8, length=0)
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("udział wierszy", color=TEKST_POBOCZNY, fontsize=9)
    ax.grid(axis="y", color=SIATKA, linewidth=0.8)
    ax.set_axisbelow(True)
    for strona in ("top", "right", "left"):
        ax.spines[strona].set_visible(False)
    ax.spines["bottom"].set_color(SIATKA)
    ax.legend(frameon=False, fontsize=8, labelcolor=TEKST, loc="upper left", bbox_to_anchor=(0, -0.22 if len(
        przedzialy) > 6 else -0.12), ncol=1)
    fig.tight_layout()
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(sciezka, facecolor=TLO)
    plt.close(fig)


def poniedzialki(od: date, do: date) -> list[date]:
    """Kolejne poniedziałki z przedziału [od, do]: t0 cotygodniowego sprawdzania."""
    pierwszy = od + timedelta(days=(7 - od.weekday()) % 7)
    return [pierwszy + timedelta(weeks=i) for i in range((do - pierwszy).days // 7 + 1)] if pierwszy <= do else []
