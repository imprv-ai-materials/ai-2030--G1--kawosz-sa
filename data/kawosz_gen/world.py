"""Budowa „świata” B2B: biura, symulacja ryzyka i odejść, sygnały, ERP."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import population as pop
from .b2b import build_lines, build_kontrahenci, materialize_invoices
from .churn import Sim, simulate_latent, select_churn, finalize_drinks
from .config import Params, N_DAYS, EXPORT
from .products import build_erp_kartoteka, MODEL_PRICE_NET
from .signals import (contract_events, plan_price_at, build_helpdesk, build_telemetry,
                      build_nps, build_contacts)
from .timeutil import day_index


def rng_for(P: Params, *key: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([P.seed, *key]))


RESERVE = 90  # zapas biur startujących w ostatnich dniach (dobierany po symulacji)


@dataclass
class World:
    P: Params
    sched: pd.DataFrame
    off: pd.DataFrame
    machines: pd.DataFrame
    sim: Sim
    events: pd.DataFrame
    kart: pd.DataFrame
    refs: dict
    helpdesk: pd.DataFrame
    awaria_m: dict
    telemetry: pd.DataFrame | None
    nps: pd.DataFrame
    contacts: pd.DataFrame
    lines: pd.DataFrame
    kontr_reg: pd.DataFrame | None = None
    kontr_arch: pd.DataFrame | None = None
    kontr_info: dict | None = None
    erp: dict | None = None
    big_sale: dict | None = None


def _trim(sim: Sim, n: int, machines: pd.DataFrame) -> tuple[Sim, pd.DataFrame]:
    sim.risk = sim.risk[:n]
    sim.hz_risk = sim.hz_risk[:n]
    sim.brew_log = sim.brew_log[:n]
    sim.dte = sim.dte[:n]
    sim.anniv = sim.anniv[:n]
    sim.drinks = sim.drinks[:n]
    sim.counted_factor = sim.counted_factor[:n]
    sim.suspended = sim.suspended[:n]
    sim.episodes = sim.episodes[sim.episodes.office < n].reset_index(drop=True)
    sim.events_extra = sim.events_extra[sim.events_extra.office < n].reset_index(drop=True)
    sim.churn = sim.churn[sim.churn.office < n].reset_index(drop=True)
    keep = machines.office.to_numpy() < n
    sim.fw_day = sim.fw_day[keep]
    machines = machines[keep].reset_index(drop=True)
    return sim, machines


def build_world(P: Params, with_telemetry: bool = True) -> World:
    sched = pop.design_schedule(P)
    # zapas biur na ostatnie dni (nie biorą udziału w selekcji odejść)
    reserve_days = np.sort(rng_for(P, 2).integers(day_index(EXPORT) - 2, day_index(EXPORT) + 1, size=RESERVE))
    off = pop.build_offices(P, rng_for(P, 1), sched, reserve_days)
    machines = pop.build_machines(P, rng_for(P, 3), off)
    sim = simulate_latent(P, rng_for(P, 4), off, machines)
    select_churn(P, rng_for(P, 5), off, sim, sched)

    # ile biur dobrać na koniec, by rejestr ERP miał dokładnie 1 400 aktywnych umów
    exp_day = day_index(EXPORT)
    base_n = len(off) - RESERVE
    ch = sim.churn.iloc[:base_n]
    in_reg = (~(ch.churned & (ch.end_excl <= exp_day))).sum()
    need = 1400 - int(in_reg)
    assert 0 <= need <= RESERVE, f"potrzeba {need} biur na koniec okresu"
    n_keep = base_n + need
    off = off.iloc[:n_keep].reset_index(drop=True)
    sim, machines = _trim(sim, n_keep, machines)
    finalize_drinks(sim)

    events = contract_events(P, rng_for(P, 6), off, sim)
    kart, refs = build_erp_kartoteka(rng_for(P, 7))
    helpdesk, awaria_m = build_helpdesk(P, rng_for(P, 8), off, sim, machines)
    telemetry = build_telemetry(P, rng_for(P, 9), off, sim, machines, awaria_m) if with_telemetry else None
    nps = build_nps(P, rng_for(P, 10), off, sim)
    contacts = build_contacts(P, rng_for(P, 11), off, sim)
    plan_m, price_m = plan_price_at(events, len(off), np.arange(N_DAYS))
    lines = build_lines(P, rng_for(P, 12), off, sim, plan_m, price_m, kart, refs, awaria_m, machines)

    # duża, prawdziwa faktura: 40 ekspresów dla jednego klienta XL
    ch = sim.churn.set_index("office")
    cand = off[(off.plan0 == "XL") & (off.start_day < 0)
               & ~ch.reindex(off.idx).churned.to_numpy()].idx.to_numpy()
    bo = int(rng_for(P, 13).choice(cand))
    big_sale = dict(office=bo, day=day_index(dt.date(2025, 11, 20)),
                    indeks=refs["machines"][5], price=float(MODEL_PRICE_NET[5]),
                    inst_indeks=refs["services"]["INSTALACJA EKSPRESU"], inst_price=250.0)

    return World(P=P, sched=sched, off=off, machines=machines, sim=sim, events=events, kart=kart,
                 refs=refs, helpdesk=helpdesk, awaria_m=awaria_m, telemetry=telemetry, nps=nps,
                 contacts=contacts, lines=lines, big_sale=big_sale)


def september_rank(W: World) -> np.ndarray:
    """Losowa kolejność biur do wyboru duplikatów z identycznym NIP-em."""
    return rng_for(W.P, 14).permutation(len(W.off))


def build_erp(W: World, price_mult: float, n_fanout: int) -> None:
    W.P.n_fanout_pairs = n_fanout
    reg, arch, info = build_kontrahenci(W.P, rng_for(W.P, 15), W.off, W.sim, september_rank(W))
    W.kontr_reg, W.kontr_arch, W.kontr_info = reg, arch, info
    W.erp = materialize_invoices(W.P, W.P.seed * 31 + 16, W.lines, info["kid"], info["dups"],
                                 price_mult, W.P.seed * 31 + 17, W.sim, W.off, W.big_sale)
