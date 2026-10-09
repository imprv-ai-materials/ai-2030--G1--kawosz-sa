"""Parametry generatora.

Wszystkie wyniki kontrolne (przychód, AUC, PSI) wynikają z parametrów rozkładów
zebranych tutaj. Parametry oznaczone jako `kalibrowane` są dostrajane
automatycznie w `calibrate.py` (deterministycznie, przy stałym ziarnie).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
import datetime as dt

START = dt.date(2024, 1, 1)
END = dt.date(2026, 9, 30)
EXPORT = dt.date(2026, 9, 30)
N_DAYS = (END - START).days + 1  # 1004
BURN_IN = 365  # dni historii ukrytego ryzyka przed START

SNAPSHOT_TEST = dt.date(2026, 4, 1)
SNAPSHOT_TEST_N = 1400
BLOCK_LEN = 90  # bloki selekcji odejść zakotwiczone na migawce testowej

TARGET_MONTH = (2026, 9)

# Docelowe wartości mostu przychodu (mln PLN) — warunki kontrolne
TARGETS = {
    "bi": 8.31,
    "sprzedaz": 8.06,
    "ksiegowosc": 7.92,
    "definicja": 7.69,
    "vat": 0.40,
    "zwroty": 0.09,
    "fanout": 0.06,
    "subskrypcje": 0.05,
    "pos_duplikaty": 0.03,
    "karty": 0.02,
    "testowe": 0.01,
    "eur": 0.03,
    "utc": 0.01,
}

VAT_ECOM = 0.23
VAT_FLAT_SALES = 0.08  # dział sprzedaży „netto” liczy jedną stawką 8%


@dataclass
class Params:
    seed: int = 2030

    # --- populacja biur -------------------------------------------------
    n_initial_offices: int = 1335
    churn_rate_90d: float = 0.035
    shrink_last_block: int = 50  # w bloku VII-IX 2026 przybywa mniej biur

    # --- ukryte ryzyko i odejścia ------------------------------------------
    episode_rate_year: float = 0.4985864999452624
    episode_severity_shape: float = 2.5
    episode_severity_scale: float = 0.5
    episode_ramp: tuple = (100, 200)  # narastanie ryzyka (dni)
    episode_plateau: tuple = (10, 40)
    episode_tau: tuple = (15, 40)  # tempo wygaszania po epizodzie
    cause_brew: dict = field(default_factory=lambda: {
        "awarie": 1.9117144643911432, "finanse": 1.7751776894466365, "zaangazowanie": 2.731034921642208, "obsluga": 1.9117144643911432})
    hazard_lag: tuple = (0, 1)  # opóźnienie decyzji względem sygnałów (dni)
    hazard_beta: float = 1.3810734685226242  # siła wpływu ryzyka na hazard
    hazard_frailty_sd: float = 0.6837008819755112
    frailty_chronic: float = 0.19028564183407803  # wpływ chronicznego niezadowolenia na hazard
    contract_end_window: int = 60  # okres decyzji o odnowieniu (dni przed końcem umowy)
    contract_end_boost: float = 1.5  # mnożnik hazardu w oknie decyzji
    contract_end_risk_boost: float = 46.98942502750854  # dodatkowy wzrost dla biur z ryzykiem
    post_renewal_days: int = 120  # tuż po odnowieniu biura rzadziej wypowiadają
    post_renewal_mult: float = 0.5
    fuzja_mult: float = 2.41747433912654  # hazard po fuzji (20–150 dni)
    przeprowadzka_mult: float = 1.8307011240233102
    type_b_prob: float = 0.8328297042960912  # P(brak odnowienia | koniec umowy w bloku)

    # siła sygnałów pobocznych (generowane po selekcji odejść — nie zmieniają tego, kto odchodzi)
    signal_strength: float = 0.4  # skaluje wpływ ryzyka na płatności i reklamacje
    nps_chronic: float = 0.7  # wpływ chronicznego niezadowolenia na brak odpowiedzi NPS
    nps_risk: float = 1.0  # wpływ bieżącego ryzyka na brak odpowiedzi NPS
    awarie_cluster: tuple = (3, 6)  # liczba awarii w epizodzie „awarie” (zakres [a, b))

    # --- wizyty retencyjne (Decyzja) --------------------------------------
    visit_prob_flagged: float = 0.5
    visit_prob_other: float = 0.012
    visit_window_days: int = 8  # wizyta w pierwszych dniach bloku
    uplift_shares: dict = field(default_factory=lambda: {
        "przekonywalni": 0.50, "pewni": 0.22, "straceni": 0.15, "nie_budzic": 0.13})
    uplift_mult: dict = field(default_factory=lambda: {
        "przekonywalni": 0.10, "pewni": 1.0, "straceni": 1.0, "nie_budzic": 1.75})

    # --- telemetria / firmware --------------------------------------------
    double_share_mean: float = 0.79  # udział napojów na podwójnym espresso
    firmware_rollout = (dt.date(2026, 5, 4), dt.date(2026, 5, 29))

    # --- POS -----------------------------------------------------------------
    pos_traffic_mult: float = 1.0  # kalibrowane
    lokal17_mult: float = 2.6  # kalibrowane
    pos_dup_days = (dt.date(2026, 9, 11), dt.date(2026, 9, 12), dt.date(2026, 9, 13))

    # --- B2B -----------------------------------------------------------------
    b2b_price_mult: float = 1.0  # kalibrowane
    n_fanout_pairs: int = 18  # kalibrowane (duplikaty z identycznym NIP)
    n_duplicates: int = 112
    korekta_rate: float = 0.04

    # --- e-commerce ----------------------------------------------------------
    ecom_price_mult: float = 1.0  # kalibrowane
    eur_price_mult: float = 1.0
    de_share: float = 0.03  # kalibrowane (udział zamówień do DE w EUR)
    return_prob: float = 0.07  # kalibrowane
    test_amount_mult: float = 1.0  # kalibrowane
    sub_billing_window_min: float = 150.0  # kalibrowane (okno nocnego batcha)
    midnight_drop_orders: int = 45  # premiera kawy miesiąca o północy 1. dnia miesiąca
    sept_campaign_annual: int = 160  # kalibrowane
    gift_breakage: float = 0.18  # kalibrowane

    def to_dict(self) -> dict:
        d = asdict(self)
        d["firmware_rollout"] = [x.isoformat() for x in self.firmware_rollout]
        d["pos_dup_days"] = [x.isoformat() for x in self.pos_dup_days]
        return d
