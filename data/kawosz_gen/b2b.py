"""ERP — kontrahenci, faktury, pozycje, płatności (kanał „Kawosz dla Biur”).

Faktura miesięczna (ostatni dzień roboczy miesiąca) zawiera abonament planu
oraz dostawy kawy i materiałów z miesiąca. Dostawy kawy wynikają z modelu
zapasu: biuro zamawia, gdy zapas spadnie poniżej progu — przy spadku spożycia
przerwy między zamówieniami rosną (sygnał „recency”).

Kwoty bazowe zapisywane są bez mnożnika poziomu cen; `price_mult` (kalibrowany)
stosowany jest przy materializacji tabel, więc suma przychodu B2B jest liniowa
względem tego parametru.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from .churn import Sim
from .config import Params, N_DAYS, EXPORT, BURN_IN
from .timeutil import months_in_range, last_workday_of_month, day_index, to_date, HOLIDAYS

HOUSE_KEYS = ["BIURO CLASSIC", "BIURO CREMA", "BIURO STRONG", "BIURO DECAF", "BIURO ORGANIC"]
HOUSE_W = [0.36, 0.30, 0.18, 0.04, 0.12]


def build_lines(P: Params, rng: np.random.Generator, off: pd.DataFrame, sim: Sim,
                plan_m: np.ndarray, price_m: np.ndarray, kart: pd.DataFrame, refs: dict,
                awaria_m: dict, machines: pd.DataFrame) -> pd.DataFrame:
    """Pozycje faktur miesięcznych (cena bazowa netto, przed mnożnikiem)."""
    n = len(off)
    price_of = kart.set_index("indeks").cena_netto
    months = months_in_range()
    ch = sim.churn.set_index("office").reindex(off.idx)
    start = off.start_day.to_numpy()
    end = np.where(ch.churned.to_numpy(), ch.end_excl.to_numpy(), N_DAYS)
    gpd = np.exp(rng.normal(np.log(0.0105), 0.12, size=n))  # kg kawy na napój
    house = rng.choice(len(HOUSE_KEYS), size=n, p=HOUSE_W)
    origin_lover = rng.random(n) < 0.22
    milk_user = rng.random(n) < 0.72
    plant_milk = rng.random(n) < 0.3
    cups_user = rng.random(n) < 0.38
    n_mach = machines.groupby("office").size().reindex(off.idx).fillna(1).to_numpy()
    origins = [k for k in price_of.index if k.startswith("10.02") and price_of[k] > 60]
    stock = np.zeros(n)
    rows = []
    aw_by_office_month: dict[tuple[int, int], int] = {}
    old_machine = machines.install_day.to_numpy() < -730
    for mi, ds in awaria_m.items():
        if old_machine[mi]:
            for d in ds:
                dd = to_date(d)
                aw_by_office_month[(int(machines.office.iat[mi]), dd.year * 12 + dd.month)] = \
                    aw_by_office_month.get((int(machines.office.iat[mi]), dd.year * 12 + dd.month), 0) + 1

    for (y, mth) in months:
        a = day_index(dt.date(y, mth, 1))
        b = day_index(dt.date(y + (mth == 12), mth % 12 + 1, 1)) if (y, mth) != (2026, 9) else N_DAYS
        if (y, mth) == (2026, 9):
            b = day_index(dt.date(2026, 10, 1))
        dim = b - a
        inv_day = day_index(last_workday_of_month(y, mth))
        lo = np.clip(start, a, b)
        hi = np.clip(end, a, b)
        act_days = np.clip(hi - lo, 0, None)
        susp = np.array([sim.suspended[i, max(lo[i], 0):min(hi[i], N_DAYS)].sum() if act_days[i] else 0
                         for i in range(n)])
        frac = (act_days - 0.5 * susp) / dim
        drinks_m = sim.drinks[:, a:min(b, N_DAYS)].sum(1)
        cons = drinks_m * gpd
        avg = np.maximum(off.liczba_pracownikow.to_numpy() * off.dpe.to_numpy() * 21 * gpd, 1)
        is_new = (start >= a) & (start < b)
        stock = np.where(is_new, 1.2 * avg, stock)
        stock = stock - cons
        pack = np.where(avg >= 8, 6.0, 1.0)
        need = (stock < 0.45 * avg) & (act_days > 0)
        q = np.where(need, np.ceil((1.25 * avg - stock) / pack) * pack, 0.0)
        # biuro po wypowiedzeniu nie uzupełnia zapasu
        leaving = ch.churned.to_numpy() & (ch.event_day.to_numpy() < a)
        q = np.where(leaving, 0.0, q)
        stock = np.maximum(stock + q, 0)
        mkey = y * 12 + mth
        for i in np.where(act_days > 0)[0]:
            if inv_day >= end[i] and end[i] < b:
                d_inv = max(end[i] - 1, a)
                while to_date(d_inv).weekday() >= 5 or to_date(d_inv) in HOLIDAYS:
                    d_inv -= 1
                d_inv = max(d_inv, a)
            else:
                d_inv = inv_day
            if start[i] > d_inv:
                d_inv = start[i]
            base = (i, d_inv)
            plan_i = plan_m[i, a if a >= 0 else 0]
            rows.append(base + (refs["plans"][plan_i], 1.0, round(price_m[i, max(a, 0)] * frac[i], 2), "abonament"))
            if q[i] > 0:
                k = refs["house"][HOUSE_KEYS[house[i]]]
                if pack[i] == 6 and rng.random() < 0.8:
                    k = refs["house6"][HOUSE_KEYS[house[i]]]  # karton 6 kg
                    rows.append(base + (k, q[i] / 6, float(price_of[k]), "kawa"))
                else:
                    rows.append(base + (k, q[i], float(price_of[k]), "kawa"))
                if origin_lover[i] and rng.random() < 0.5:
                    ok = origins[int(rng.integers(len(origins)))]
                    rows.append(base + (ok, float(rng.integers(1, 4)), float(price_of[ok]), "kawa"))
            if milk_user[i] and drinks_m[i] > 0:
                liters = max(1.0, np.round(drinks_m[i] * 0.05))
                mk = refs["consumables"]["MLEKO UHT 3,2% 1L"]
                rows.append(base + (mk, liters, float(price_of[mk]), "mleko"))
                if plant_milk[i]:
                    pk = refs["consumables"]["NAPÓJ OWSIANY BARISTA 1L"]
                    rows.append(base + (pk, max(1.0, np.round(liters * 0.18)), float(price_of[pk]), "mleko"))
            if cups_user[i] and rng.random() < 0.4 and drinks_m[i] > 0:
                ck = list(refs["cups"].values())[int(rng.integers(0, 5))]
                rows.append(base + (ck, 1.0, float(price_of[ck]), "kubki"))
            if rng.random() < 0.5 and drinks_m[i] > 0:
                tk = refs["cleaning"]["TABLETKI CZYSZCZĄCE (100 SZT)"]
                rows.append(base + (tk, float(n_mach[i]), float(price_of[tk]), "czyszczenie"))
            if rng.random() < 0.22 and drinks_m[i] > 0:
                sk = refs["consumables"][["CUKIER SASZETKI 1000 SZT", "MIESZADEŁKA DREWNIANE 1000 SZT",
                                          "CZEKOLADA DO PICIA 1KG"][int(rng.integers(0, 3))]]
                rows.append(base + (sk, 1.0, float(price_of[sk]), "dodatki"))
            na = aw_by_office_month.get((int(i), mkey), 0)
            if na:
                rk = refs["services"]["SERWIS POGWARANCYJNY – ROBOCIZNA"]
                dk = refs["services"]["DOJAZD SERWISU"]
                rows.append(base + (rk, float(na), float(price_of[rk]), "serwis"))
                rows.append(base + (dk, float(na), float(price_of[dk]), "serwis"))
    lines = pd.DataFrame(rows, columns=["office", "day", "indeks", "ilosc", "cena_base", "rodzaj"])
    lines = lines[lines.cena_base * lines.ilosc > 0].reset_index(drop=True)
    return lines


def build_kontrahenci(P: Params, rng: np.random.Generator, off: pd.DataFrame, sim: Sim,
                      sept_rank: np.ndarray) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Rejestr kontrahentów (aktywne umowy) + archiwum. 112 rozmytych duplikatów.

    `sept_rank` — kolejność biur kandydujących na duplikaty z identycznym NIP-em
    (fan-out w hurtowni). Pierwsze `P.n_fanout_pairs` dostaje identyczny NIP.
    """
    exp_day = day_index(EXPORT)
    ch = sim.churn.set_index("office").reindex(off.idx)
    in_reg = ~(ch.churned.to_numpy() & (ch.end_excl.to_numpy() <= exp_day))
    order = np.argsort(off.start_day.to_numpy(), kind="stable")
    kid = np.empty(len(off), dtype=int)
    kid[order] = 200001 + np.arange(len(off))

    def nip_fmt(n: str, style: int) -> str:
        if style == 1:
            return f"{n[:3]}-{n[3:6]}-{n[6:8]}-{n[8:]}"
        if style == 2:
            return f"{n[:3]}-{n[3:5]}-{n[5:7]}-{n[7:]}"
        return n

    def erp_name(name: str, style: int) -> str:
        if style == 0:
            return name
        return name.upper()

    styles = rng.choice(3, size=len(off), p=[0.7, 0.2, 0.1])
    nstyle = rng.choice(2, size=len(off), p=[0.4, 0.6])
    moved = set(sim.events_extra.loc[sim.events_extra.typ == "przeprowadzka", "office"])
    base = pd.DataFrame({
        "office": off.idx.to_numpy(), "id_kontrahenta": kid,
        "nazwa": [erp_name(n, s) for n, s in zip(off.nazwa, nstyle)],
        "nip": [nip_fmt(n, s) for n, s in zip(off.nip, styles)],
        "adres": off.adres.to_numpy(), "kod_pocztowy": off.kod_pocztowy.to_numpy(),
        "id_biura_crm": np.where(rng.random(len(off)) < 0.94, off.id_biura.astype(str), ""),
        "in_reg": in_reg,
    })
    # ~8 NIP-ów z 9 cyframi wśród oryginałów (literówka)
    typo_orig = rng.choice(np.where(in_reg)[0], size=8, replace=False)
    for i in typo_orig:
        digits = base.at[i, "nip"].replace("-", "")
        j = int(rng.integers(1, 9))
        base.at[i, "nip"] = digits[:j] + digits[j + 1:]

    # duplikaty: wybór wśród biur w rejestrze, 112 sztuk
    reg_idx = np.where(in_reg)[0]
    cand = [i for i in sept_rank if in_reg[i] and i not in set(typo_orig)]
    fan = cand[: P.n_fanout_pairs]
    rest_pool = np.setdiff1d(reg_idx, np.array(fan + list(typo_orig)))
    rest = list(rng.choice(rest_pool, size=P.n_duplicates - len(fan), replace=False))
    dup_rows = []
    typo_dups = set(rng.choice(rest, size=7, replace=False).tolist())
    for j, i in enumerate(fan + rest):
        o = off.iloc[i]
        orig_nip = base.at[i, "nip"]
        digits = orig_nip.replace("-", "")
        if i in fan:
            nip = orig_nip  # identyczny ciąg znaków -> fan-out przy złączeniu po NIP
        elif i in typo_dups:
            k = int(rng.integers(1, 9))
            nip = digits[:k] + digits[k + 1:]
        else:
            nip = nip_fmt(digits, 1) if "-" not in orig_nip else digits
        core = o.nazwa
        for pre in ("Biurowiec ", "Grupa ", "Studio ", "Centrum ", "Biuro ", "Hub ", "Park "):
            core = core.replace(pre, "")
        if rng.random() < 0.6:
            nm = core.upper().replace(".", "").replace("SP Z O O", "SP Z O O").replace(" SP K", " SPK")
        else:
            nm = core.replace("Sp. z o.o.", "spółka z o.o.").replace("S.A.", "Spółka Akcyjna")
        dup_day = int(rng.integers(max(o.start_day, 0), max(o.start_day, 0) + 600)) if o.start_day < 800 else int(o.start_day + 5)
        dup_rows.append(dict(office=i, id_kontrahenta=0, nazwa=nm, nip=nip,
                             adres=o.adres if i not in moved else o.adres,
                             kod_pocztowy=o.kod_pocztowy,
                             id_biura_crm=str(o.id_biura) if rng.random() < 0.15 else "",
                             in_reg=True, dup_day=min(dup_day, N_DAYS - 20), fanout=i in fan))
    dups = pd.DataFrame(dup_rows)
    dups["id_kontrahenta"] = 260001 + np.arange(len(dups))
    reg = pd.concat([base[base.in_reg], dups[base.columns]], ignore_index=True)
    reg = reg.sort_values("id_kontrahenta").reset_index(drop=True)
    arch = base[~base.in_reg].sort_values("id_kontrahenta").reset_index(drop=True)
    info = {"fanout_offices": [int(x) for x in fan], "dup_offices": [int(x) for x in fan + rest],
            "typo_nip_original": [int(x) for x in typo_orig], "typo_nip_dup": sorted(int(x) for x in typo_dups),
            "dups": dups, "kid": kid}
    return reg, arch, info


