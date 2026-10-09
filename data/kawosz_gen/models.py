"""Modele referencyjne do warunków kontrolnych (uczciwy model, reguła AM, agencja, PSI)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .features import Snapshotter, agency_features

TRAIN_SNAPSHOTS = [pd.Timestamp(d) for d in ["2024-04-01", "2024-07-01", "2024-10-01", "2025-01-01",
                                             "2025-04-01", "2025-07-01"]]
CALIB_SNAPSHOTS = [pd.Timestamp("2025-10-01"), pd.Timestamp("2026-01-01")]
TEST_SNAPSHOT = pd.Timestamp("2026-04-01")
PSI_REF, PSI_CUR = pd.Timestamp("2026-04-01"), pd.Timestamp("2026-07-01")


def design(X: pd.DataFrame) -> pd.DataFrame:
    """Macierz cech uczciwego modelu (transformacje log / wskaźniki)."""
    Z = pd.DataFrame(index=X.index)
    tr = np.clip(X.trend_30_90, 0, 2)
    Z["trend"] = tr
    Z["trend_le_07"] = (X.trend_30_90 <= 0.7).astype(float)
    Z["koniec_lt_90"] = (X.dni_do_konca < 90).astype(float)
    Z["dni_do_konca"] = X.dni_do_konca / 365
    Z["koniec_x_spadek"] = Z.koniec_lt_90 * (1 - np.clip(tr, 0, 1.2))
    for c in ["zap_30", "bledy_60", "awarie_60", "inne_90", "opozn_sr_180", "opozn_max_180", "zalegle",
              "dni_od_zam_kawy", "korekty_180", "spory_180", "kontakty_am_90", "downgrade_180",
              "fuzja_przepr_180", "zawieszenie_180", "liczba_pracownikow", "staz_dni", "cena"]:
        Z[c] = np.log1p(np.clip(X[c], 0, None))
    Z["kawa_trend"] = np.log(X.kawa_trend)
    Z["nps_ostatni"] = X.nps_ostatni
    Z["nps_brak_odp"] = X.nps_brak_odp
    Z["nps_brak_odp_2"] = X.nps_brak_odp_2
    Z["plan"] = X.plan_num
    return Z.fillna(0)


def honest_model(S: Snapshotter, seed: int = 0) -> dict:
    """Regresja logistyczna, podział czasowy, kalibracja Platta na migawkach out-of-time."""
    tr = pd.concat([S.honest(t) for t in TRAIN_SNAPSHOTS])
    ca = pd.concat([S.honest(t) for t in CALIB_SNAPSHOTS])
    te = S.honest(TEST_SNAPSHOT)
    clf = make_pipeline(StandardScaler(), LogisticRegression(C=0.2, max_iter=3000))
    clf.fit(design(tr), tr.y)
    raw_ca = clf.decision_function(design(ca))
    raw_te = clf.decision_function(design(te))
    platt = LogisticRegression(C=1e6).fit(raw_ca.reshape(-1, 1), ca.y)
    p = platt.predict_proba(raw_te.reshape(-1, 1))[:, 1]
    y = te.y.to_numpy()
    order = np.argsort(-p)
    rule = S.am_rule(te)
    out = {
        "n_test": int(len(te)), "pos_test": int(y.sum()), "pos_train": int(tr.y.sum()),
        "auc_test": float(roc_auc_score(y, raw_te)), "auc_calib": float(roc_auc_score(ca.y, raw_ca)),
        "thr_0_5_n": int((p > 0.5).sum()), "thr_0_5_tp": int(y[p > 0.5].sum()),
        "top60_tp": int(y[order[:60]].sum()),
        "thr_0_175_n": int((p > 0.175).sum()), "thr_0_175_tp": int(y[p > 0.175].sum()),
        "am_rule_auc": float(roc_auc_score(y, rule)),
        "am_rule_n": int(rule.sum()), "am_rule_tp": int(y[rule == 1].sum()),
    }
    return out


def agency_model(S: Snapshotter, table: pd.DataFrame | None = None, seed: int = 0) -> dict:
    A = table if table is not None else agency_features(S, TRAIN_SNAPSHOTS + CALIB_SNAPSHOTS + [TEST_SNAPSHOT])
    X = A.drop(columns=["id_biura", "data_migawki", "odejdzie_90d", "miasto"])
    X = pd.get_dummies(X, columns=["status_crm", "plan", "branza"], dtype=float)
    X = X.fillna(-1)
    is_test = pd.to_datetime(A.data_migawki) == TEST_SNAPSHOT
    clf = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=300, random_state=seed)
    clf.fit(X[~is_test], A.odejdzie_90d[~is_test])
    p = clf.predict_proba(X[is_test])[:, 1]
    rng = np.random.default_rng(seed)
    rnd = rng.random(len(A)) < 0.25
    clf2 = HistGradientBoostingClassifier(max_depth=4, learning_rate=0.05, max_iter=300, random_state=seed)
    clf2.fit(X[~rnd], A.odejdzie_90d[~rnd])
    p2 = clf2.predict_proba(X[rnd])[:, 1]
    return {"auc_agency_test": float(roc_auc_score(A.odejdzie_90d[is_test], p)),
            "auc_agency_random_split": float(roc_auc_score(A.odejdzie_90d[rnd], p2))}


def psi(ref: np.ndarray, cur: np.ndarray, bins: int = 10) -> float:
    q = np.quantile(ref, np.linspace(0, 1, bins + 1))
    q[0], q[-1] = -np.inf, np.inf
    q = np.unique(q)
    r = np.histogram(ref, q)[0] / len(ref)
    c = np.histogram(cur, q)[0] / len(cur)
    r, c = np.clip(r, 1e-6, None), np.clip(c, 1e-6, None)
    return float(((c - r) * np.log(c / r)).sum())


def drift(S: Snapshotter) -> dict:
    a = S.honest(PSI_REF)
    b = S.honest(PSI_CUR)
    a, b = a[a.zap_30 > 0], b[b.zap_30 > 0]
    return {"psi_zaparzenia_30d": psi(a.zap_30.to_numpy(), b.zap_30.to_numpy()),
            "median_ref": float(a.zap_30.median()), "median_cur": float(b.zap_30.median())}


def nps_mnar(S: Snapshotter) -> dict:
    X = pd.concat([S.honest(t) for t in TRAIN_SNAPSHOTS + CALIB_SNAPSHOTS + [TEST_SNAPSHOT]])
    X = X[X.nps_brak_odp != 0.5]
    r_no = X[X.nps_brak_odp == 1].y.mean()
    r_yes = X[X.nps_brak_odp == 0].y.mean()
    return {"churn_no_response": float(r_no), "churn_response": float(r_yes), "ratio": float(r_no / r_yes)}
