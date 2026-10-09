"""Pełny przebieg: świat B2B -> kalibracja -> wszystkie tabele -> zapis CSV -> klucz odpowiedzi."""

from __future__ import annotations

import shutil
import time
import zipfile
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

from . import export_b2b as ex
from .calibrate import calibrate
from .config import Params, N_DAYS
from .ecom import EcomGen, build_subscriptions, build_gift_cards, build_nbp
from .features import prepare, Snapshotter, agency_features
from .models import TRAIN_SNAPSHOTS, CALIB_SNAPSHOTS, TEST_SNAPSHOT
from .names import AM_NAMES, AM_REGION
from .pos import PosGen, NEW_COLUMN_FROM
from .population import lokale
from .products import build_pos_products, build_ecom_products
from .timeutil import DAYS, day_index
from .world import build_world, build_erp, rng_for

POS_ZIP = "pos_paragony.zip"
OUT_DIRS = ["crm", "erp", "pos", "ecom", "iot", "helpdesk", "nbp", "agencja"]


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# POS — zapis plików dziennych (równolegle per lokal)
# ---------------------------------------------------------------------------
def _pos_worker(args) -> pd.DataFrame:
    P, lok, cat, lokal, out = args
    g = PosGen(P, lok, cat)
    dup_days = {day_index(d) for d in P.pos_dup_days}
    pozs, neg, files, stats = [], [], [], {"paragony": 0, "bez_metody": 0, "storno": 0}
    for d, (par, poz) in g.days_for(lokal, range(N_DAYS)):
        pozs.append(poz)
        m = poz.merge(par[["nr_paragonu", "storno"]], on="nr_paragonu")
        neg.append(m[(m.ilosc < 0) & (m.storno == 0)])
        stats["paragony"] += len(par)
        stats["bez_metody"] += int((par.metoda_platnosci == "").sum())
        stats["storno"] += int(par.storno.sum())
        date = DAYS[d].strftime("%Y-%m-%d")
        f = par.assign(data_czas=par.data_czas.dt.strftime("%Y-%m-%d %H:%M:%S"))
        cols = ["lokal", "nr_paragonu", "data_czas", "kwota_brutto", "metoda_platnosci", "storno"]
        if d >= NEW_COLUMN_FROM:  # dostawca POS dodał kolumnę bez ostrzeżenia
            cols = ["lokal", "nr_paragonu", "data_czas", "kanal", "kwota_brutto", "metoda_platnosci", "storno"]
        text = f[cols].to_csv(sep=";", decimal=",", float_format="%.2f", index=False, lineterminator="\r\n")
        files.append((f"pos_paragony_{lokal}_{date}.csv", text.encode("cp1250")))
        if lokal == 17 and d in dup_days:  # ponowna wysyłka pliku przez dostawcę
            files.append((f"pos_paragony_{lokal}_{date} (1).csv", text.encode("cp1250")))
    return pd.concat(pozs, ignore_index=True), pd.concat(neg, ignore_index=True), stats, files


