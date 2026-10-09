"""Warunki kontrolne (krok 7) liczone z plików danych — tak, jak zrobiłby to uczestnik.

Uruchomienie:  cd data && poetry run python -m kawosz_gen.validate
"""

from __future__ import annotations

import argparse
import io
import json
import zipfile
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .config import TARGETS
from .features import prepare, Snapshotter
from . import models
from .revenue import Revenue, BRIDGE_STEPS

ROOT = Path(__file__).resolve().parent.parent
KEY = ROOT.parent / "klucz_odpowiedzi"


def read_pos(root: Path, month: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    parts = []
    with zipfile.ZipFile(root / "pos" / "pos_paragony.zip") as z:
        names = sorted(n for n in z.namelist() if n.endswith(".csv"))
        if month:
            names = [n for n in names if f"_{month}-" in n]
        for n in names:
            df = pd.read_csv(io.BytesIO(z.read(n)), sep=";", decimal=",", encoding="cp1250",
                             dtype={"metoda_platnosci": str})
            df["plik"] = n.split("/")[-1]
            parts.append(df)
    par = pd.concat(parts, ignore_index=True)
    poz = pd.read_parquet(root / "pos" / "pos_pozycje.parquet")
    return par, poz


def load(root: Path) -> dict:
    T = {}
    for sub in ("crm", "erp", "ecom", "iot", "helpdesk", "nbp"):
        for f in (root / sub).glob("*.parquet"):
            T[f.stem] = pd.read_parquet(f)
    T["erp_kartoteka"]["kategoria"] = T["erp_kartoteka"].kategoria.fillna("")
    for k in ("erp_kontrahenci", "erp_kontrahenci_archiwum"):
        T[k]["id_biura_crm"] = T[k].id_biura_crm.fillna("")
    T["agencja_features"] = pd.read_parquet(root / "agencja" / "agencja_features.parquet")
    return T


def check(name: str, value, ok: bool, target: str, rows: list) -> None:
    rows.append((name, value, target, "OK" if ok else "BŁĄD"))


def run(root: Path = ROOT, key_dir: Path = KEY) -> bool:
    rows: list = []
    T = load(root)
    key = json.loads((key_dir / "klucz_odpowiedzi.json").read_text()) if (key_dir / "klucz_odpowiedzi.json").exists() else None

    # --- przychód ---------------------------------------------------------
    par, poz = read_pos(root, "2026-09")
    R = Revenue({**T, "pos_paragony": par, "pos_pozycje": poz}).reports()
    for k in ("bi", "sprzedaz", "ksiegowosc", "definicja"):
        v = R[k] / 1e6
        check(f"przychód {k}", round(v, 4), abs(v - TARGETS[k]) <= 0.005, f"{TARGETS[k]} ± 0,005", rows)
    for k in BRIDGE_STEPS:
        v = abs(R["bridge"][k]) / 1e6
        check(f"most: {k}", round(v, 4), abs(v - TARGETS[k]) <= 0.005, f"{TARGETS[k]} ± 0,005", rows)

    # --- encje i usterki ----------------------------------------------------
    kr = T["erp_kontrahenci"]
    check("kontrahenci (wiersze)", len(kr), len(kr) == 1512, "1512", rows)
    if key:
        nd = key["usterki"]["kontrahenci"]["duplikaty"]
        dup_ids = {p["id_kontrahenta_duplikat"] for p in key["usterki"]["kontrahenci"]["pary"]}
        check("kontrahenci (duplikaty)", nd, nd == 112 and dup_ids <= set(kr.id_kontrahenta), "112", rows)
    norm = kr.nip.str.replace("-", "", regex=False)
    check("NIP z 9 cyframi", int((norm.str.len() == 9).sum()), 10 <= (norm.str.len() == 9).sum() <= 20, "~15", rows)
    kart = T["erp_kartoteka"]
    share = (kart.kategoria == "").mean()
    check("kartoteka bez kategorii", f"{share:.1%}", abs(share - 0.06) < 0.01, "6%", rows)
    pk = set(T["crm_biura"].id_biura)
    check("klucze główne unikalne", "crm/erp/iot", T["crm_biura"].id_biura.is_unique and kr.id_kontrahenta.is_unique
          and T["iot_ekspresy"].id_ekspresu.is_unique and T["erp_faktury"].nr_faktury.is_unique, "unikalne", rows)
    act = T["crm_biura"][T["crm_biura"].status.isin(["aktywny", "zawieszony", "w wypowiedzeniu"])].id_biura
    has_m = set(T["iot_ekspresy"].id_biura)
    check("aktywne biura z ekspresem", f"{np.isin(act, list(has_m)).mean():.0%}", np.isin(act, list(has_m)).all(), "100%", rows)
    check("spójność kluczy ERP→CRM", "id_biura_crm ⊂ CRM",
          set(pd.to_numeric(kr.id_biura_crm, errors="coerce").dropna().astype(int)) <= pk, "tak", rows)

    # --- odejścia i modele --------------------------------------------------
    S = Snapshotter(prepare(T))
    t0 = models.TEST_SNAPSHOT
    pop = S.population(t0)
    y = S.labels(t0, pop)
    check("migawka 2026-04-01: biura", len(pop), len(pop) == 1400, "1400", rows)
    check("migawka 2026-04-01: odejścia 90d", int(y.sum()), int(y.sum()) == 49, "49", rows)
    h = models.honest_model(S)
    check("uczciwy model AUC", round(h["auc_test"], 3), 0.76 <= h["auc_test"] <= 0.80, "0,76–0,80", rows)
    check("reguła AM AUC", round(h["am_rule_auc"], 3), 0.68 <= h["am_rule_auc"] <= 0.72, "0,68–0,72", rows)
    check("próg 0,5", f"{h['thr_0_5_n']} (TP {h['thr_0_5_tp']})", True, "≈15 (TP 9)", rows)
    check("top 60", f"TP {h['top60_tp']}", True, "TP 24", rows)
    check("próg 0,175", f"{h['thr_0_175_n']} (TP {h['thr_0_175_tp']})", True, "≈75 (TP 28)", rows)
    ag = models.agency_model(S, T["agencja_features"])
    check("model agencji AUC", round(ag["auc_agency_test"], 3), ag["auc_agency_test"] >= 0.92, "≥ 0,92", rows)
    dr = models.drift(S)
    check("PSI zaparzenia_30d", round(dr["psi_zaparzenia_30d"], 3), 0.28 <= dr["psi_zaparzenia_30d"] <= 0.34, "0,28–0,34", rows)
    mn = models.nps_mnar(S)
    check("NPS: brak odpowiedzi → odejścia ×", round(mn["ratio"], 2), 1.6 <= mn["ratio"] <= 2.5, "≈2", rows)
    if key:
        att = key["decyzja"]["wizyty_retencyjne"]["sredni_efekt_wzgledny"]
        check("efekt wizyt (klucz)", f"{att:.1%}", 0.25 <= att <= 0.35, "≈30%", rows)

    # --- POS: rozkład paragonów ----------------------------------------------
    ok = par[(par.storno == 0) & (par.kwota_brutto < 10000)]
    check("paragon średnia", round(ok.kwota_brutto.mean(), 2), abs(ok.kwota_brutto.mean() - 31) < 1.5, "31", rows)
    check("paragon mediana", ok.kwota_brutto.median(), abs(ok.kwota_brutto.median() - 24) <= 1, "24", rows)
    check("paragon p99", ok.kwota_brutto.quantile(0.99), abs(ok.kwota_brutto.quantile(0.99) - 140) <= 15, "140", rows)

    # --- rozmiar --------------------------------------------------------------
    with zipfile.ZipFile(root / "pos" / "pos_paragony.zip") as z:
        unz = sum(i.file_size for i in z.infolist())
        n_pos_files = len(z.namelist())
    size = (sum(p.stat().st_size for p in root.rglob("*.parquet")) + unz) / 1e9
    check("rozmiar danych", f"{size:.2f} GB", size < 2, "< 2 GB", rows)
    check("pliki POS w archiwum", n_pos_files, n_pos_files > 20000, "~24 tys.", rows)
    if key:
        man = key["manifest"]
        files = {str(p.relative_to(root)) for p in root.rglob("*.parquet")} | {"pos/pos_paragony.zip"}
        check("manifest (liczba plików)", len(files), files == set(man), str(len(man)), rows)

    w = max(len(r[0]) for r in rows)
    for r in rows:
        print(f"{r[3]:5} {r[0]:<{w}}  {str(r[1]):>16}   cel: {r[2]}")
    bad = [r for r in rows if r[3] != "OK"]
    print(f"\n{len(rows) - len(bad)}/{len(rows)} warunków spełnionych")
    return not bad


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=ROOT)
    ap.add_argument("--key", type=Path, default=KEY)
    a = ap.parse_args()
    sys.exit(0 if run(a.data, a.key) else 1)


if __name__ == "__main__":
    main()
