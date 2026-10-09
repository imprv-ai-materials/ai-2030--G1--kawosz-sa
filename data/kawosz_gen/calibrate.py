"""Deterministyczna kalibracja parametrów rozkładów pod most przychodu (krok 4).

Kalibrowane są wyłącznie parametry rozkładów (poziomy cen, natężenia ruchu,
prawdopodobieństwa, liczebności), a nie sumy. Każdy parametr steruje głównie
jedną pozycją mostu:

  b2b_price_mult         -> dashboard BI = 8,31
  pos_traffic_mult,
  ecom_price_mult        -> VAT = 0,40 oraz raport sprzedaży = 8,06
  lokal17_mult           -> duplikaty plików POS = 0,03
  de_share               -> EUR zapisane jako PLN = 0,03
  sub_billing_window_min -> granica doby UTC = 0,01
  return_prob            -> zwroty i korekty = 0,09
  n_fanout_pairs         -> fan-out = 0,06
  sept_campaign_annual   -> subskrypcje roczne = 0,05
  gift_breakage          -> karty podarunkowe = 0,02
  test_amount_mult       -> definicja = 7,69 (zamówienia testowe ≈ 0,01)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Params, TARGETS
from .ecom import EcomGen, build_subscriptions, build_gift_cards, build_nbp
from .pos import PosGen
from .revenue import Revenue
from .timeutil import day_index
from .world import World, build_erp
from . import export_b2b as ex

SEPT = range(day_index(pd.Timestamp("2026-09-01").date()), day_index(pd.Timestamp("2026-09-30").date()) + 1)
SIGN = {"vat": -1, "zwroty": -1, "fanout": -1, "subskrypcje": -1, "pos_duplikaty": -1, "karty": -1,
        "testowe": -1, "eur": +1, "utc": +1}


def pos_month(P: Params, lok: pd.DataFrame, cat: pd.DataFrame, days=SEPT) -> tuple[pd.DataFrame, pd.DataFrame]:
    g = PosGen(P, lok, cat)
    dup_days = {day_index(d) for d in P.pos_dup_days}
    pars, pozs = [], []
    for l in lok.lokal:
        for d, (par, poz) in g.days_for(int(l), days):
            pars.append(par)
            pozs.append(poz)
            if int(l) == 17 and d in dup_days:
                pars.append(par)  # plik wysłany ponownie
    return pd.concat(pars, ignore_index=True), pd.concat(pozs, ignore_index=True)


def revenue_tables(P: Params, W: World, lok, pos_cat, ecom_prod, full_ecom: bool = False) -> dict:
    build_erp(W, P.b2b_price_mult, P.n_fanout_pairs)
    T = ex.erp_tables(W)
    par, poz = pos_month(P, lok, pos_cat)
    T["pos_paragony"], T["pos_pozycje"] = par, poz
    eg = EcomGen(P, ecom_prod)
    o, _ = eg.build(None if full_ecom else range(SEPT[0] - 2, SEPT[-1] + 1))
    T["ecom_zamowienia"] = o.assign(data_utc=o.data_utc)
    T["ecom_subskrypcje"] = build_subscriptions(P)
    T["karty_podarunkowe"] = build_gift_cards(P)
    T["kursy_nbp"] = build_nbp(P)
    return T


def evaluate(P: Params, W: World, lok, pos_cat, ecom_prod) -> dict:
    return Revenue(revenue_tables(P, W, lok, pos_cat, ecom_prod)).reports()


def calibrate(P: Params, W: World, lok, pos_cat, ecom_prod, max_iter: int = 30, tol: float = 1500.0,
              log=print) -> dict:
    tg = {k: v * 1e6 for k, v in TARGETS.items()}
    prev_subs = None
    fan_hist: dict[int, float] = {}
    fan_frozen = False
    for it in range(max_iter):
        r = evaluate(P, W, lok, pos_cat, ecom_prod)
        br = {k: (-v if SIGN[k] < 0 else v) for k, v in r["bridge"].items()}  # wielkość pozycji
        err = {
            "bi": r["bi"] - tg["bi"], "sprzedaz": r["sprzedaz"] - tg["sprzedaz"],
            "ksiegowosc": r["ksiegowosc"] - tg["ksiegowosc"], "definicja": r["definicja"] - tg["definicja"],
            **{k: br[k] - tg[k] for k in br},
        }
        log(f"[kalibracja {it:2d}] " + " ".join(f"{k}={v / 1e3:+.1f}k" for k, v in err.items()))
        main_ok = all(abs(err[k]) < tol for k in ("bi", "sprzedaz", "ksiegowosc", "definicja", "vat", "zwroty",
                                                  "subskrypcje", "pos_duplikaty", "karty", "eur"))
        if main_ok and abs(err["fanout"]) < 4000 and abs(err["testowe"]) < 4000 and abs(err["utc"]) < 4000:
            return {"iterations": it, "reports": r, "errors": err, "converged": True}
        bi, dfn, acc = r["parts"]["bi"], r["parts"]["definicja"], r["parts"]["ksiegowosc"]
        # 1) VAT i raport sprzedaży: dwa równania na POS brutto (P) i e-com brutto (G)
        Pg, Gg = bi["_pos_gross"], bi["_ecom_gross"]
        a_p = (Pg - bi["_pos_net"]) / Pg
        a_e = 0.23 / 1.23
        S = (tg["bi"] - tg["sprzedaz"]) * 1.08 / 0.08  # wymagane P + G
        Gs = (tg["vat"] - a_p * S) / (a_e - a_p)
        Ps = S - Gs
        orders = bi["ecom_zamowienia"]
        P.pos_traffic_mult *= float(np.clip(Ps / Pg, 0.7, 1.4))
        P.ecom_price_mult *= float(np.clip((orders + Gs - Gg) / orders, 0.6, 1.6))
        # 2) pozostałe pozycje
        P.lokal17_mult *= float(np.clip(tg["pos_duplikaty"] / max(br["pos_duplikaty"], 1.0), 0.7, 1.4))
        P.de_share = float(np.clip(P.de_share * tg["eur"] / max(br["eur"], 1.0), 0.002, 0.15))
        P.sub_billing_window_min = float(np.clip(P.sub_billing_window_min * br["utc"] / tg["utc"], 20, 1500))
        kor = acc["erp"] - br["fanout"] - dfn["erp"]  # wartość korekt (dodatnia)
        ret_e = br["zwroty"] - kor
        P.return_prob = float(np.clip(P.return_prob * (tg["zwroty"] - kor) / max(ret_e, 1.0), 0.01, 0.25))
        fan_hist[P.n_fanout_pairs] = abs(err["fanout"])
        if not fan_frozen:
            x = P.n_fanout_pairs * tg["fanout"] / max(br["fanout"], 1.0)
            cands = [c for c in (round(x), int(np.floor(x)), int(np.ceil(x))) if 1 <= c <= 80 and c not in fan_hist]
            if cands:
                nf = cands[0]
            else:  # sąsiednie liczby sprawdzone — wybór najlepszej
                nf, fan_frozen = min(fan_hist, key=fan_hist.get), True
            P.n_fanout_pairs = int(nf)
        if prev_subs is None or prev_subs[0] == P.sept_campaign_annual:
            slope = 420.0
        else:
            slope = (br["subskrypcje"] - prev_subs[1]) / (P.sept_campaign_annual - prev_subs[0])
        prev_subs = (P.sept_campaign_annual, br["subskrypcje"])
        P.sept_campaign_annual = int(np.clip(round(
            P.sept_campaign_annual + (tg["subskrypcje"] - br["subskrypcje"]) / max(slope, 100.0)), 0, 3000))
        sold_net, real_net = bi["karty"] / 1.23, dfn["karty"]
        P.gift_breakage = float(np.clip(1 - (1 - P.gift_breakage) * (sold_net - tg["karty"]) / max(real_net, 1.0),
                                        0.0, 0.6))
        # zamówienia testowe domykają definicję: 8,31 − Σ pozostałych pozycji − 7,69
        others = sum(br[k] * (1 if SIGN[k] < 0 else -1) for k in br if k != "testowe")
        tt = tg["bi"] - tg["definicja"] - others
        damp = 1.0 if it < 4 else 0.6  # tłumienie sprzężenia BI <-> zamówienia testowe
        P.test_amount_mult *= float(np.clip(tt / max(br["testowe"], 1.0), 0.5, 2.0)) ** damp
        # 3) poziom cen B2B domyka dashboard BI
        P.b2b_price_mult *= float((tg["bi"] - (bi["total"] - bi["erp"])) / bi["erp"]) ** damp
    return {"iterations": max_iter, "reports": r, "errors": err, "converged": False}