def write_pos(P: Params, lok: pd.DataFrame, cat: pd.DataFrame, root: Path, workers: int = 8) -> dict:
    (root / "pos").mkdir(parents=True, exist_ok=True)
    with Pool(workers) as pool:
        parts = pool.map(_pos_worker, [(P, lok, cat, int(l), None) for l in lok.lokal])
    # ~24 tys. plików dziennych w jednym archiwum (stała data wpisów -> archiwum powtarzalne)
    with zipfile.ZipFile(root / "pos" / POS_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, data in sorted(f for p in parts for f in p[3]):
            zi = zipfile.ZipInfo(f"paragony/{name}", date_time=(2026, 9, 30, 23, 59, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, data)
    poz = pd.concat([p[0] for p in parts], ignore_index=True)
    poz["ilosc"] = poz.ilosc.astype(int)
    _parquet(poz, root / "pos" / "pos_pozycje.parquet")
    stats = pd.DataFrame([p[2] for p in parts], index=lok.lokal.to_numpy())
    return {"n_pozycji": len(poz), "neg": pd.concat([p[1] for p in parts], ignore_index=True), "stats": stats}


# ---------------------------------------------------------------------------
def _parquet(df: pd.DataFrame, path: Path) -> None:
    """Zapis Parquet (zstd). Puste napisy -> null, żeby braki były jawne w typach kolumn."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == object or str(df[c].dtype) in ("str", "string"):
            df[c] = df[c].astype(object).where(df[c].astype(object) != "", None)
    df.reset_index(drop=True).to_parquet(path, index=False, engine="pyarrow", compression="zstd")


def generate(seed: int, root: Path, key_dir: Path, workers: int = 8) -> dict:
    t0 = time.time()
    P = Params(seed=seed)
    for d in OUT_DIRS:
        shutil.rmtree(root / d, ignore_errors=True)
    _log("krok 1–3: encje, ukryte ryzyko, odejścia, sygnały")
    W = build_world(P)
    lok = lokale(rng_for(P, 30))
    pos_cat = build_pos_products()
    ecom_prod = build_ecom_products(rng_for(P, 31))

    _log("kalibracja mostu przychodu (wrzesień 2026)")
    cal = calibrate(P, W, lok, pos_cat, ecom_prod, log=lambda m: _log("  " + m))
    if not cal["converged"]:
        raise RuntimeError("kalibracja nie zbiegła się — zmień ziarno lub parametry")
    build_erp(W, P.b2b_price_mult, P.n_fanout_pairs)

    _log("tabele CRM / ERP / IoT / helpdesk")
    T = {}
    T.update(ex.crm_tables(W, P.b2b_price_mult, rng_for(P, 20)))
    T.update(ex.iot_tables(W))
    T["helpdesk_zgloszenia"] = ex.helpdesk_table(W)
    T.update(ex.erp_tables(W))
    T["crm_opiekunowie"] = pd.DataFrame({"am_id": range(1, 7), "imie_nazwisko": AM_NAMES, "region": AM_REGION})

    _log("e-commerce, subskrypcje, karty, kursy NBP")
    eg = EcomGen(P, ecom_prod)
    orders, opos = eg.build()
    subs = build_subscriptions(P)
    gift = build_gift_cards(P)
    nbp = build_nbp(P)
    T["ecom_zamowienia"] = pd.DataFrame({
        "id": orders.id, "data_utc": orders.data_utc,
        "waluta": orders.waluta, "brutto": orders.brutto, "email": orders.email,
        "notatka": orders.notatka, "zwrot": orders.zwrot, "metoda_platnosci": orders.metoda_platnosci})
    T["ecom_pozycje"] = opos
    T["ecom_subskrypcje"] = pd.DataFrame({"id": subs.id, "plan": subs.plan,
                                          "data_platnosci": subs.data_platnosci,
                                          "kwota": subs.kwota})
    T["karty_podarunkowe"] = gift[["kod", "data_sprzedazy", "data_realizacji", "kwota"]]
    T["kursy_nbp"] = nbp
    T["ecom_produkty"] = ecom_prod[["sku", "nazwa", "cena_brutto_pln"]].assign(
        cena_brutto_pln=lambda d: (d.cena_brutto_pln * P.ecom_price_mult).round(2))
    T["pos_produkty"] = pos_cat[["kod_produktu", "nazwa", "kategoria", "cena_brutto", "vat"]]
    T["lokale"] = lok[["lokal", "nazwa", "miasto", "adres", "data_otwarcia"]]

    _log("cechy agencji (agencja_features.parquet)")
    S = Snapshotter(prepare(T))
    agency = agency_features(S, TRAIN_SNAPSHOTS + CALIB_SNAPSHOTS + [TEST_SNAPSHOT])
    T["agencja_features"] = agency

    _log("zapis Parquet")
    layout = {
        "crm": ["crm_biura", "crm_umowy_historia", "crm_kontakty_am", "ankiety_nps", "crm_opiekunowie"],
        "erp": ["erp_kontrahenci", "erp_kontrahenci_archiwum", "erp_faktury", "erp_pozycje", "erp_platnosci",
                "erp_kartoteka"],
        "ecom": ["ecom_zamowienia", "ecom_pozycje", "ecom_subskrypcje", "karty_podarunkowe", "ecom_produkty"],
        "iot": ["iot_ekspresy", "iot_telemetria"], "helpdesk": ["helpdesk_zgloszenia"], "nbp": ["kursy_nbp"],
        "pos": ["pos_produkty", "lokale"], "agencja": ["agencja_features"],
    }
    for d, names in layout.items():
        for n in names:
            _parquet(T[n], root / d / f"{n}.parquet")
    _log("POS: pliki dzienne paragonów (CSV cp1250 w archiwum zip)")
    pos_info = write_pos(P, lok, pos_cat, root, workers=workers)

    _log("klucz odpowiedzi")
    from .answer_key import build_answer_key
    key = build_answer_key(P, W, T, cal, pos_info, orders, subs, gift, lok, pos_cat, ecom_prod, root, key_dir)
    _log(f"gotowe w {time.time() - t0:.0f} s")
    return key
