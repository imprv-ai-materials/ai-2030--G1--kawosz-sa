"""Krok 2/3 — zdarzenia CRM, helpdesk, telemetria IoT, NPS, kontakty AM.

Sygnały powstają z ukrytego ryzyka r(t) z `churn.py`, więc wyprzedzają
wypowiedzenia. Pułapki przecieku (krok 5) wynikają z działania systemów:
odbiór ekspresu po wypowiedzeniu, rabat retencyjny po wypowiedzeniu,
eksport CRM ze stanem na dzień eksportu.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from .churn import Sim
from .config import Params, N_DAYS, BURN_IN, EXPORT
from .population import PLAN_BASE_PRICE
from .timeutil import DAYS, IS_WORKDAY, to_date, day_index

DOWN = {"XL": "L", "L": "M", "M": "S", "S": "S"}
INDEX_RATE = {2024: 0.035, 2025: 0.04, 2026: 0.03}
FW_OLD = ["4.6.2", "4.6.2", "4.7.1", "4.7.1", "3.9.8", "3.9.8", "2.21", "2.21", "8.4.0", "8.4.0", "1.12.7", "6.3"]
FW_MID = ["4.6.5", "4.6.5", "4.7.3", "4.7.3", "3.9.9", "3.9.9", "2.22", "2.22", "8.4.2", "8.4.2", "1.12.9", "6.4"]
FW_NEW = ["5.0.1", "5.0.1", "5.0.1", "5.0.1", "5.0.3", "5.0.3", "3.0", "3.0", "9.0.0", "9.0.0", "2.0.1", "7.0"]
FW_MID_DAY = day_index(dt.date(2025, 2, 17))


def _ts(day: np.ndarray, minutes: np.ndarray) -> pd.Series:
    base = pd.Timestamp("2024-01-01")
    return base + pd.to_timedelta(day, unit="D") + pd.to_timedelta(np.round(minutes).astype(int), unit="m")


# ---------------------------------------------------------------------------
# historia umów
# ---------------------------------------------------------------------------
def contract_events(P: Params, rng: np.random.Generator, off: pd.DataFrame, sim: Sim) -> pd.DataFrame:
    """Pełna oś czasu planu i ceny (cena przed mnożnikiem poziomu cen B2B)."""
    rows = []
    ch = sim.churn.set_index("office")
    ex = sim.events_extra
    for o in off.itertuples():
        c = ch.loc[o.idx]
        end = c.end_excl if c.churned else 10 ** 6
        an = sim.anniv[o.idx]
        renewals_before = int((an < 0).sum()) if o.start_day < 0 else 0
        renew_days = [a for a in an if 0 <= a < min(end, N_DAYS)]
        if c.churned and c.typ == "B":
            renew_days = [a for a in renew_days if a < c.event_day]
        price = o.cena0 / (1.035 ** renewals_before)
        plan = o.plan0
        rows.append((o.idx, o.start_day, "start", plan, price))
        price = o.cena0
        evs = [(a, "odnowienie") for a in renew_days]
        evs += [(e.day, e.typ) for e in ex[ex.office == o.idx].itertuples() if 0 <= e.day < min(end, N_DAYS)]
        if c.churned and c.typ == "A":
            evs.append((c.event_day, "wypowiedzenie"))
        for d, typ in sorted(evs):
            if typ == "odnowienie":
                price = price * (1 + INDEX_RATE[to_date(d).year])
            elif typ == "downgrade":
                if plan == "S":
                    continue
                newp = DOWN[plan]
                price = price * PLAN_BASE_PRICE[newp] / PLAN_BASE_PRICE[plan]
                plan = newp
            rows.append((o.idx, d, typ, plan, price))
    ev = pd.DataFrame(rows, columns=["office", "day", "typ", "plan", "cena_base"])
    ev["cena_base"] = ev.cena_base.round(-1)
    return ev


def plan_price_at(ev: pd.DataFrame, n_off: int, days: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Plan i cena (bazowa) obowiązujące w zadanych dniach — macierze (n_off, len(days))."""
    plan = np.empty((n_off, len(days)), dtype=object)
    price = np.zeros((n_off, len(days)))
    for o, g in ev[ev.typ.isin(["start", "odnowienie", "downgrade"])].groupby("office"):
        g = g.sort_values("day")
        pos = np.searchsorted(g.day.to_numpy(), days, side="right") - 1
        pos = np.clip(pos, 0, None)
        plan[o] = g.plan.to_numpy()[pos]
        price[o] = g.cena_base.to_numpy()[pos]
    return plan, price


