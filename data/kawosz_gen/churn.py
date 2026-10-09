"""Krok 3 — ukryte ryzyko, spożycie kawy i mechanizm odejść.

Każde biuro ma ukryty proces ryzyka r(t), złożony z „epizodów kryzysowych”
(awarie, finanse, spadek zaangażowania, obsługa). Ryzyko jednocześnie:
  * obniża faktyczne spożycie kawy (spadek zaparzeń),
  * podnosi hazard odejścia (zwłaszcza w ostatnich 75 dniach umowy),
  * generuje sygnały w innych systemach (awarie, płatności, NPS) — `signals.py`.
Odejścia losowane są w blokach 90-dniowych: liczba odejść = round(3,5% × N),
a wybór biur odbywa się losowaniem bez zwracania z wagami = skumulowany
hazard w bloku (Gumbel top-k). Część odejść to odejścia „ciche” (hazard bazowy).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import Params, N_DAYS, BURN_IN
from .population import blocks
from .timeutil import DOW, MONTH, DOY, IS_HOLIDAY, add_years, to_date, day_index

CAUSES = ["awarie", "finanse", "zaangazowanie", "obsluga"]
CAUSE_P = [0.30, 0.25, 0.30, 0.15]


@dataclass
class Sim:
    risk: np.ndarray            # (n, BURN+N_DAYS) ukryte ryzyko (widoczne w sygnałach)
    hz_risk: np.ndarray         # (n, BURN+N_DAYS) ryzyko w hazardzie (opóźnione względem sygnałów)
    brew_log: np.ndarray        # (n, BURN+N_DAYS) log-wpływ ryzyka na spożycie
    episodes: pd.DataFrame
    dte: np.ndarray             # (n, N_DAYS) dni do końca bieżącego okresu umowy
    anniv: list                 # lista rocznic (indeksy dni) per biuro
    drinks: np.ndarray          # (n, N_DAYS) faktyczne napoje (przed modyfikacją po odejściu)
    counted_factor: np.ndarray  # (n, N_DAYS) mnożnik licznika (firmware)
    fw_day: np.ndarray          # dzień aktualizacji firmware per ekspres
    events_extra: pd.DataFrame  # fuzja / przeprowadzka / zawieszenie / downgrade
    suspended: np.ndarray       # (n, N_DAYS) bool
    churn: pd.DataFrame = None  # wynik selekcji
    visits: pd.DataFrame = None
    blocks_log: list = field(default_factory=list)


def _season(n_days: int) -> np.ndarray:
    s = np.ones(n_days)
    s[MONTH == 7] = 0.88
    s[MONTH == 8] = 0.80
    dec = (MONTH == 12) & (DOY >= 357 - 0)  # ~23-31 grudnia
    s[dec] = 0.45
    jan = (MONTH == 1) & (DOY <= 6)
    s[jan] = 0.7
    return s


def simulate_latent(P: Params, rng: np.random.Generator, off: pd.DataFrame,
                    machines: pd.DataFrame) -> Sim:
    n = len(off)
    D = BURN_IN + N_DAYS
    risk = np.zeros((n, D), dtype=np.float32)
    hz_risk = np.zeros((n, D), dtype=np.float32)
    brew_log = np.zeros((n, D), dtype=np.float32)

    # --- epizody ryzyka ---------------------------------------------------
    eps = []
    lam = P.episode_rate_year * off.ep_mult.to_numpy() * D / 365
    cnt = rng.poisson(lam)
    t = np.arange(D)
    for i in range(n):
        for _ in range(cnt[i]):
            s = int(rng.integers(0, D))
            S = float(rng.gamma(P.episode_severity_shape, P.episode_severity_scale))
            R = int(rng.integers(*P.episode_ramp))
            Pl = int(rng.integers(*P.episode_plateau))
            tau = float(rng.uniform(*P.episode_tau))
            cause = CAUSES[int(rng.choice(4, p=CAUSE_P))]
            lag = int(rng.integers(*P.hazard_lag))
            x = t - s
            shape = np.where(x < 0, 0.0, np.where(x < R, x / R, np.where(x < R + Pl, 1.0,
                             np.exp(-(x - R - Pl) / tau))))
            risk[i] += (S * shape).astype(np.float32)
            # decyzja o odejściu dojrzewa później niż widoczne sygnały
            hz_risk[i, lag:] += (S * shape[:D - lag]).astype(np.float32)
            # spożycie spada przez całą aktywną fazę epizodu (narastanie + plateau)
            # (stałe tempo spadku: cause_brew × S na 100 dni)
            bshape = np.where(x < 0, 0.0, np.where(x < R + Pl, x / 100.0,
                              (R + Pl) / 100.0 * np.exp(-(x - R - Pl) / tau)))
            brew_log[i] += (P.cause_brew[cause] * S * bshape).astype(np.float32)
            eps.append((i, s - BURN_IN, R, Pl, tau, S, cause))
    episodes = pd.DataFrame(eps, columns=["office", "start", "ramp", "plateau", "tau", "severity", "cause"])

    # --- rocznice umów i dni do końca okresu ------------------------------
    dte = np.zeros((n, N_DAYS), dtype=np.int16)
    anniv = []
    days = np.arange(N_DAYS)
    for o in off.itertuples():
        st = to_date(o.start_day)
        an = []
        k = 1
        while True:
            a = day_index(add_years(st, k))
            if a > N_DAYS + 400:
                break
            if a > -400:
                an.append(a)
            k += 1
        an = np.array(an)
        anniv.append(an)
        nxt = an[np.searchsorted(an, days, side="right")]
        dte[o.idx] = (nxt - days).astype(np.int16)

    # --- dodatkowe zdarzenia: fuzja, przeprowadzka, zawieszenie, downgrade -
    extra = []
    for o in off.itertuples():
        lo = max(o.start_day + 30, -BURN_IN)
        span = N_DAYS - lo
        if span <= 0:
            continue
        for typ, rate in (("fuzja", 0.03), ("przeprowadzka", 0.04), ("zawieszenie", 0.035)):
            for _ in range(rng.poisson(rate * span / 365)):
                extra.append((o.idx, typ, int(rng.integers(lo, N_DAYS)), 0))
        if rng.random() < 0.02 * span / 365 and o.plan0 != "S":  # dopasowanie planu
            extra.append((o.idx, "downgrade", int(rng.integers(lo, N_DAYS)), 0))
    for e in episodes.itertuples():
        st = off.start_day.iat[e.office]
        if e.start < st or e.start >= N_DAYS:
            continue
        p = 0.45 if e.cause == "finanse" else (0.18 if e.severity > 1.5 else 0.03)
        if rng.random() < p:
            d = e.start + int(rng.integers(10, max(11, e.ramp + 20)))
            if d < N_DAYS:
                extra.append((e.office, "downgrade", d, 1))
    events_extra = pd.DataFrame(extra, columns=["office", "typ", "day", "z_epizodu"])
    events_extra = events_extra.sort_values(["office", "day"]).reset_index(drop=True)

    suspended = np.zeros((n, N_DAYS), dtype=bool)
    for e in events_extra[events_extra.typ == "zawieszenie"].itertuples():
        a = max(e.day, 0)
        suspended[e.office, a:min(N_DAYS, e.day + int(rng.integers(25, 61)))] = True

    # --- faktyczne spożycie (napoje / dzień) -------------------------------
    season = _season(N_DAYS)
    wd = np.select([DOW == 0, DOW == 4, DOW == 5, DOW == 6], [0.96, 0.88, 0.04, 0.015], 1.0)
    base = off.liczba_pracownikow.to_numpy() * off.dpe.to_numpy()
    drift = np.cumsum(rng.normal(0, 0.10 / np.sqrt(365), size=(n, N_DAYS)), axis=1)
    noise = rng.normal(0, 0.13, size=(n, N_DAYS))
    wdm = np.tile(wd, (n, 1))
    sat = off.sat_open.to_numpy()
    wdm[sat[:, None] & (DOW == 5)[None, :]] = 0.35
    hol = np.where(IS_HOLIDAY, 0.04, 1.0)
    lam_d = (base[:, None] * wdm * season[None, :] * hol[None, :]
             * np.exp(drift + noise - brew_log[:, BURN_IN:]))
    drinks = rng.poisson(np.maximum(lam_d, 0)).astype(np.float32)
    drinks[suspended] = 0
    for i, sd in enumerate(off.start_day.to_numpy()):
        if sd > 0:
            drinks[i, :min(sd, N_DAYS)] = 0

    # --- firmware: od maja 2026 podwójne espresso liczone jako 1 ------------
    r0, r1 = (day_index(d) for d in P.firmware_rollout)
    fw_day = rng.integers(r0, r1 + 1, size=len(machines))
    fw_day = np.maximum(fw_day, machines.install_day.to_numpy())
    counted = np.zeros((n, N_DAYS), dtype=np.float32)
    for m, (o, sh, dbl, inst) in enumerate(machines[["office", "share", "double", "install_day"]].itertuples(index=False)):
        f = np.where(days < fw_day[m], 1.0 + dbl, 1.0) * sh
        f[days < inst] = 0.0
        counted[o] += f.astype(np.float32)

    return Sim(risk=risk, hz_risk=hz_risk, brew_log=brew_log, episodes=episodes, dte=dte, anniv=anniv,
               drinks=drinks, counted_factor=counted, fw_day=fw_day,
               events_extra=events_extra, suspended=suspended)


def am_trend(counted_brews: np.ndarray, a: int) -> np.ndarray:
    """Trend 30/90 dni na danych dostarczonych do dnia a (opóźnienie 2 dni)."""
    lo30, lo90, hi = a - 32, a - 92, a - 2
    m30 = counted_brews[:, max(lo30, 0):hi].sum(1) / 30
    m90 = counted_brews[:, max(lo90, 0):hi].sum(1) / 90
    return np.where(m90 > 0, m30 / np.maximum(m90, 1e-9), 1.0)


def select_churn(P: Params, rng: np.random.Generator, off: pd.DataFrame, sim: Sim,
                 sched: pd.DataFrame) -> None:
    n = len(off)
    start = off.start_day.to_numpy()
    frail = off.frailty.to_numpy()
    mult = off.uplift.map(P.uplift_mult).to_numpy()
    counted_brews = sim.drinks * sim.counted_factor

    # mnożnik hazardu po fuzji / przeprowadzce
    fx = np.ones((n, N_DAYS), dtype=np.float32)
    for e in sim.events_extra[sim.events_extra.typ.isin(["fuzja", "przeprowadzka"])].itertuples():
        a, b = max(e.day + 20, 0), min(e.day + 150, N_DAYS)
        if a < b:
            fx[e.office, a:b] *= P.fuzja_mult if e.typ == "fuzja" else P.przeprowadzka_mult

    churned = np.zeros(n, dtype=bool)
    ev_day = np.full(n, -1)
    ev_type = np.array([""] * n, dtype=object)
    end_excl = np.full(n, 10 ** 6)
    visits = []
    ccheck = sched.set_index("a")
    for (a, b) in blocks():
        elig = (start < a) & ~churned
        k = int(ccheck.loc[a, "churn"])
        if k == 0 or elig.sum() == 0:
            continue
        idx = np.where(elig)[0]
        cols = slice(a + BURN_IN, b + BURN_IN)
        r = sim.hz_risk[idx, cols]
        dte = sim.dte[idx, a:b]
        # okno decyzji o odnowieniu: ostatnie dni umowy, której rocznica wypada w tym bloku
        ann = np.arange(a, b)[None, :] + dte
        w_end = ((dte >= 1) & (dte <= P.contract_end_window) & (ann < b)).astype(np.float32)
        E = 1.0 + w_end * (P.contract_end_boost + P.contract_end_risk_boost * np.minimum(r, 2.0))
        E = E * np.where(dte > 365 - P.post_renewal_days, P.post_renewal_mult, 1.0)
        newbie = np.where((np.arange(a, b)[None, :] - start[idx, None]) < 180, 0.5, 1.0)
        h = np.exp(frail[idx, None] + P.hazard_beta * r) * E * fx[idx, a:b] * newbie

        # wizyty retencyjne na początku bloku (reguła AM + losowość)
        V = np.ones_like(h)
        vis_day = np.full(len(idx), -1)
        if a >= 92 and b - a == 90:
            tr = am_trend(counted_brews[idx], a)
            flagged = (sim.dte[idx, a] < 90) & (tr <= 0.7)
            pv = np.where(flagged, P.visit_prob_flagged, P.visit_prob_other)
            vis = rng.random(len(idx)) < pv
            vd = rng.integers(0, P.visit_window_days, size=len(idx))
            for j in np.where(vis)[0]:
                V[j, vd[j]:] = mult[idx[j]]
                vis_day[j] = a + vd[j]
        h_v = h * V
        W = h_v.sum(1)
        W0 = h.sum(1)
        g = np.log(W) + rng.gumbel(size=len(idx))
        sel = idx[np.argsort(-g)[:k]]
        sel_pos = {o: p for p, o in enumerate(idx)}
        for o in sel:
            p = sel_pos[o]
            an = sim.anniv[o]
            in_blk = an[(an >= a) & (an < b)]
            if len(in_blk) and rng.random() < P.type_b_prob:
                d, typ = int(in_blk[0]), "B"
                end = d
            else:
                pr = h_v[p] / h_v[p].sum()
                d, typ = a + int(rng.choice(b - a, p=pr)), "A"
                dd = to_date(d)
                y, m = dd.year, dd.month + 2
                if m > 12:
                    y, m = y + 1, m - 12
                end = day_index(dd.replace(year=y, month=m, day=1))
            churned[o], ev_day[o], ev_type[o], end_excl[o] = True, d, typ, end
        for j in np.where(vis_day >= 0)[0]:
            o = idx[j]
            dropped = churned[o] and ev_day[o] < vis_day[j] and a <= ev_day[o] < b
            visits.append(dict(office=o, block_a=a, day=int(vis_day[j]), dropped=bool(dropped),
                               group=off.uplift.iat[o], W_with=float(W[j]), W_without=float(W0[j]),
                               churned=bool(churned[o] and a <= ev_day[o] < b)))
        sim.blocks_log.append(dict(a=a, b=b, n_elig=int(len(idx)), k=k,
                                   churners=[int(x) for x in sel]))
    sim.churn = pd.DataFrame({"office": np.arange(n), "churned": churned, "event_day": ev_day,
                              "typ": ev_type, "end_excl": end_excl})
    sim.visits = pd.DataFrame(visits)


def finalize_drinks(sim: Sim) -> None:
    """Po wypowiedzeniu spożycie spada, po końcu umowy ekspres jest odbierany."""
    days = np.arange(N_DAYS)
    for c in sim.churn[sim.churn.churned].itertuples():
        if c.typ == "A":
            decay = np.where((days >= c.event_day) & (days < c.end_excl),
                             np.exp(-(days - c.event_day) / 40.0) * 0.5 + 0.35, 1.0)
            sim.drinks[c.office] = np.round(sim.drinks[c.office] * decay)
        sim.drinks[c.office, max(0, min(c.end_excl, N_DAYS)):] = 0
