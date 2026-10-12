"""Karty cech z katalog.yaml, modele, które z każdej cechy korzystają, i dane strony katalogu (ui/app/katalog).

Modeli nie wpisujemy w karty, tylko wyliczamy z wersji w ai/churn_model/versions/:
- cechy wersji to `cechy` z jej artefakty/meta.json, czyli to, na czym nauczony model faktycznie działa;
- wersja korzysta z katalogu, gdy jej model.py importuje api.ai.features.build (cechy z sql/, tak jak v3_katalog).
  Sama nazwa nie wystarcza: v0_agencja i v2_bez_przeciekow mają cechy o tych samych nazwach (np. zaparzenia_30d),
  ale liczone innym kodem (tabela agencji, cechy_snapszotu.sql), więc karty katalogu ich nie opisują.

    GET /api/katalog
"""

import ast
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import duckdb
import yaml

from api.adapters.duckdb_conn import PROJECT_ROOT, connect
from api.ai.churn_model import psi as psi_cech
from api.ai.features.build import KATALOG_SQL, RODZINY

PLIK = KATALOG_SQL.parent / "katalog.yaml"
WERSJE_MODELI = KATALOG_SQL.parents[1] / "churn_model" / "versions"
POMINIETE = "pominiete_cechy_agencji"
POLA = ("opis", "sql", "zrodlo", "okno", "opoznienie", "wlasciciel", "wersja")
POLA_ZRODLA = ("system", "tabele")
WERSJA = re.compile(r"^\d+\.\d+\.\d+$")
MODUL_CECH = "api.ai.features.build"
TYGODNIE_PSI = 8  # ile ostatnich tygodni PSI pokazuje strona


@dataclass(frozen=True)
class Karta:
    cecha: str
    rodzina: str
    opis: str
    sql: str
    system: str
    tabele: tuple[str, ...]
    okno: str
    opoznienie: str
    wlasciciel: str
    wersja: str


def bledy_karty(rodzina: str, cecha: str, karta: object) -> list[str]:
    """Co brakuje albo nie pasuje w karcie; pusta lista = karta kompletna."""
    if not isinstance(karta, dict):
        return [f"{cecha}: karta to nie słownik pól, tylko {type(karta).__name__}"]
    bledy = [f"{cecha}: brak pola {p}" for p in POLA if p not in karta]
    bledy += [f"{cecha}: nieznane pole {p}" for p in karta if p not in POLA]
    for pole in POLA:
        if pole != "zrodlo" and pole in karta and not (isinstance(karta[pole], str) and karta[pole].strip()):
            bledy.append(f"{cecha}: puste pole {pole}")
    zrodlo = karta.get("zrodlo")
    if "zrodlo" in karta:
        if not isinstance(zrodlo, dict) or set(zrodlo) != set(POLA_ZRODLA):
            bledy.append(f"{cecha}: zrodlo musi mieć dokładnie pola {', '.join(POLA_ZRODLA)}")
        elif not (isinstance(zrodlo["system"], str) and zrodlo["system"].strip()):
            bledy.append(f"{cecha}: puste zrodlo.system")
        elif not zrodlo["tabele"] or not all(isinstance(t, str) and t for t in zrodlo["tabele"]):
            bledy.append(f"{cecha}: zrodlo.tabele to niepusta lista nazw tabel")
    if isinstance(karta.get("wersja"), str) and not WERSJA.match(karta["wersja"]):
        bledy.append(f"{cecha}: wersja {karta['wersja']!r}, oczekiwano GŁÓWNA.PODRZĘDNA.POPRAWKA, np. 1.0.0")
    if isinstance(karta.get("sql"), str) and karta["sql"] != f"sql/{rodzina}.sql":
        bledy.append(f"{cecha}: sql {karta['sql']!r}, a cecha jest w rodzinie {rodzina} (sql/{rodzina}.sql)")
    return bledy


def wczytaj() -> list[Karta]:
    """Karty wszystkich cech w kolejności rodzin z build.RODZINY. Niekompletna karta przerywa z listą błędów."""
    katalog = yaml.safe_load(PLIK.read_text())
    if set(katalog) - {POMINIETE} != set(RODZINY):
        raise ValueError(f"rodziny w {PLIK.name} {sorted(set(katalog) - {POMINIETE})} ≠ build.RODZINY {RODZINY}")
    karty, bledy = [], []
    for rodzina in RODZINY:
        for cecha, karta in katalog[rodzina].items():
            bledy_tej = bledy_karty(rodzina, cecha, karta)
            bledy += bledy_tej
            if not bledy_tej:
                zrodlo = karta["zrodlo"]
                pola = {p: karta[p] for p in POLA if p != "zrodlo"}
                karty.append(Karta(cecha, rodzina, system=zrodlo["system"], tabele=tuple(zrodlo["tabele"]), **pola))
    if bledy:
        raise ValueError(f"niekompletne karty w {PLIK.name}:\n" + "\n".join(bledy))
    return karty