# ---------------------------------------------------------------------------
# helpdesk
# ---------------------------------------------------------------------------
def build_helpdesk(P: Params, rng: np.random.Generator, off: pd.DataFrame, sim: Sim,
                   machines: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    ch = sim.churn.set_index("office")
    rows = []
    awaria_days: dict[int, list[int]] = {}
    end_of = {o: (ch.loc[o].end_excl if ch.loc[o].churned else N_DAYS) for o in off.idx}
    for m in machines.itertuples():
        a = max(m.install_day, 0)
        b = min(end_of[m.office], N_DAYS)
        if a >= b:
            continue
        span = b - a
        ad = list(rng.integers(a, b, size=rng.poisson(0.55 * span / 365 * (1 + 10 * m.err_base))))
        # przeglądy okresowe co ~90 dni
        d = a + int(rng.integers(0, 90))
        while d < b:
            if IS_WORKDAY[d]:
                rows.append((m.office, d, "serwis", m.Index))
            d += int(rng.integers(80, 100))
        awaria_days[m.Index] = ad
    # epizody „awarie”: seria 3–5 awarii w ~50 dni
    mach_of = machines.groupby("office").groups
    for e in sim.episodes[sim.episodes.cause == "awarie"].itertuples():
        if e.office not in mach_of or e.start < max(0, off.start_day.iat[e.office]):
            continue
        b = min(end_of[e.office], N_DAYS)
        ms = list(mach_of[e.office])
        for _ in range(int(rng.integers(*P.awarie_cluster))):
            d = e.start + int(rng.integers(0, 50))
            if 0 <= d < b:
                awaria_days.setdefault(ms[int(rng.integers(len(ms)))], []).append(d)
    for mi, ds in awaria_days.items():
        for d in ds:
            rows.append((int(machines.loc[mi, "office"]), d, "awaria", mi))
    # „inne”
    for o in off.itertuples():
        a, b = max(o.start_day, 0), min(end_of[o.idx], N_DAYS)
        if a < b:
            for d in rng.integers(a, b, size=rng.poisson(0.65 * (b - a) / 365)):
                rows.append((o.idx, int(d), "inne", -1))
    # odbiór ekspresu: 1–20 dni po wypowiedzeniu / końcu umowy (pułapka przecieku)
    for c in sim.churn[sim.churn.churned].itertuples():
        if rng.random() < 0.96:
            d = c.event_day + int(rng.integers(1, 21))
            if d < N_DAYS:
                rows.append((c.office, d, "odbiór ekspresu", -1))
    hd = pd.DataFrame(rows, columns=["office", "day", "kategoria", "machine"])
    n = len(hd)
    minutes = np.where(hd.kategoria == "serwis", rng.uniform(7 * 60, 15 * 60, n),
                       rng.uniform(7.5 * 60, 18 * 60, n))
    hd["utworzono"] = _ts(hd.day.to_numpy(), minutes)
    res_days = np.select(
        [hd.kategoria == "awaria", hd.kategoria == "serwis", hd.kategoria == "inne"],
        [rng.gamma(1.6, 1.3, n), rng.uniform(0, 1.5, n), rng.gamma(1.5, 3.0, n)],
        0.0)
    pick = hd.kategoria == "odbiór ekspresu"
    endx = hd.office.map(lambda o: end_of[o]).to_numpy()
    res_days = np.where(pick, np.maximum(endx - hd.day.to_numpy(), 1) + rng.uniform(0, 3, n), res_days)
    hd["rozwiazano"] = hd.utworzono + pd.to_timedelta(res_days * 24 * 60 + rng.uniform(10, 240, n), unit="m")
    hd.loc[hd.rozwiazano > pd.Timestamp(EXPORT) + pd.Timedelta(hours=16), "rozwiazano"] = pd.NaT
    hd = hd.sort_values(["utworzono"]).reset_index(drop=True)
    hd["id"] = [f"HD-{i:06d}" for i in range(100001, 100001 + len(hd))]
    awaria_m = {}
    for r in hd[hd.kategoria == "awaria"].itertuples():
        awaria_m.setdefault(r.machine, []).append(r.day)
    return hd, awaria_m


# ---------------------------------------------------------------------------
# telemetria
# ---------------------------------------------------------------------------
def build_telemetry(P: Params, rng: np.random.Generator, off: pd.DataFrame, sim: Sim,
                    machines: pd.DataFrame, awaria_m: dict) -> pd.DataFrame:
    ch = sim.churn.set_index("office")
    parts = []
    days = np.arange(N_DAYS)
    for m in machines.itertuples():
        c = ch.loc[m.office]
        a = max(m.install_day, 0)
        b = min(c.end_excl if c.churned else N_DAYS, N_DAYS)
        if a >= b:
            continue
        dd = days[a:b]
        drinks = rng.binomial(sim.drinks[m.office, a:b].astype(np.int64), min(m.share, 1.0))
        doubles = rng.binomial(drinks, m.double)
        old = dd < sim.fw_day[m.Index]
        counted = drinks + np.where(old, doubles, 0)
        lam_e = np.full(len(dd), m.err_base)
        for d in awaria_m.get(m.Index, []):
            lo, hi = max(d - 6, a), min(d + 1, b)
            if lo < hi:
                lam_e[lo - a:hi - a] += rng.uniform(1.5, 5.0)
        bledy = rng.poisson(lam_e)
        fw = np.where(old, np.where(dd < FW_MID_DAY, FW_OLD[m.model_idx], FW_MID[m.model_idx]),
                      FW_NEW[m.model_idx])
        parts.append(pd.DataFrame({"id_ekspresu": m.id_ekspresu, "day": dd, "zaparzenia": counted,
                                   "bledy": bledy, "firmware": fw}))
    tel = pd.concat(parts, ignore_index=True)
    tel["data"] = DAYS[tel.day.to_numpy()].date
    tel["data_dostarczenia"] = (DAYS[tel.day.to_numpy()] + pd.Timedelta(days=2)).date
    return tel


# ---------------------------------------------------------------------------
# NPS (MNAR: niezadowoleni nie odpowiadają)
# ---------------------------------------------------------------------------
def nps_send_days() -> list[int]:
    out = []
    for y in (2024, 2025, 2026):
        for mth in (2, 5, 8, 11):
            if y == 2026 and mth > 8:
                continue
            d = dt.date(y, mth, 8)
            while d.weekday() != 1:  # wtorek
                d += dt.timedelta(days=1)
            out.append(day_index(d))
    return out


def build_nps(P: Params, rng: np.random.Generator, off: pd.DataFrame, sim: Sim) -> pd.DataFrame:
    ch = sim.churn.set_index("office")
    rows = []
    chronic = off.chronic.to_numpy()
    for sd in nps_send_days():
        for o in off.itertuples():
            c = ch.loc[o.idx]
            if o.start_day >= sd - 30 or (c.churned and c.event_day <= sd):
                continue
            r = float(sim.risk[o.idx, sd + BURN_IN])
            unhappy = P.nps_risk * r + P.nps_chronic * chronic[o.idx]
            p_resp = 1 / (1 + np.exp(-(0.55 - 1.1 * unhappy)))
            if rng.random() < p_resp:
                score = int(np.clip(np.round(9.0 - 1.3 * r - 0.8 * chronic[o.idx] + rng.normal(0, 1.2)), 0, 10))
                resp = sd + int(min(rng.geometric(0.35), 21))
                rows.append((o.idx, sd, resp, score))
            else:
                rows.append((o.idx, sd, -1, -1))
    nps = pd.DataFrame(rows, columns=["office", "send_day", "resp_day", "wynik"])
    nps.loc[nps.resp_day >= N_DAYS, ["resp_day", "wynik"]] = -1
    return nps


# ---------------------------------------------------------------------------
# kontakty opiekunów (AM)
# ---------------------------------------------------------------------------
def build_contacts(P: Params, rng: np.random.Generator, off: pd.DataFrame, sim: Sim) -> pd.DataFrame:
    ch = sim.churn.set_index("office")
    rows = []
    rate = {"S": 2.3, "M": 3.4, "L": 4.8, "XL": 6.5}
    for o in off.itertuples():
        c = ch.loc[o.idx]
        a = max(o.start_day, 0)
        b = min(c.event_day if c.churned else N_DAYS, N_DAYS)
        if a >= b:
            continue
        k = rng.poisson(rate[o.plan0] * (b - a) / 365)
        for d in rng.integers(a, b, size=k):
            d = int(d)
            while not IS_WORKDAY[d] and d + 1 < N_DAYS:
                d += 1
            rows.append((o.idx, d, "wizyta" if rng.random() < 0.38 else "telefon", 0, False))
    # wizyty retencyjne (przed wypowiedzeniem) — efekt opisany w kluczu
    for v in sim.visits[~sim.visits.dropped].itertuples():
        d = v.day
        while d < N_DAYS - 1 and not IS_WORKDAY[d]:
            d += 1
        if d < N_DAYS:
            rows.append((v.office, d, "wizyta", 0, True))
    # rabat retencyjny dopiero PO wypowiedzeniu (pułapka przecieku)
    for c in sim.churn[sim.churn.churned].itertuples():
        if rng.random() < 0.72:
            d = c.event_day + int(rng.integers(1, 26))
            if d < N_DAYS:
                rows.append((c.office, d, "telefon" if rng.random() < 0.6 else "wizyta",
                             int(rng.choice([5, 10, 15, 20], p=[0.3, 0.35, 0.2, 0.15])), True))
    ct = pd.DataFrame(rows, columns=["office", "day", "typ", "rabat_retencyjny_pct", "czy_retencyjna"])
    return ct.sort_values(["day", "office"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# stan CRM na dzień eksportu
# ---------------------------------------------------------------------------
def crm_state(off: pd.DataFrame, sim: Sim, ev: pd.DataFrame, b2b_mult: float) -> pd.DataFrame:
    ch = sim.churn.set_index("office")
    exp_day = day_index(EXPORT)
    last = ev[ev.typ.isin(["start", "odnowienie", "downgrade"])].sort_values("day").groupby("office").last()
    rows = []
    for o in off.itertuples():
        c = ch.loc[o.idx]
        plan, price = last.loc[o.idx, "plan"], last.loc[o.idx, "cena_base"]
        if c.churned and c.end_excl <= exp_day:
            status, end = "zakończony", c.end_excl - 1
        elif c.churned:
            status, end = "w wypowiedzeniu", c.end_excl - 1
        else:
            end = int(sim.dte[o.idx, exp_day]) + exp_day - 1
            status = "zawieszony" if sim.suspended[o.idx, exp_day] else "aktywny"
        rows.append((o.id_biura, o.nazwa, o.nip, o.kod_pocztowy, o.miasto, o.branza,
                     o.liczba_pracownikow, plan, o.am_id, o.data_startu, to_date(end),
                     round(price * b2b_mult, 2), status))
    return pd.DataFrame(rows, columns=["id_biura", "nazwa", "nip", "kod_pocztowy", "miasto", "branza",
                                       "liczba_pracownikow", "plan", "am_id", "data_startu",
                                       "data_konca_umowy", "cena_mies", "status"])
