"""POS — paragony kawiarni (24 lokale) i ich pozycje.

Każdy dzień każdego lokalu ma własny strumień losowy, a każdy paragon zużywa
stały wiersz macierzy liczb losowych — przy zmianie natężenia ruchu pierwsze
paragony dnia pozostają identyczne (stabilna kalibracja).

Usterki wynikające z działania systemu POS:
  * kwoty brutto (VAT w cenie), plik dzienny per lokal, cp1250 i przecinek dziesiętny,
  * od 2026-06-01 dostawca dodał kolumnę `kanal` w środku pliku,
  * lokal 17: trzy pliki z września 2026 wysłane ponownie (duplikaty),
  * lokal 9: 0,5% paragonów bez metody płatności (MCAR),
  * ~200 pozycji z ujemną ilością bez flagi storno (zwroty przy kasie),
  * paragon na 48 000 zł (literówka: miało być 48,00).
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from .config import Params, N_DAYS
from .timeutil import DAYS, DOW, MONTH, day_index, easter_sundays

NPOS_P = np.array([0.53, 0.43, 0.03, 0.007, 0.003])
FIRST_P = np.array([0.89, 0.093, 0.017])
NEXT_P = np.array([0.36, 0.625, 0.015])
QTY_P = np.array([0.952, 0.022, 0.008, 0.005, 0.004, 0.004, 0.003, 0.002])
PAY = np.array(["karta", "BLIK", "gotówka", "aplikacja"])
PAY_P = np.array([0.58, 0.17, 0.15, 0.10])
KANAL = np.array(["sala", "wynos", "aplikacja"])
KANAL_P = np.array([0.55, 0.38, 0.07])
NEW_COLUMN_FROM = day_index(dt.date(2026, 6, 1))
K_U = 1 + 5 * 3 + 6  # liczby losowe na paragon
HOUR_W = np.array([0, 0, 0, 0, 0, 0, 0, 6, 10, 9, 7, 7, 9, 9, 7, 7, 7, 6, 4, 2, 0, 0, 0, 0], float)
TYPO_DAY = day_index(dt.date(2025, 3, 14))
TYPO_LOKAL = 5

CLOSED = {day_index(d) for d in [dt.date(2024, 12, 25), dt.date(2025, 12, 25), dt.date(2025, 1, 1),
                                 dt.date(2026, 1, 1), dt.date(2024, 1, 1)] + sorted(easter_sundays())
          if 0 <= day_index(d) < N_DAYS}


class PosGen:
    def __init__(self, P: Params, lok: pd.DataFrame, cat: pd.DataFrame):
        self.P = P
        self.lok = lok
        cat = cat[cat.kod_produktu != "P0999"]
        self.groups = []
        for g in ("napoje", "jedzenie", "detal"):
            G = cat[cat.kategoria == g]
            self.groups.append((G.kod_produktu.to_numpy(), G.cena_brutto.to_numpy(), G.vat.to_numpy(),
                                np.cumsum(G.waga.to_numpy() / G.waga.sum())))
        self.hour_cdf = np.cumsum(HOUR_W / HOUR_W.sum())

    def _rng(self, lokal: int, day: int, salt: int = 0) -> np.random.Generator:
        return np.random.default_rng(np.random.SeedSequence([self.P.seed, 777, lokal, day, salt]))

    def counts(self, lokal: int) -> np.ndarray:
        """Liczba paragonów per dzień dla lokalu (deterministyczna)."""
        P = self.P
        r = self.lok.set_index("lokal").loc[lokal]
        noise = np.random.default_rng(np.random.SeedSequence([P.seed, 778, lokal])).normal(0, 0.09, N_DAYS)
        season = np.select([MONTH == 12, np.isin(MONTH, [7, 8]), MONTH == 1], [1.12, 0.96, 0.9], 1.0)
        wk = np.where(DOW >= 5, r.weekend, 1.0)
        years = np.arange(N_DAYS) / 365.0
        lam = (r.base_traffic * P.pos_traffic_mult * (P.lokal17_mult if lokal == 17 else 1.0)
               * wk * season * (1 + r.growth) ** years * np.exp(noise))
        n = np.round(lam).astype(int)
        n[np.arange(N_DAYS) < r.open_day] = 0
        for d in CLOSED:
            n[d] = 0
        return n

    def day(self, lokal: int, day: int, nr_offset: int, n: int) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Paragony i pozycje jednego dnia lokalu."""
        rng = self._rng(lokal, day)
        U = rng.random((n, K_U))
        npos = np.searchsorted(np.cumsum(NPOS_P), U[:, 0]) + 1
        npos = np.minimum(npos, 5)
        rows_r, cols = np.repeat(np.arange(n), npos), np.concatenate([np.arange(k) for k in npos]) if n else np.array([], int)
        pos_u = U[:, 1:16].reshape(n, 5, 3)
        uc = pos_u[rows_r, cols, 0]
        up = pos_u[rows_r, cols, 1]
        uq = pos_u[rows_r, cols, 2]
        g = np.where(cols == 0, np.searchsorted(np.cumsum(FIRST_P), uc), np.searchsorted(np.cumsum(NEXT_P), uc))
        g = np.minimum(g, 2)
        kod = np.empty(len(g), dtype=object)
        price = np.zeros(len(g))
        vat = np.zeros(len(g), dtype=int)
        for gi, (codes, prices, vats, cdf) in enumerate(self.groups):
            m = g == gi
            k = np.minimum(np.searchsorted(cdf, up[m]), len(codes) - 1)
            kod[m], price[m], vat[m] = codes[k], prices[k], vats[k]
        qty = np.searchsorted(np.cumsum(QTY_P), uq) + 1
        # czas: godzina wg profilu, minuta i sekunda losowe
        hour = np.searchsorted(self.hour_cdf, U[:, 16])
        if DOW[day] >= 5:
            hour = np.maximum(hour, 8)
        sec = (U[:, 17] * 3600).astype(int)
        base = DAYS[day]
        t = base + pd.to_timedelta(hour * 3600 + sec, unit="s")
        # numeracja chronologiczna w ciągu dnia
        nr = nr_offset + np.argsort(np.argsort(t.values, kind="stable"), kind="stable") + 1
        pay = PAY[np.minimum(np.searchsorted(np.cumsum(PAY_P), U[:, 18]), 3)].astype(object)
        if lokal == 9:
            pay[U[:, 19] < 0.005] = ""  # MCAR: utrata metody płatności
        kanal = KANAL[np.minimum(np.searchsorted(np.cumsum(KANAL_P), U[:, 20]), 2)]
        poz = pd.DataFrame({"lokal": lokal, "nr_paragonu": nr[rows_r], "kod_produktu": kod,
                            "ilosc": qty.astype(float), "cena_brutto": price, "vat": vat})
        # zwrot towaru przy kasie: ujemna ilość bez flagi storno (~200 w całym okresie)
        ret = np.where(U[:, 21] < 9.5e-5)[0]
        if len(ret):
            codes, prices, vats, _ = self.groups[2]
            j = (U[ret, 21] * 1e9).astype(int) % len(codes)
            poz = pd.concat([poz, pd.DataFrame({"lokal": lokal, "nr_paragonu": nr[ret], "kod_produktu": codes[j],
                                                "ilosc": -1.0, "cena_brutto": prices[j], "vat": vats[j]})])
        par = pd.DataFrame({"lokal": lokal, "nr_paragonu": nr, "data_czas": t, "kanal": kanal,
                            "metoda_platnosci": pay, "storno": 0})
        # storno: anulowanie paragonu kolejnym dokumentem z ujemną kwotą (~0,2%)
        st = np.where(U[:, 19] > 0.998)[0]
        if len(st):
            nr_st = nr_offset + n + np.arange(1, len(st) + 1)
            orig = par.iloc[st]
            par = pd.concat([par, orig.assign(nr_paragonu=nr_st, storno=1,
                                              data_czas=orig.data_czas + pd.Timedelta(minutes=3))])
            src = poz[poz.nr_paragonu.isin(nr[st])]
            mp = dict(zip(nr[st], nr_st))
            poz = pd.concat([poz, src.assign(nr_paragonu=src.nr_paragonu.map(mp), ilosc=-src.ilosc)])
        if lokal == TYPO_LOKAL and day == TYPO_DAY:
            tn = nr_offset + n + len(st) + 1
            par = pd.concat([par, pd.DataFrame({"lokal": [lokal], "nr_paragonu": [tn],
                                                "data_czas": [base + pd.Timedelta(hours=11, minutes=42, seconds=7)],
                                                "kanal": ["sala"], "metoda_platnosci": ["karta"], "storno": [0]})])
            poz = pd.concat([poz, pd.DataFrame({"lokal": [lokal], "nr_paragonu": [tn], "kod_produktu": ["P0999"],
                                                "ilosc": [1.0], "cena_brutto": [48000.0], "vat": [23]})])
        poz["wartosc"] = (poz.ilosc * poz.cena_brutto).round(2)
        poz["netto"] = poz.wartosc / (1 + poz.vat / 100)
        agg = poz.groupby("nr_paragonu").agg(kwota_brutto=("wartosc", "sum"), netto=("netto", "sum"))
        par = par.merge(agg, left_on="nr_paragonu", right_index=True, how="left")
        par = par.sort_values("data_czas", kind="stable").reset_index(drop=True)
        return par, poz.drop(columns=["wartosc", "netto"])

    def days_for(self, lokal: int, days):
        """Numer paragonu = RRMMDD × 10000 + numer kolejny w dniu (unikalny w lokalu)."""
        n = self.counts(lokal)
        for d in days:
            if n[d] > 0:
                t = DAYS[d]
                off = ((t.year % 100) * 10000 + t.month * 100 + t.day) * 10000
                yield d, self.day(lokal, d, off, int(n[d]))
