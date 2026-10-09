"""E-commerce: zamówienia (UTC), pozycje, subskrypcje „Kawosz co miesiąc”, karty podarunkowe, kursy NBP.

Usterki wynikające z działania systemu:
  * czas zapisywany w UTC (granica doby przesunięta względem Europe/Warsaw),
  * kwoty brutto; zamówienia do DE zapisane w EUR w tej samej kolumnie `brutto`,
  * zamówienia testowe rozpoznawalne tylko po notatce / adresie e-mail,
  * zwroty oznaczone flagą, kwota zamówienia pozostaje w tabeli,
  * subskrypcja roczna płatna z góry (jedna płatność na 12 miesięcy),
  * brak e-maila prawie zawsze przy płatności gotówką przy odbiorze (MAR).
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from . import names as N
from .config import Params, N_DAYS, START
from .timeutil import DAYS, DOW, MONTH, IS_HOLIDAY, day_index, warsaw_to_utc

HOUR_W = np.array([2.2, 1.0, 0.5, 0.3, 0.3, 0.5, 1.5, 3.5, 5, 6, 6.5, 7, 7.5, 7, 6.5, 6, 6, 6.5,
                   7.5, 8.5, 9, 8.5, 6, 4], float)
PAY = np.array(["karta", "BLIK", "przelew", "pobranie"])
PAY_P = np.array([0.33, 0.42, 0.15, 0.10])
NOTES = ["Proszę o zmielenie pod ekspres kolbowy", "Proszę zmielić do dripa", "Dzwonić przed dostawą",
         "Paczkomat przy Biedronce", "Prezent – proszę bez paragonu w paczce", "Zostawić u sąsiada (nr 4)",
         "Domofon nie działa, proszę dzwonić", "Faktura na firmę – NIP w danych", "Proszę o szybką wysyłkę",
         "Bez folii bąbelkowej, dziękuję :)"]
TEST_NOTES = ["TEST – nie wysyłać", "zamówienie testowe QA", "test bramki płatności, anulować",
              "prosze nie realizowac (test)", "[TEST] sprawdzenie integracji z kurierem",
              "test nowego checkoutu – Marek", "Testowe – zwrot środków automatyczny"]
TEST_EMAILS = ["test@kawosz.pl", "qa@kawosz.pl", "sklep.test@kawosz.pl", "jan.testowy@kawosz.pl"]
K_U = 1 + 4 * 2 + 2 + 1 + 2 + 2 + 1 + 1 + 1
SHIP_PLN, SHIP_EUR, FREE_FROM = 14.99, 6.90, 149.0
QA_DAYS = [dt.date(2026, 9, 8), dt.date(2026, 9, 9), dt.date(2026, 9, 10), dt.date(2026, 9, 22)]
QA_PER_DAY = 14


def _email(first: str, last: str, k: int, domain: str) -> str:
    f = first.lower().translate(N.TRANSLIT)
    l_ = last.lower().translate(N.TRANSLIT)
    return [f"{f}.{l_}@{domain}", f"{f}{l_}{k % 100}@{domain}", f"{f[0]}{l_}@{domain}",
            f"{l_}.{f}{k % 1000}@{domain}"][k % 4]


class EcomGen:
    def __init__(self, P: Params, prod: pd.DataFrame):
        self.P = P
        self.prod = prod
        self.cdf = np.cumsum(prod.waga.to_numpy() / prod.waga.sum())
        rng = np.random.default_rng(np.random.SeedSequence([P.seed, 900]))
        n_pl, n_de = 80000, 3000
        fem = rng.random(n_pl) < 0.55
        fn = np.where(fem, rng.choice(N.FIRST_F, n_pl), rng.choice(N.FIRST_M, n_pl))
        ln = rng.choice(N.LAST_M, n_pl)
        ln = np.array([N.female_last(x) if f else x for x, f in zip(ln, fem)])
        dom = rng.choice(N.EMAIL_DOMAINS_PL, n_pl, p=[0.42, 0.14, 0.1, 0.08, 0.08, 0.05, 0.06, 0.03, 0.02, 0.02])
        self.pl_emails = np.array([_email(a, b, k, d) for k, (a, b, d) in enumerate(zip(fn, ln, dom))])
        self.de_emails = np.array([_email(a, b, k, d) for k, (a, b, d) in enumerate(zip(
            rng.choice(N.DE_FIRST, n_de), rng.choice(N.DE_LAST, n_de), rng.choice(N.EMAIL_DOMAINS_DE, n_de)))])
        self.hour_cdf = np.cumsum(HOUR_W / HOUR_W.sum())

    def counts(self) -> np.ndarray:
        rng = np.random.default_rng(np.random.SeedSequence([self.P.seed, 901]))
        years = np.arange(N_DAYS) / 365.0
        season = np.select([MONTH == 12, MONTH == 11, MONTH == 1, np.isin(MONTH, [7, 8])], [1.45, 1.25, 0.85, 0.85], 1.0)
        bf = np.zeros(N_DAYS)
        for y in (2024, 2025):
            d = dt.date(y, 11, 30)
            while d.weekday() != 4:
                d -= dt.timedelta(days=1)
            i = day_index(d)
            bf[i:i + 4] = 1.2
        dow = np.select([DOW == 6, DOW == 0, DOW == 5], [1.15, 1.1, 0.85], 1.0)
        lam = 185 * 1.11 ** years * season * dow * (1 + bf) * np.exp(rng.normal(0, 0.08, N_DAYS))
        lam[IS_HOLIDAY] *= 0.7
        return np.round(lam).astype(int)

    def day(self, d: int, n: int, first_id: int) -> tuple[pd.DataFrame, pd.DataFrame]:
        o, p = self._day(d, n, first_id, salt=0)
        if DAYS[d].day == 1 and self.P.midnight_drop_orders > 0:
            # premiera „kawy miesiąca” o północy czasu warszawskiego pierwszego dnia miesiąca
            k = self.P.midnight_drop_orders
            o2, p2 = self._day(d, k, first_id + n, salt=1)
            r = np.random.default_rng(np.random.SeedSequence([self.P.seed, 904, d])).random(k)
            o2["data_lokalna"] = DAYS[d] + pd.to_timedelta(np.round(r ** 1.6 * 95 * 60), unit="s")
            o, p = pd.concat([o, o2], ignore_index=True), pd.concat([p, p2], ignore_index=True)
        return o, p

    def _day(self, d: int, n: int, first_id: int, salt: int) -> tuple[pd.DataFrame, pd.DataFrame]:
        P = self.P
        rng = np.random.default_rng(np.random.SeedSequence([P.seed, 902, d, salt]))
        U = rng.random((n, K_U))
        nitem = np.searchsorted([0.68, 0.90, 0.97, 1.0], U[:, 0]) + 1
        is_de = U[:, 14] < P.de_share
        is_test = U[:, 15] < 0.0025
        rows = np.repeat(np.arange(n), nitem)
        cols = np.concatenate([np.arange(k) for k in nitem]) if n else np.array([], int)
        uu = U[:, 1:9].reshape(n, 4, 2)
        k = np.minimum(np.searchsorted(self.cdf, uu[rows, cols, 0]), len(self.prod) - 1)
        qty = np.searchsorted([0.93, 0.99, 1.0], uu[rows, cols, 1]) + 1
        pln = self.prod.cena_brutto_pln.to_numpy()[k]
        # cennik DE w EUR wyprowadzony z cennika PLN (kurs 4,30, narzut 8%)
        price = np.round(pln * P.ecom_price_mult, 2)
        price = np.where(is_de[rows], np.round(price / 4.3 * 1.08 * P.eur_price_mult, 1) - 0.01, price)
        price = np.where(is_test[rows], np.round(price * P.test_amount_mult, 2), price)
        ids = first_id + np.arange(n)
        poz = pd.DataFrame({"id_zamowienia": ids[rows], "sku": self.prod.sku.to_numpy()[k],
                            "ilosc": qty, "cena_brutto": price})
        val = poz.assign(v=poz.ilosc * poz.cena_brutto).groupby("id_zamowienia").v.sum().reindex(ids).to_numpy()
        ship = np.where(is_de, SHIP_EUR, np.where(val >= FREE_FROM, 0.0, SHIP_PLN))
        sp = ship > 0
        poz = pd.concat([poz, pd.DataFrame({"id_zamowienia": ids[sp], "sku": "DOSTAWA", "ilosc": 1,
                                            "cena_brutto": ship[sp]})], ignore_index=True)
        brutto = np.round(val + ship, 2)
        hour = np.searchsorted(self.hour_cdf, U[:, 9])
        sec = (U[:, 10] * 3600).astype(int)
        local = DAYS[d] + pd.to_timedelta(hour * 3600 + sec, unit="s")
        pay = PAY[np.minimum(np.searchsorted(np.cumsum(PAY_P), U[:, 11]), 3)]
        pay = np.where(is_de, np.where(U[:, 11] < 0.6, "karta", "przelew"), pay)
        cust = (len(self.pl_emails) * U[:, 12] ** 1.7).astype(int)
        email = np.where(is_de, self.de_emails[(len(self.de_emails) * U[:, 12]).astype(int)], self.pl_emails[cust])
        missing = np.where(pay == "pobranie", U[:, 13] < 0.93, U[:, 13] < 0.012)  # MAR
        email = np.where(missing, "", email).astype(object)
        note = np.where(U[:, 16] < 0.07, np.array(NOTES)[(U[:, 16] * 1e6).astype(int) % len(NOTES)], "").astype(object)
        zwrot = (U[:, 17] < P.return_prob) & ~is_test
        if is_test.any():
            ti = np.where(is_test)[0]
            for j, i in enumerate(ti):
                r = (U[i, 16] * 1e6).astype(int)
                if r % 3 != 2:
                    note[i] = TEST_NOTES[r % len(TEST_NOTES)]
                if r % 3 != 0:
                    email[i] = TEST_EMAILS[r % len(TEST_EMAILS)]
        o = pd.DataFrame({"id": ids, "data_lokalna": local, "waluta": np.where(is_de, "EUR", "PLN"),
                          "brutto": brutto, "email": email, "notatka": note, "zwrot": zwrot,
                          "metoda_platnosci": pay, "test": is_test})
        return o, poz

    def qa_batch(self, first_id: int) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Seria zamówień testowych QA (migracja bramki płatności, wrzesień 2026)."""
        P = self.P
        rng = np.random.default_rng(np.random.SeedSequence([P.seed, 903]))
        parts_o, parts_p = [], []
        fid = first_id
        for d in QA_DAYS:
            n = QA_PER_DAY
            k = np.minimum(np.searchsorted(self.cdf, rng.random((n, 3))), len(self.prod) - 1)
            price = np.round(self.prod.cena_brutto_pln.to_numpy()[k] * P.ecom_price_mult * P.test_amount_mult, 2)
            ids = fid + np.arange(n)
            poz = pd.DataFrame({"id_zamowienia": np.repeat(ids, 3), "sku": self.prod.sku.to_numpy()[k].ravel(),
                                "ilosc": 1, "cena_brutto": price.ravel()})
            local = pd.Timestamp(d) + pd.to_timedelta(rng.uniform(9.5, 16.5, n) * 3600, unit="s").round("s")
            r = rng.integers(0, 1000, n)
            parts_o.append(pd.DataFrame({
                "id": ids, "data_lokalna": local, "waluta": "PLN", "brutto": price.sum(1).round(2),
                "email": np.where(r % 4 == 0, [f"qa+{x}@kawosz.pl" for x in r], np.array(self.pl_emails)[r * 37 % 80000]),
                "notatka": np.where(r % 4 == 0, "", np.array(TEST_NOTES)[r % len(TEST_NOTES)]),
                "zwrot": False, "metoda_platnosci": np.where(r % 2 == 0, "BLIK", "karta"), "test": True}))
            parts_p.append(poz)
            fid += n
        return pd.concat(parts_o, ignore_index=True), pd.concat(parts_p, ignore_index=True)

    def build(self, days: range | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
        counts = self.counts()
        extra = np.where(DAYS.day.to_numpy() == 1, self.P.midnight_drop_orders, 0)
        ids0 = 1000001 + np.concatenate([[0], np.cumsum(counts + extra)[:-1]])
        os_, ps_ = [], []
        for d in (days if days is not None else range(N_DAYS)):
            o, p = self.day(d, int(counts[d]), int(ids0[d]))
            os_.append(o)
            ps_.append(p)
        qo, qp = self.qa_batch(1000001 + int((counts + extra).sum()))
        if days is None or day_index(QA_DAYS[0]) in days:
            os_.append(qo)
            ps_.append(qp)
        o = pd.concat(os_, ignore_index=True)
        o["data_utc"] = warsaw_to_utc(o.data_lokalna).to_numpy()
        o = o.sort_values(["data_utc", "id"], kind="stable").reset_index(drop=True)
        # numeracja zamówień chronologiczna
        new_id = pd.Series(1000001 + np.arange(len(o)), index=o.id.to_numpy())
        p = pd.concat(ps_, ignore_index=True)
        p["id_zamowienia"] = new_id.loc[p.id_zamowienia.to_numpy()].to_numpy()
        o["id"] = new_id.to_numpy()
        return o, p.sort_values(["id_zamowienia"], kind="stable").reset_index(drop=True)


# ---------------------------------------------------------------------------
# subskrypcje
# ---------------------------------------------------------------------------
PRICE_M, PRICE_Y = 39.0, 399.0


def build_subscriptions(P: Params) -> pd.DataFrame:
    """Płatności subskrypcji. Każdy subskrybent ma własny wektor liczb losowych
    (rezygnacja / odnowienie / godzina batcha), więc zmiana wielkości kampanii
    nie zmienia losów pozostałych subskrybentów."""
    rng = np.random.default_rng(np.random.SeedSequence([P.seed, 910]))
    subs = []  # (start_day, plan, u)
    for _ in range(5400):
        subs.append((-int(rng.integers(1, 900)), "miesięczny", rng.random(96)))
    for _ in range(1150):
        subs.append((-int(rng.integers(1, 365)), "roczny", rng.random(96)))
    years = np.arange(N_DAYS) / 365.0
    lam_m = 9.6 * 1.10 ** years * np.select([MONTH == 12, MONTH == 1], [1.4, 1.2], 1.0)
    lam_y = 1.3 * 1.10 ** years * np.select([MONTH == 12], [2.5], 1.0)
    for d in range(N_DAYS):
        for _ in range(int(rng.poisson(lam_m[d]))):
            subs.append((d, "miesięczny", rng.random(96)))
        for _ in range(int(rng.poisson(lam_y[d]))):
            subs.append((d, "roczny", rng.random(96)))
    # kampania wrześniowa („Wrzesień z Kawoszem”) — dodatkowe plany roczne
    crng = np.random.default_rng(np.random.SeedSequence([P.seed, 911]))
    for y, f in ((2024, 0.8), (2025, 0.9), (2026, 1.0)):
        a = day_index(dt.date(y, 9, 1))
        days = a + crng.integers(1, 30, 3000)  # kampania startuje 2 września
        us = crng.random((3000, 96))
        k = int(round(P.sept_campaign_annual * f))
        subs += [(int(days[i]), "roczny", us[i]) for i in range(k)]
    subs.sort(key=lambda s: (s[0], s[1], s[2][0]))
    rows = []
    t0 = pd.Timestamp(START)
    for sid, (st, plan, u) in enumerate(subs, start=1):
        sd = t0 + pd.Timedelta(days=st)
        if plan == "miesięczny":
            # 3,2% rezygnacji miesięcznie; płatność w dniu „miesięcznicy”
            life = int(np.argmax(u[:48] < 0.032)) if (u[:48] < 0.032).any() else 48
            k0 = max(0, (-st) // 31 - 1)
            for k in range(k0, life + 1):
                di = ((sd + pd.DateOffset(months=k)) - t0).days
                if di >= N_DAYS:
                    break
                if di >= 0:
                    rows.append((sid, plan, di, PRICE_M, u[48 + k % 48]))
        else:
            ren = int(np.argmax(u[:6] > 0.72)) if (u[:6] > 0.72).any() else 6  # 72% odnawia
            for k in range(ren + 1):
                di = ((sd + pd.DateOffset(years=k)) - t0).days
                if di >= N_DAYS:
                    break
                if di >= 0:
                    rows.append((sid, plan, di, PRICE_Y, u[48 + k]))
    df = pd.DataFrame(rows, columns=["sid", "plan", "day", "kwota", "u"])
    # nocny batch płatności: 00:05 + U × okno (czasu warszawskiego), zapis w UTC
    minutes = 5 + df.u.to_numpy() * P.sub_billing_window_min
    local = DAYS[df.day.to_numpy()] + pd.to_timedelta(np.round(minutes * 60), unit="s")
    df["data_lokalna"] = local
    df["data_platnosci"] = warsaw_to_utc(pd.Series(local)).to_numpy()
    df["id"] = [f"SUB-{s:06d}" for s in df.sid]
    return df.drop(columns="u").sort_values(["data_platnosci", "id"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# karty podarunkowe
# ---------------------------------------------------------------------------
GIFT_AMOUNTS = np.array([50, 100, 150, 200, 300])
GIFT_P = np.array([0.18, 0.38, 0.18, 0.18, 0.08])


def build_gift_cards(P: Params) -> pd.DataFrame:
    rng = np.random.default_rng(np.random.SeedSequence([P.seed, 920]))
    lam = np.full(N_DAYS, 15.0) * 1.08 ** (np.arange(N_DAYS) / 365)
    dec = (MONTH == 12) & (DAYS.day.to_numpy() <= 23)
    lam[dec] *= 3.8
    for m, dd in ((2, 14), (5, 26), (6, 23)):
        sel = (MONTH == m) & (np.abs(DAYS.day.to_numpy() - dd) <= 4)
        lam[sel] *= 2.0
    n = rng.poisson(lam)
    day = np.repeat(np.arange(N_DAYS), n)
    U = rng.random((len(day), 4))
    amount = GIFT_AMOUNTS[np.minimum(np.searchsorted(np.cumsum(GIFT_P), U[:, 0]), 4)]
    lag = np.maximum(1, np.ceil(np.exp(np.log(38) + 0.9 * _norm_ppf(U[:, 1])))).astype(int)
    real = day + lag
    unrealized = (U[:, 2] < P.gift_breakage) | (real >= N_DAYS)
    codes = _codes(rng, len(day))
    df = pd.DataFrame({"kod": codes, "day": day, "real_day": np.where(unrealized, -1, real), "kwota": amount})
    df["data_sprzedazy"] = DAYS[df.day.to_numpy()].date
    df["data_realizacji"] = [DAYS[r].date() if r >= 0 else None for r in df.real_day]
    return df


def _norm_ppf(u: np.ndarray) -> np.ndarray:
    from scipy.stats import norm
    return norm.ppf(np.clip(u, 1e-9, 1 - 1e-9))


def _codes(rng: np.random.Generator, n: int) -> list[str]:
    alphabet = np.array(list("ABCDEFGHJKLMNPQRSTUVWXYZ23456789"))
    out, seen = [], set()
    while len(out) < n:
        c = "".join(alphabet[rng.integers(0, len(alphabet), 8)])
        if c not in seen:
            seen.add(c)
            out.append(f"KP-{c[:4]}-{c[4:]}")
    return out


# ---------------------------------------------------------------------------
# kursy NBP
# ---------------------------------------------------------------------------
def build_nbp(P: Params) -> pd.DataFrame:
    rng = np.random.default_rng(np.random.SeedSequence([P.seed, 930]))
    days = [d for d in range(-1, N_DAYS) if 0 <= d and DOW[d] < 5 and not IS_HOLIDAY[d]]
    x, out = 4.3480, []
    for d in days:
        target = 4.31 if d < 400 else (4.26 if d < 700 else 4.24)
        x = x + 0.04 * (target - x) + rng.normal(0, 0.0105)
        out.append((DAYS[d].date(), round(x, 4)))
    return pd.DataFrame(out, columns=["data", "eur_pln"])
