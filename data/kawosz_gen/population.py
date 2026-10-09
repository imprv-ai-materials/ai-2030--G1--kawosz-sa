"""Krok 1 — encje: biura (CRM), opiekunowie, ekspresy, lokale.

Liczebność populacji jest projektowana blokami 90-dniowymi zakotwiczonymi na
migawce testowej (2026-04-01): w każdym bloku odchodzi round(3,5% × N) biur,
a przybywa tyle samo plus zaplanowany wzrost. Dzięki temu na migawce testowej
aktywnych jest dokładnie 1 400 biur, a w jej oknie odchodzi dokładnie 49.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from . import names as N
from .config import Params, START, N_DAYS, BLOCK_LEN, SNAPSHOT_TEST, SNAPSHOT_TEST_N
from .products import MACHINE_MODELS
from .timeutil import day_index, to_date

AM_OF_CITY = {
    "Poznań": (1, 3), "Swarzędz": (1, 3), "Luboń": (1, 3), "Gniezno": (3,), "Kalisz": (3,),
    "Leszno": (3,), "Piła": (3,), "Konin": (3,), "Warszawa": (2,), "Radom": (2,),
    "Kraków": (4,), "Katowice": (4,), "Wrocław": (4,), "Gliwice": (4,), "Częstochowa": (4,),
    "Opole": (4,), "Kielce": (4,), "Rzeszów": (4,), "Gdańsk": (5,), "Gdynia": (5,), "Sopot": (5,),
    "Szczecin": (5,), "Bydgoszcz": (5,), "Toruń": (5,), "Olsztyn": (5,),
}

PLAN_BASE_PRICE = {"S": 1250.0, "M": 2300.0, "L": 3900.0, "XL": 6900.0}
PLANS = ["S", "M", "L", "XL"]


def blocks() -> list[tuple[int, int]]:
    """Bloki [a, b) w indeksach dni, zakotwiczone na migawce testowej."""
    a_test = day_index(SNAPSHOT_TEST)
    first = a_test % BLOCK_LEN
    out = [(0, first)] if first > 0 else []
    a = first
    while a < N_DAYS:
        out.append((a, min(a + BLOCK_LEN, N_DAYS)))
        a += BLOCK_LEN
    return out


def design_schedule(P: Params) -> pd.DataFrame:
    """Deterministyczny plan: liczba aktywnych, odejść i przybyć w blokach."""
    bl = blocks()
    a_test = day_index(SNAPSHOT_TEST)
    pre = [i for i, (a, _) in enumerate(bl) if a < a_test]
    growth_total = SNAPSHOT_TEST_N - P.n_initial_offices
    lens = np.array([bl[i][1] - bl[i][0] for i in pre], dtype=float)
    raw = growth_total * lens / lens.sum()
    g = np.floor(raw).astype(int)
    for j in np.argsort(-(raw - g))[: growth_total - g.sum()]:
        g[j] += 1
    rows, n_act = [], P.n_initial_offices
    for i, (a, b) in enumerate(bl):
        k = int(round(P.churn_rate_90d * n_act * (b - a) / BLOCK_LEN))
        if a < a_test:
            growth = int(g[pre.index(i)])
        elif b - a == BLOCK_LEN and b < N_DAYS:
            growth = 0 if a == a_test else -P.shrink_last_block
        else:
            growth = 0  # ostatni niepełny blok: przybycia dobierane po symulacji
        arrivals = k + growth if (b - a == BLOCK_LEN or a < a_test) else None
        rows.append(dict(block=i, a=a, b=b, n_active=n_act, churn=k, arrivals=arrivals))
        if arrivals is not None:
            n_act = n_act + arrivals - k
    sched = pd.DataFrame(rows)
    assert int(sched.loc[sched.a == a_test, "n_active"].iloc[0]) == SNAPSHOT_TEST_N
    assert int(sched.loc[sched.a == a_test, "churn"].iloc[0]) == 49
    return sched


def _nip(rng: np.random.Generator, n: int) -> list[str]:
    w = np.array([6, 5, 7, 2, 3, 4, 5, 6, 7])
    out, seen = [], set()
    while len(out) < n:
        d = rng.integers(0, 10, size=9)
        d[0] = rng.integers(1, 10)
        c = int((d * w).sum() % 11)
        if c == 10:
            continue
        s = "".join(map(str, d)) + str(c)
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _company_names(rng: np.random.Generator, n: int) -> list[str]:
    out, seen = [], set()
    while len(out) < n:
        p = rng.choice(N.COMPANY_PREFIX)
        c = rng.choice(N.COMPANY_CORE)
        legal = rng.choice(N.LEGAL, p=N.LEGAL_W)
        r = rng.random()
        if r < 0.45:
            name = f"{p} {c} {legal}"
        elif r < 0.7:
            name = f"{c} {legal}"
        elif r < 0.85:
            ln = rng.choice(N.LAST_M)
            name = f"{ln} i Wspólnicy {legal}" if rng.random() < 0.5 else f"{p} {ln} {legal}"
        else:
            name = f"{c} {rng.choice(['Consulting', 'Solutions', 'Group', 'Tech', 'Design', 'Partners'])} {legal}"
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def build_offices(P: Params, rng: np.random.Generator, sched: pd.DataFrame,
                  reserve_days: np.ndarray) -> pd.DataFrame:
    """Statyczne atrybuty biur. `reserve_days` — zapas biur startujących w ostatnich
    dniach okresu; ich liczba jest przycinana po symulacji (rejestr ERP = 1 400)."""
    n0 = P.n_initial_offices
    # biura istniejące przed 2024: start 2012-03 .. 2023-12, rosnąca gęstość
    span0, span1 = (dt.date(2012, 3, 1) - START).days, -1
    u = rng.random(n0) ** 0.62
    starts = sorted((span0 + u * (span1 - span0)).astype(int).tolist())
    for _, r in sched.iterrows():
        if r.arrivals is None or pd.isna(r.arrivals) or r.arrivals <= 0:
            continue
        starts += sorted(rng.integers(r.a, r.b, size=int(r.arrivals)).tolist())
    starts += sorted(int(d) for d in reserve_days)
    return _attributes(P, rng, np.array(starts), first_id=10001)


def _attributes(P: Params, rng: np.random.Generator, start_days: np.ndarray, first_id: int) -> pd.DataFrame:
    n = len(start_days)
    cities = list(N.CITIES)
    cw = np.array([N.CITIES[c][0] for c in cities])
    city = rng.choice(cities, size=n, p=cw / cw.sum())
    emp = np.clip(np.round(np.exp(rng.normal(np.log(55), 0.85, size=n))), 8, 1500).astype(int)
    plan_score = np.log(emp) + rng.normal(0, 0.35, size=n)
    plan = np.select([plan_score < np.log(28), plan_score < np.log(75), plan_score < np.log(190)],
                     ["S", "M", "L"], "XL")
    am = np.array([rng.choice(AM_OF_CITY.get(c, (6,))) for c in city])
    branza = rng.choice(N.BRANZE, size=n)
    post = np.array([f"{rng.choice(N.CITIES[c][1])}-{rng.integers(0, 1000):03d}" for c in city])
    street = rng.choice(N.STREETS, size=n)
    no = rng.integers(1, 180, size=n)
    price = np.array([PLAN_BASE_PRICE[p] for p in plan]) * np.exp(rng.normal(0, 0.12, size=n))
    price *= (1 + 0.004 * np.clip(emp - 50, -40, 400) / 10)

    # ukryte cechy
    br_eff = dict(zip(N.BRANZE, rng.normal(0, 0.22, size=len(N.BRANZE))))
    city_eff = {c: (0.0 if N.CITIES[c][0] > 0.03 else rng.normal(0, 0.25)) for c in cities}
    chronic = rng.normal(0, 1, size=n)  # chroniczne niezadowolenie
    frailty = (P.hazard_frailty_sd * rng.normal(0, 1, size=n)
               + np.array([br_eff[b] for b in branza]) + np.array([city_eff[c] for c in city])
               + np.select([plan == "S", plan == "XL"], [0.25, -0.2], 0.0)
               + P.frailty_chronic * chronic)
    groups = list(P.uplift_shares)
    gp = np.array([P.uplift_shares[g] for g in groups])
    uplift = rng.choice(groups, size=n, p=gp / gp.sum())
    # „pewni” zostają niezależnie od wizyty (niskie ryzyko), „straceni” odchodzą mimo wizyty
    frailty = frailty + np.select([uplift == "pewni", uplift == "straceni"], [-0.6, 0.6], 0.0)
    ep_mult = np.exp(rng.normal(0, 0.35, size=n) + 0.25 * chronic)
    dpe = np.exp(rng.normal(np.log(1.05), 0.25, size=n))  # napoje / pracownika / dzień
    pay_trait = rng.gamma(1.2, 2.2, size=n) * (rng.random(n) < 0.55)  # stałe opóźnienie (dni)
    sat_open = rng.random(n) < 0.12  # biura pracujące także w soboty

    names = _company_names(rng, n)
    nips = _nip(rng, n)
    df = pd.DataFrame({
        "idx": np.arange(n), "id_biura": np.arange(first_id, first_id + n),
        "nazwa": names, "nip": nips, "kod_pocztowy": post, "miasto": city,
        "adres": [f"ul. {s} {k}" for s, k in zip(street, no)], "branza": branza,
        "liczba_pracownikow": emp, "plan0": plan, "am_id": am, "start_day": start_days,
        "cena0": np.round(price, -1),
        "frailty": frailty, "chronic": chronic, "uplift": uplift, "ep_mult": ep_mult,
        "dpe": dpe, "pay_trait": pay_trait, "sat_open": sat_open,
    })
    df["data_startu"] = [to_date(d) for d in df.start_day]
    return df


def build_machines(P: Params, rng: np.random.Generator, offices: pd.DataFrame,
                   first_id: int = 1) -> pd.DataFrame:
    rows = []
    model_w = np.array([0.10, 0.16, 0.10, 0.08, 0.13, 0.08, 0.07, 0.05, 0.06, 0.04, 0.08, 0.05])
    # udział napojów na podwójnym espresso zależy od modelu (menu domyślne)
    model_double = np.clip(P.double_share_mean + np.linspace(-0.12, 0.12, len(MACHINE_MODELS))
                           [np.argsort(rng.random(len(MACHINE_MODELS)))], 0.3, 0.9)
    next_id = first_id
    for o in offices.itertuples():
        k = {"S": 1, "M": 1 + (rng.random() < 0.15), "L": 1 + (rng.random() < 0.6),
             "XL": 2 + (rng.random() < 0.4)}[o.plan0]
        for j in range(int(k)):
            m = int(rng.choice(len(MACHINE_MODELS), p=model_w))
            inst = o.start_day + (0 if j == 0 else int(rng.integers(0, 60)))
            if o.start_day < -5 * 365 and rng.random() < 0.7:  # wymiana starego ekspresu
                inst = int(rng.integers(-3 * 365, -30))
            rows.append(dict(id_ekspresu=f"EX-{next_id:05d}", office=o.idx, model_idx=m,
                             model=MACHINE_MODELS[m], install_day=inst,
                             share=float(rng.uniform(0.7, 1.3)),
                             double=float(np.clip(model_double[m] + rng.normal(0, 0.04), 0.2, 0.95)),
                             err_base=float(rng.gamma(2.0, 0.025))))
            next_id += 1
    mc = pd.DataFrame(rows)
    mc["share"] = mc.share / mc.groupby("office").share.transform("sum")
    return mc


def lokale(rng: np.random.Generator) -> pd.DataFrame:
    spec = [("Poznań", "Stary Rynek 41"), ("Poznań", "ul. Półwiejska 32 (Stary Browar)"),
            ("Poznań", "ul. Garbary 48"), ("Poznań", "ul. Głogowska 108"), ("Poznań", "ul. Dąbrowskiego 77"),
            ("Poznań", "ul. Królowej Jadwigi 51"), ("Warszawa", "ul. Mokotowska 45"),
            ("Warszawa", "ul. Prosta 70"), ("Warszawa", "ul. Grzybowska 62"),
            ("Warszawa", "ul. Puławska 145"), ("Wrocław", "Rynek 12"), ("Wrocław", "ul. Legnicka 48"),
            ("Kraków", "ul. Karmelicka 9"), ("Kraków", "ul. Zabłocie 23"), ("Gdańsk", "ul. Długa 22"),
            ("Gdańsk", "ul. Grunwaldzka 141"), ("Warszawa", "Al. Jerozolimskie 54 (Dworzec Centralny)"),
            ("Łódź", "ul. Piotrkowska 98"), ("Katowice", "ul. Mariacka 15"), ("Szczecin", "Al. Wojska Polskiego 20"),
            ("Bydgoszcz", "ul. Gdańska 30"), ("Wrocław", "ul. Powstańców Śląskich 95"),
            ("Katowice", "ul. Chorzowska 107"), ("Kraków", "ul. Pawia 5")]
    base = rng.uniform(70, 125, size=len(spec))
    open_day = np.full(len(spec), -2000)
    open_day[22] = day_index(dt.date(2025, 3, 7))
    open_day[23] = day_index(dt.date(2025, 10, 3))
    weekend = rng.uniform(0.85, 1.35, size=len(spec))
    weekend[[7, 8, 16, 22]] = [0.55, 0.6, 1.0, 0.7]  # lokale biurowe / dworcowe
    return pd.DataFrame({
        "lokal": np.arange(1, len(spec) + 1), "nazwa": [f"Kawosz {c} – {a.split(' (')[0]}" for c, a in spec],
        "miasto": [c for c, _ in spec], "adres": [a for _, a in spec],
        "data_otwarcia": [to_date(d) if d > -2000 else dt.date(2012 + i % 9, 1 + i % 12, 1) for i, d in enumerate(open_day)],
        "open_day": open_day, "base_traffic": base, "weekend": weekend,
        "growth": rng.uniform(0.0, 0.07, size=len(spec)),
    })