def materialize_invoices(P: Params, rng_seed: int, lines: pd.DataFrame, kid: np.ndarray, dups: pd.DataFrame,
                         price_mult: float, korekty_seed: int, sim: Sim, off: pd.DataFrame,
                         big_sale: dict) -> dict:
    """Tworzy erp_faktury / erp_pozycje / erp_platnosci z pozycji bazowych."""
    rng = np.random.default_rng(rng_seed)
    L = lines.copy()
    L["cena"] = (L.cena_base * price_mult).round(2)
    L["wartosc"] = (L.cena * L.ilosc).round(2)
    # przypisanie faktury: kontrahent oryginalny lub duplikat (po dacie powstania duplikatu)
    inv = L.groupby(["office", "day"], as_index=False).agg(kwota_netto=("wartosc", "sum"))
    inv["id_kontrahenta"] = kid[inv.office.to_numpy()]
    d = dups.set_index("office")
    u = rng.random(len(inv))
    is_dup_office = inv.office.isin(d.index).to_numpy()
    use_dup = np.zeros(len(inv), dtype=bool)
    use_dup[is_dup_office] = (inv.day.to_numpy()[is_dup_office] >= d.loc[inv.office[is_dup_office], "dup_day"].to_numpy()) & (u[is_dup_office] < 0.5)
    inv.loc[use_dup, "id_kontrahenta"] = d.loc[inv.office[use_dup], "id_kontrahenta"].to_numpy()
    # sprzedaż 40 ekspresów (prawdziwa, duża faktura)
    bs = pd.DataFrame([dict(office=big_sale["office"], day=big_sale["day"], kwota_netto=0.0,
                            id_kontrahenta=kid[big_sale["office"]])])
    big_lines = pd.DataFrame([
        dict(office=big_sale["office"], day=big_sale["day"], indeks=big_sale["indeks"], ilosc=40.0,
             cena=round(big_sale["price"] * price_mult, 2), rodzaj="ekspresy"),
        dict(office=big_sale["office"], day=big_sale["day"], indeks=big_sale["inst_indeks"], ilosc=40.0,
             cena=round(big_sale["inst_price"] * price_mult, 2), rodzaj="ekspresy")])
    big_lines["wartosc"] = (big_lines.cena * big_lines.ilosc).round(2)
    bs["kwota_netto"] = big_lines.wartosc.sum()
    bs["big"] = True
    inv["big"] = False
    inv = pd.concat([inv, bs], ignore_index=True).sort_values(["day", "id_kontrahenta", "big"]).reset_index(drop=True)
    dd = pd.to_datetime("2024-01-01") + pd.to_timedelta(inv.day, unit="D")
    inv["seq"] = inv.groupby([dd.dt.year, dd.dt.month]).cumcount() + 1
    inv["nr_faktury"] = [f"FV/{t.year}/{t.month:02d}/{s:05d}" for t, s in zip(dd, inv.seq)]
    inv["data"] = dd.dt.date
    inv["typ"] = "faktura"
    inv["waluta"] = "PLN"
    inv["kwota_netto"] = inv.kwota_netto.round(2)
    inv["vat"] = (inv.kwota_netto * 0.23).round(2)
    key = inv.set_index(["office", "day", "big"]).nr_faktury
    L["big"] = False
    big_lines["big"] = True
    allL = pd.concat([L, big_lines], ignore_index=True)
    allL["nr_faktury"] = key.loc[list(zip(allL.office, allL.day, allL.big))].to_numpy()

    # korekty (reklamacje) — ujemne dokumenty z odwołaniem do faktury
    krng = np.random.default_rng(korekty_seed)
    risk_at = sim.risk[inv.office.to_numpy(), np.clip(inv.day.to_numpy(), 0, N_DAYS - 1) + BURN_IN]
    p_k = P.korekta_rate * (0.6 + 0.8 * P.signal_strength * np.minimum(risk_at, 2))
    pick = (krng.random(len(inv)) < p_k) & ~inv.big.to_numpy()
    kor_rows, kor_lines = [], []
    lines_by_inv = allL.groupby("nr_faktury")
    for r in inv[pick].itertuples():
        kd = r.day + int(krng.integers(3, 41))
        if kd >= N_DAYS:
            continue
        g = lines_by_inv.get_group(r.nr_faktury)
        # połowa reklamacji to rabat za przestój ekspresu (korekta abonamentu)
        abon = krng.random() < 0.5
        g2 = g[(g.rodzaj == "abonament") == abon]
        g = g2 if len(g2) else g
        ln = g.iloc[int(krng.integers(len(g)))]
        frac = float(krng.choice([0.1, 0.2, 0.25, 0.5, 1.0], p=[0.15, 0.2, 0.25, 0.25, 0.15]))
        qty = -round(ln.ilosc * frac, 2) if ln.ilosc * frac >= 0.01 else -ln.ilosc
        kid_ = len(kor_rows)
        kor_lines.append(dict(k=kid_, indeks=ln.indeks, ilosc=qty, cena=ln.cena))
        kor_rows.append(dict(k=kid_, office=r.office, day=kd, id_kontrahenta=r.id_kontrahenta,
                             ref=r.nr_faktury, kwota_netto=round(qty * ln.cena, 2)))
    kor = pd.DataFrame(kor_rows).sort_values(["day", "id_kontrahenta", "k"]).reset_index(drop=True)
    kdd = pd.to_datetime("2024-01-01") + pd.to_timedelta(kor.day, unit="D")
    kor["seq"] = kor.groupby([kdd.dt.year, kdd.dt.month]).cumcount() + 1
    kor["nr_faktury"] = [f"KOR/{t.year}/{t.month:02d}/{s:04d}" for t, s in zip(kdd, kor.seq)]
    kor["data"] = kdd.dt.date
    kor["typ"] = "korekta"
    kor["waluta"] = "PLN"
    kor["vat"] = (kor.kwota_netto * 0.23).round(2)
    kl = pd.DataFrame(kor_lines)
    kl["nr_faktury"] = kl.k.map(kor.set_index("k").nr_faktury)

    cols = ["nr_faktury", "id_kontrahenta", "data", "typ", "waluta", "kwota_netto", "vat"]
    faktury = pd.concat([inv.assign(office=inv.office)[cols + ["office", "day"]],
                         kor[cols + ["office", "day"]]], ignore_index=True)
    faktury = faktury.sort_values(["day", "nr_faktury"]).reset_index(drop=True)
    pozycje = pd.concat([allL[["nr_faktury", "indeks", "ilosc", "cena"]],
                         kl[["nr_faktury", "indeks", "ilosc", "cena"]]], ignore_index=True)

    # płatności
    prng = np.random.default_rng(rng_seed + 7)
    fin_risk = np.zeros_like(sim.risk)
    eps = sim.episodes[sim.episodes.cause == "finanse"]
    t = np.arange(sim.risk.shape[1])
    for e in eps.itertuples():
        x = t - (e.start + BURN_IN)
        shape = np.where(x < 0, 0.0, np.where(x < e.ramp, x / e.ramp, np.where(
            x < e.ramp + e.plateau, 1.0, np.exp(-(x - e.ramp - e.plateau) / e.tau))))
        fin_risk[e.office] += e.severity * shape
    fv = faktury[faktury.typ == "faktura"].copy()
    o = fv.office.to_numpy()
    dday = fv.day.to_numpy()
    pay_trait = off.pay_trait.to_numpy()[o]
    fr = fin_risk[o, np.clip(dday + 14, 0, N_DAYS - 1) + BURN_IN]
    r_all = sim.risk[o, np.clip(dday + 14, 0, N_DAYS - 1) + BURN_IN]
    k = P.signal_strength
    delay = pay_trait + k * (14.0 * fr + 2.5 * r_all) + prng.normal(0, 2.5, len(fv)) - 1.5
    spor = prng.random(len(fv)) < (0.012 + k * 0.03 * np.minimum(r_all, 2))
    delay = np.where(spor, delay + prng.uniform(25, 90, len(fv)), delay)
    pay_day = dday + 14 + np.round(np.maximum(delay, -12)).astype(int)
    ok = pay_day < N_DAYS
    kw = (fv.kwota_netto + fv.vat).round(2).to_numpy()
    plat = pd.DataFrame({"nr_faktury": fv.nr_faktury.to_numpy()[ok],
                         "data_platnosci": (pd.Timestamp("2024-01-01") + pd.to_timedelta(pay_day[ok], unit="D")).date,
                         "kwota": kw[ok], "spor": spor[ok], "office": o[ok], "pay_day": pay_day[ok]})
    # przesunięcie płatności z weekendów na poniedziałek
    wd = pd.to_datetime(plat.data_platnosci).dt.dayofweek
    shift = np.where(wd == 5, 2, np.where(wd == 6, 1, 0))
    plat["pay_day"] = plat.pay_day + shift
    plat = plat[plat.pay_day < N_DAYS].copy()
    plat["data_platnosci"] = (pd.Timestamp("2024-01-01") + pd.to_timedelta(plat.pay_day, unit="D")).dt.date
    plat = plat.sort_values(["pay_day", "nr_faktury"]).reset_index(drop=True)
    return {"faktury": faktury, "pozycje": pozycje, "platnosci": plat}
