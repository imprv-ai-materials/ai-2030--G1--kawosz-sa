"""Trzy liczby przychodu + definicja i most (krok 4).

Każdy raport to ten sam zestaw źródeł z innymi ustawieniami:

  ustawienie         BI     sprzedaż  księgowość  definicja
  vat (netto)        nie    8% flat   tak         tak
  zwroty/korekty     nie    nie       nie         tak
  fan-out NIP        tak    tak       tak         nie
  subskr. rozłożone  nie    nie       nie         tak
  dedup plików POS   nie    nie       tak         tak
  karty przy realiz. nie    nie       nie         tak
  bez testowych      nie    nie       nie         tak
  EUR po kursie NBP  nie    nie       tak         tak
  doba Warszawa      nie    nie       tak         tak

Most liczony jest sekwencyjnie (kolejność w BRIDGE_ORDER), więc pozycje
sumują się dokładnie do różnicy BI − definicja.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

# Pozycje mostu (kolejność prezentacji jak w specyfikacji) ...
BRIDGE_STEPS = ["vat", "zwroty", "fanout", "subskrypcje", "pos_duplikaty", "karty", "testowe", "eur", "utc"]
# ... liczone sekwencyjnie w kolejności: najpierw poprawki, które stosuje też księgowość
# (VAT, duplikaty POS, kurs EUR, doba Warszawa), potem pozostałe. Dzięki temu
# księgowość = BI − VAT − duplikaty + EUR + UTC dokładnie, a definicja = księgowość − reszta.
BRIDGE_ORDER = ["vat", "pos_duplikaty", "eur", "utc", "zwroty", "fanout", "subskrypcje", "karty", "testowe"]
TEST_RE = re.compile(r"test", re.IGNORECASE)


def is_test_order(o: pd.DataFrame) -> pd.Series:
    note = o.notatka.fillna("").astype(str)
    email = o.email.fillna("").astype(str)
    return note.str.contains(TEST_RE) | email.str.endswith("@kawosz.pl")


def _month_mask(ts: pd.Series, y: int, m: int) -> pd.Series:
    return (ts.dt.year == y) & (ts.dt.month == m)


def _warsaw(ts: pd.Series) -> pd.Series:
    return ts.dt.tz_localize("UTC").dt.tz_convert("Europe/Warsaw").dt.tz_localize(None)


class Revenue:
    """Przygotowuje źródła raz, a potem liczy przychód dla dowolnych ustawień."""

    def __init__(self, T: dict, year: int = 2026, month: int = 9):
        self.y, self.m = year, month
        f = T["erp_faktury"].copy()
        f["data"] = pd.to_datetime(f.data)
        kr = T["erp_kontrahenci"]
        ka = T.get("erp_kontrahenci_archiwum")
        allk = pd.concat([kr, ka]) if ka is not None else kr
        nip_of = allk.set_index("id_kontrahenta").nip.astype(str)
        cnt = kr.nip.astype(str).value_counts()
        f["fan"] = f.id_kontrahenta.map(nip_of).map(cnt).fillna(1).clip(lower=1)
        self.fak = f[_month_mask(f.data, year, month)]
        p = T["pos_paragony"].copy()
        p["data_czas"] = pd.to_datetime(p.data_czas)
        p = p[_month_mask(p.data_czas, year, month)]
        poz = T["pos_pozycje"]
        poz = poz[poz.set_index(["lokal", "nr_paragonu"]).index.isin(p.set_index(["lokal", "nr_paragonu"]).index)]
        net = (poz.ilosc * poz.cena_brutto / (1 + poz.vat / 100)).groupby([poz.lokal, poz.nr_paragonu]).sum()
        p["netto"] = net.reindex(list(zip(p.lokal, p.nr_paragonu))).to_numpy()
        p["dup"] = p.duplicated(["lokal", "nr_paragonu"], keep="first")
        self.pos = p
        o = T["ecom_zamowienia"].copy()
        o["utc"] = pd.to_datetime(o.data_utc)
        o["waw"] = _warsaw(o.utc)
        o["test_"] = is_test_order(o)
        o["zwrot_"] = o.zwrot.astype(str).str.lower().isin(["true", "1", "tak"])  # bool lub tekst
        rates = T["kursy_nbp"].copy()
        rates["data"] = pd.to_datetime(rates.data)
        rates = rates.sort_values("data")
        self.rates = rates
        o = o[(o.utc >= pd.Timestamp(year, month, 1) - pd.Timedelta(days=2)) &
              (o.utc < pd.Timestamp(year, month, 1) + pd.DateOffset(months=1) + pd.Timedelta(days=2))].copy()
        d = o.waw.dt.normalize()
        idx = np.searchsorted(rates.data.to_numpy(), d.to_numpy(), side="right") - 1
        o["kurs"] = rates.eur_pln.to_numpy()[np.clip(idx, 0, None)]
        self.ord = o
        s = T["ecom_subskrypcje"].copy()
        s["utc"] = pd.to_datetime(s.data_platnosci)
        s["waw"] = _warsaw(s.utc)
        self.subs = s
        g = T["karty_podarunkowe"].copy()
        g["sp"] = pd.to_datetime(g.data_sprzedazy)
        g["re"] = pd.to_datetime(g.data_realizacji)
        self.gift = g

    def compute(self, vat="none", zwroty=False, fanout=True, subskrypcje=False, pos_duplikaty=False,
                karty=False, testowe=False, eur=False, utc=False) -> dict:
        y, m = self.y, self.m
        # ERP
        f = self.fak
        fv = f[f.typ == "faktura"]
        erp = (fv.kwota_netto * (fv.fan if fanout else 1)).sum()
        if zwroty:
            erp += f[f.typ == "korekta"].kwota_netto.sum()
        # POS
        p = self.pos if not pos_duplikaty else self.pos[~self.pos.dup]
        pos = p.netto.sum() if vat == "true" else p.kwota_brutto.sum()
        # e-commerce
        tcol = "waw" if utc else "utc"
        o = self.ord[_month_mask(self.ord[tcol], y, m)]
        if zwroty:
            o = o[~o.zwrot_]
        if testowe:
            o = o[~o.test_]
        amt = o.brutto * np.where((o.waluta == "EUR") & eur, o.kurs, 1.0)
        s = self.subs
        sm = s[(s.plan != "roczny") & _month_mask(s[tcol], y, m)].kwota.sum()
        if subskrypcje:
            ya = s[s.plan == "roczny"]
            per = ya[tcol].dt.year * 12 + ya[tcol].dt.month
            cur = y * 12 + m
            sy = (ya.kwota[(per <= cur) & (per > cur - 12)] / 12).sum()
        else:
            sy = s[(s.plan == "roczny") & _month_mask(s[tcol], y, m)].kwota.sum()
        g = self.gift
        gk = g[_month_mask(g.re, y, m)].kwota.sum() if karty else g[_month_mask(g.sp, y, m)].kwota.sum()
        ecom_gross = amt.sum() + sm + sy + gk
        if vat == "true":
            ecom, pos_v = ecom_gross / 1.23, pos
        elif vat == "flat8":
            ecom, pos_v = ecom_gross / 1.08, pos / 1.08
        else:
            ecom, pos_v = ecom_gross, pos
        parts = {"erp": erp, "pos": pos_v, "ecom_zamowienia": amt.sum() / (1.23 if vat == "true" else 1.08 if vat == "flat8" else 1),
                 "subskrypcje": (sm + sy) / (1.23 if vat == "true" else 1.08 if vat == "flat8" else 1),
                 "karty": gk / (1.23 if vat == "true" else 1.08 if vat == "flat8" else 1)}
        parts["total"] = erp + pos_v + ecom
        parts["_pos_gross"] = p.kwota_brutto.sum()
        parts["_pos_net"] = p.netto.sum()
        parts["_ecom_gross"] = ecom_gross
        return parts

    # --------------------------------------------------------------
    def reports(self) -> dict:
        bi = self.compute()
        sales = self.compute(vat="flat8")
        acc = self.compute(vat="true", pos_duplikaty=True, eur=True, utc=True)
        dfn = self.compute(vat="true", zwroty=True, fanout=False, subskrypcje=True, pos_duplikaty=True,
                           karty=True, testowe=True, eur=True, utc=True)
        # most sekwencyjny
        state = dict(vat="none", zwroty=False, fanout=True, subskrypcje=False, pos_duplikaty=False,
                     karty=False, testowe=False, eur=False, utc=False)
        prev = bi["total"]
        bridge = {}
        for step in BRIDGE_ORDER:
            if step == "vat":
                state["vat"] = "true"
            elif step == "fanout":
                state["fanout"] = False
            else:
                state[step] = True
            cur = self.compute(**state)["total"]
            bridge[step] = cur - prev  # wpływ na drodze BI -> definicja
            prev = cur
        assert abs(prev - dfn["total"]) < 1e-6
        bridge = {k: bridge[k] for k in BRIDGE_STEPS}
        return {"bi": bi["total"], "sprzedaz": sales["total"], "ksiegowosc": acc["total"],
                "definicja": dfn["total"], "bridge": bridge,
                "parts": {"bi": bi, "sprzedaz": sales, "ksiegowosc": acc, "definicja": dfn}}