def _importuje_cechy_z_katalogu(model_py: Path) -> bool:
    """Czy model.py importuje api.ai.features.build (`import …build` albo `from …build import` albo
    `from api.ai.features import build`)."""
    for wezel in ast.walk(ast.parse(model_py.read_text())):
        if isinstance(wezel, ast.Import) and any(a.name == MODUL_CECH for a in wezel.names):
            return True
        if isinstance(wezel, ast.ImportFrom) and wezel.module:
            if wezel.module == MODUL_CECH:
                return True
            if f"{wezel.module}.build" == MODUL_CECH and any(a.name == "build" for a in wezel.names):
                return True
    return False


def wersje_modeli(katalog: Path = WERSJE_MODELI) -> list[dict]:
    """Każda wersja z artefakty/meta.json: jej cechy i to, czy liczy je katalog (sql/)."""
    wersje = []
    for folder in sorted(p for p in katalog.iterdir() if (p / "artefakty" / "meta.json").exists()):
        meta = json.loads((folder / "artefakty" / "meta.json").read_text())
        model_py = folder / "model.py"
        wersje.append(
            {
                "wersja": folder.name,
                "cechy": list(meta["cechy"]),
                "z_katalogu": model_py.exists() and _importuje_cechy_z_katalogu(model_py),
            }
        )
    return wersje


def modele_cech(karty: list[Karta], wersje: list[dict]) -> dict[str, list[str]]:
    """Cecha → wersje modeli z katalogu, które jej używają. Cecha wersji z katalogu, której nie ma w kartach,
    przerywa: model działałby na cesze bez karty."""
    nazwy = {k.cecha for k in karty}
    modele: dict[str, list[str]] = {k.cecha: [] for k in karty}
    for w in (w for w in wersje if w["z_katalogu"]):
        bez_karty = [c for c in w["cechy"] if c not in nazwy]
        if bez_karty:
            raise ValueError(f"{w['wersja']} korzysta z katalogu, ale cechy {bez_karty} nie mają karty")
        for cecha in w["cechy"]:
            modele[cecha].append(w["wersja"])
    return modele


def _psi(con: duckdb.DuckDBPyConnection) -> tuple[str | None, dict[str, dict]]:
    """Ostatnie t0 z psi_cech i dla każdej cechy: PSI z tego t0 i liczba alertów z TYGODNIE_PSI ostatnich tygodni."""
    tabela = psi_cech.TABELA_PSI
    if not con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name = ?", [tabela]).fetchone()[0]:
        return None, {}
    wiersze = con.execute(
        f"""
        WITH tygodnie AS (SELECT DISTINCT t0 FROM {tabela} ORDER BY t0 DESC LIMIT ?)
        SELECT cecha, max(t0), arg_max(psi, t0), arg_max(alert, t0), count(*) FILTER (WHERE alert), count(*)
        FROM {tabela} JOIN tygodnie USING (t0) GROUP BY cecha
        """,
        [TYGODNIE_PSI],
    ).fetchall()
    ostatnie = max((w[1] for w in wiersze), default=None)
    return (str(ostatnie) if ostatnie else None), {
        cecha: {"t0": str(t0), "psi": round(float(psi), 4), "alert": alert, "alerty": alerty, "tygodnie": tygodnie}
        for cecha, t0, psi, alert, alerty, tygodnie in wiersze
    }


def dane(baza: Path) -> dict:
    """Strona katalogu: karty z modelami i ostatnim PSI, wersje modeli i próg PSI."""
    karty = wczytaj()
    wersje = wersje_modeli()
    modele = modele_cech(karty, wersje)
    con = connect(read_only=True, db_path=baza)
    try:
        psi_t0, psi = _psi(con)
    finally:
        con.close()
    pominiete = yaml.safe_load(PLIK.read_text())[POMINIETE]
    return {
        "karty": [
            asdict(k) | {"tabele": list(k.tabele), "modele": modele[k.cecha], "psi": psi.get(k.cecha)} for k in karty
        ],
        "rodziny": RODZINY,
        "wersje": [
            {"wersja": w["wersja"], "z_katalogu": w["z_katalogu"], "cechy": len(w["cechy"])} for w in wersje
        ],
        "pominiete": [{"cecha": c, "powod": p} for c, p in pominiete.items()],
        "psi_t0": psi_t0,
        "psi_prog": psi_cech.PROG,
        "psi_tygodnie": TYGODNIE_PSI,
        "baza": str(baza.relative_to(PROJECT_ROOT)) if baza.is_relative_to(PROJECT_ROOT) else baza.name,
    }
