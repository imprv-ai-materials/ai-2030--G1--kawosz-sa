"""Cechy na migawkach: uczciwe (znane w t0) oraz cechy „agencji” (z przeciekami).

Funkcje działają na tabelach w kształcie widocznym dla uczestników, więc
walidacja może liczyć je zarówno z pamięci, jak i z plików CSV.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import EXPORT

DATE_COLS = {
    "crm_biura": ["data_startu", "data_konca_umowy"],
    "crm_umowy_historia": ["data_zdarzenia"],
    "crm_kontakty_am": ["data"],
    "ankiety_nps": ["data_wysylki", "data_odpowiedzi"],
    "iot_ekspresy": ["data_instalacji"],
    "iot_telemetria": ["data", "data_dostarczenia"],
    "helpdesk_zgloszenia": ["utworzono", "rozwiazano"],
    "erp_faktury": ["data"],
    "erp_platnosci": ["data_platnosci"],
}

HONEST = ["zap_30", "zap_90", "trend_30_90", "bledy_60", "awarie_60", "inne_90", "dni_do_konca",
          "staz_dni", "cena", "plan_num", "liczba_pracownikow", "n_ekspresow", "opozn_sr_180",
          "opozn_max_180", "zalegle", "dni_od_zam_kawy", "kawa_trend", "nps_ostatni", "nps_brak_odp",
          "nps_brak_odp_2", "downgrade_180", "fuzja_przepr_180", "zawieszenie_180", "kontakty_am_90",
          "korekty_180", "spory_180"]

PLAN_NUM = {"S": 1, "M": 2, "L": 3, "XL": 4}


def prepare(T: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    out = {}
    for k, df in T.items():
        df = df.copy()
        for c in DATE_COLS.get(k, []):
            if c in df:
                df[c] = pd.to_datetime(df[c])
        out[k] = df
    return out


class Snapshotter:
    """Wstępnie agreguje tabele, by szybko liczyć cechy dla wielu migawek."""

    def __init__(self, T: dict[str, pd.DataFrame]):
        self.T = T
        b = T["crm_biura"].set_index("id_biura")
        h = T["crm_umowy_historia"]
        wyp = h[h.typ == "wypowiedzenie"].groupby("id_biura").data_zdarzenia.min()
        churn = pd.Series(pd.NaT, index=b.index, dtype="datetime64[ns]")
        churn.loc[wyp.index] = wyp
        typeb = (b.status == "zakończony") & churn.isna()
        churn.loc[typeb] = b.loc[typeb, "data_konca_umowy"] + pd.Timedelta(days=1)
        self.biura = b
        self.churn_date = churn
        self.hist = h.sort_values("data_zdarzenia")
        e = T["iot_ekspresy"]
        tel = T["iot_telemetria"].merge(e[["id_ekspresu", "id_biura"]], on="id_ekspresu")
        self.tel_day = tel.groupby(["id_biura", "data"], as_index=False)[["zaparzenia", "bledy"]].sum()
        self.n_eksp = e.groupby("id_biura").size()
        self.hd = T["helpdesk_zgloszenia"]
        f = T["erp_faktury"]
        k = T["erp_kontrahenci"]
        ka = T.get("erp_kontrahenci_archiwum")
        kk = pd.concat([k, ka]) if ka is not None else k
        kk = kk.copy()
        kk["nip_norm"] = kk.nip.astype(str).str.replace("-", "", regex=False)
        # mapowanie kontrahent -> biuro: id_biura_crm, a gdy puste — po znormalizowanym NIP
        crm_nip = b.reset_index()[["id_biura", "nip"]].rename(columns={"nip": "nip_norm"})
        crm_nip["nip_norm"] = crm_nip.nip_norm.astype(str)
        kk = kk.merge(crm_nip, on="nip_norm", how="left")
        idc = pd.to_numeric(kk.id_biura_crm, errors="coerce")
        kk["id_biura"] = idc.fillna(kk.id_biura)
        self.k2b = kk.dropna(subset=["id_biura"]).drop_duplicates("id_kontrahenta").set_index("id_kontrahenta").id_biura.astype(int)
        f = f.copy()
        f["id_biura"] = f.id_kontrahenta.map(self.k2b)
        self.fak = f
        poz = T["erp_pozycje"]
        kart = T["erp_kartoteka"]
        coffee_idx = set(kart[kart.nazwa.str.startswith("KAWA ZIARN.")].indeks)
        pc = poz[poz.indeks.isin(coffee_idx) & (poz.ilosc > 0)].copy()
        pc["kg"] = pc.ilosc * np.where(pc.indeks.map(kart.set_index("indeks").nazwa).str.contains("6KG"), 6, 1)
        pc = pc.groupby("nr_faktury").kg.sum()
        f2 = f[f.typ == "faktura"].copy()
        f2["kg"] = f2.nr_faktury.map(pc).fillna(0)
        self.coffee = f2[f2.kg > 0][["id_biura", "data", "kg"]]
        p = T["erp_platnosci"].merge(f2[["nr_faktury", "data", "id_biura"]], on="nr_faktury")
        p["opozn"] = (p.data_platnosci - (p.data + pd.Timedelta(days=14))).dt.days
        self.pay = p
        self.inv = f2
        self.nps = T["ankiety_nps"]
        self.ct = T["crm_kontakty_am"]

    # ------------------------------------------------------------------
    def population(self, t0: pd.Timestamp) -> pd.Index:
        b = self.biura
        cd = self.churn_date
        m = (b.data_startu < t0) & (cd.isna() | (cd >= t0))
        return b.index[m]

    def labels(self, t0: pd.Timestamp, ids: pd.Index, horizon: int = 90) -> pd.Series:
        cd = self.churn_date.reindex(ids)
        return ((cd >= t0) & (cd < t0 + pd.Timedelta(days=horizon))).astype(int)

    def honest(self, t0: pd.Timestamp) -> pd.DataFrame:
        ids = self.population(t0)
        X = pd.DataFrame(index=ids)
        b = self.biura.loc[ids]
        td = self.tel_day
        last = t0 - pd.Timedelta(days=2)  # dostarczone przed t0
        w30 = td[(td.data >= last - pd.Timedelta(days=30)) & (td.data < last)].groupby("id_biura")
        w90 = td[(td.data >= last - pd.Timedelta(days=90)) & (td.data < last)].groupby("id_biura")
        w60 = td[(td.data >= last - pd.Timedelta(days=60)) & (td.data < last)].groupby("id_biura")
        X["zap_30"] = w30.zaparzenia.sum().reindex(ids).fillna(0)
        X["zap_90"] = w90.zaparzenia.sum().reindex(ids).fillna(0)
        X["trend_30_90"] = np.where(X.zap_90 > 0, (X.zap_30 / 30) / (X.zap_90 / 90).replace(0, np.nan), 1.0)
        X["trend_30_90"] = X.trend_30_90.fillna(1.0)
        X["bledy_60"] = w60.bledy.sum().reindex(ids).fillna(0)
        hd = self.hd[self.hd.utworzono < t0]
        X["awarie_60"] = hd[(hd.kategoria == "awaria") & (hd.utworzono >= t0 - pd.Timedelta(days=60))] \
            .groupby("id_biura").size().reindex(ids).fillna(0)
        X["inne_90"] = hd[(hd.kategoria == "inne") & (hd.utworzono >= t0 - pd.Timedelta(days=90))] \
            .groupby("id_biura").size().reindex(ids).fillna(0)
        # koniec bieżącego okresu umowy: kolejna rocznica startu
        st = b.data_startu
        ann = pd.to_datetime([_anniv(s, t0) for s in st])
        X["dni_do_konca"] = (ann - t0).days.to_numpy()
        X["staz_dni"] = (t0 - st).dt.days
        h = self.hist[self.hist.data_zdarzenia < t0]
        hp = h[h.typ.isin(["start", "odnowienie", "downgrade"])].groupby("id_biura").last()
        X["cena"] = hp.cena.reindex(ids)
        X["plan_num"] = hp.plan.map(PLAN_NUM).reindex(ids)
        X["liczba_pracownikow"] = b.liczba_pracownikow
        X["n_ekspresow"] = self.n_eksp.reindex(ids).fillna(1)
        p = self.pay[(self.pay.data_platnosci < t0) & (self.pay.data >= t0 - pd.Timedelta(days=180))]
        g = p.groupby("id_biura").opozn
        X["opozn_sr_180"] = g.mean().reindex(ids).fillna(0)
        X["opozn_max_180"] = g.max().reindex(ids).fillna(0)
        inv = self.inv[(self.inv.data + pd.Timedelta(days=14) < t0)]
        paid = self.pay[self.pay.data_platnosci < t0].nr_faktury
        X["zalegle"] = inv[~inv.nr_faktury.isin(paid)].groupby("id_biura").size().reindex(ids).fillna(0)
        cf = self.coffee[self.coffee.data < t0]
        lastc = cf.groupby("id_biura").data.max().reindex(ids)
        X["dni_od_zam_kawy"] = (t0 - lastc).dt.days.fillna(365)
        k90 = cf[cf.data >= t0 - pd.Timedelta(days=90)].groupby("id_biura").kg.sum().reindex(ids).fillna(0)
        k270 = cf[(cf.data >= t0 - pd.Timedelta(days=270)) & (cf.data < t0 - pd.Timedelta(days=90))] \
            .groupby("id_biura").kg.sum().reindex(ids).fillna(0)
        X["kawa_trend"] = (k90 + 1) / (k270 / 2 + 1)
        n = self.nps[self.nps.data_wysylki < t0].sort_values("data_wysylki")
        resp_known = n.data_odpowiedzi.notna() & (n.data_odpowiedzi < t0)
        n = n.assign(resp=resp_known, wynik_k=n.wynik.where(resp_known))
        lastn = n.groupby("id_biura").last()
        X["nps_brak_odp"] = (~lastn.resp).astype(float).reindex(ids).fillna(0.5)
        X["nps_ostatni"] = n[n.resp].groupby("id_biura").wynik_k.last().reindex(ids).astype(float).fillna(-1)
        X["nps_brak_odp_2"] = (~n.groupby("id_biura").tail(2).groupby("id_biura").resp.any()) \
            .astype(float).reindex(ids).fillna(0.5)
        h180 = h[h.data_zdarzenia >= t0 - pd.Timedelta(days=180)]
        for col, typs in (("downgrade_180", ["downgrade"]), ("fuzja_przepr_180", ["fuzja", "przeprowadzka"]),
                          ("zawieszenie_180", ["zawieszenie"])):
            X[col] = h180[h180.typ.isin(typs)].groupby("id_biura").size().reindex(ids).fillna(0)
        ct = self.ct[(self.ct.data < t0) & (self.ct.data >= t0 - pd.Timedelta(days=90))]
        X["kontakty_am_90"] = ct.groupby("id_biura").size().reindex(ids).fillna(0)
        kor = self.fak[(self.fak.typ == "korekta") & (self.fak.data < t0) &
                       (self.fak.data >= t0 - pd.Timedelta(days=180))]
        X["korekty_180"] = kor.groupby("id_biura").size().reindex(ids).fillna(0)
        sp = p[p.spor]
        X["spory_180"] = sp.groupby("id_biura").size().reindex(ids).fillna(0)
        X["y"] = self.labels(t0, ids)
        X["t0"] = t0
        return X

    def am_rule(self, X: pd.DataFrame) -> pd.Series:
        """Reguła AM: do końca umowy < 90 dni i zaparzenia spadły o ≥30%."""
        return ((X.dni_do_konca < 90) & (X.trend_30_90 <= 0.7)).astype(int)


def _anniv(start: pd.Timestamp, t0: pd.Timestamp) -> pd.Timestamp:
    y = max(start.year + 1, t0.year)
    for yy in (y - 1, y, y + 1):
        if yy <= start.year:
            continue
        try:
            a = start.replace(year=yy)
        except ValueError:
            a = start.replace(year=yy, day=28)
        if a > t0:
            return a
    return start.replace(year=t0.year + 1)


# ---------------------------------------------------------------------------
AGENCY_COLS = ["status_crm", "plan", "liczba_pracownikow", "branza", "miasto", "miasto_te", "am_id",
               "staz_mies", "dni_do_konca_umowy", "cena_mies", "zaparzenia_30d", "trend_zaparzen",
               "bledy_60d", "awarie_60d", "zgloszenia_odbior_ekspresu", "rabat_retencyjny_max",
               "kontakty_am_90d", "sr_opoznienie_platnosci", "dni_od_ostatniego_zamowienia", "nps_ostatni"]


def agency_features(S: Snapshotter, snapshots: list[pd.Timestamp]) -> pd.DataFrame:
    """Gotowa tabela agencji: 20 cech, w tym przecieki (opis w kluczu odpowiedzi)."""
    exp = pd.Timestamp(EXPORT)
    rows = []
    b = S.biura
    td = S.tel_day
    for t0 in snapshots:
        X = S.honest(t0)
        ids = X.index
        A = pd.DataFrame(index=ids)
        A["status_crm"] = b.loc[ids, "status"]  # PRZECIEK: stan z dnia eksportu
        A["plan"] = b.loc[ids, "plan"]  # stan z eksportu
        A["liczba_pracownikow"] = b.loc[ids, "liczba_pracownikow"]
        A["branza"] = b.loc[ids, "branza"]
        A["miasto"] = b.loc[ids, "miasto"]
        A["am_id"] = b.loc[ids, "am_id"]
        A["staz_mies"] = ((t0 - b.loc[ids, "data_startu"]).dt.days / 30.44).round(1)
        A["dni_do_konca_umowy"] = (b.loc[ids, "data_konca_umowy"] - t0).dt.days  # z eksportu
        A["cena_mies"] = b.loc[ids, "cena_mies"]
        fut = td[(td.data >= t0) & (td.data < t0 + pd.Timedelta(days=30))]
        A["zaparzenia_30d"] = fut.groupby("id_biura").zaparzenia.sum().reindex(ids).fillna(0)  # PRZECIEK
        A["trend_zaparzen"] = X.trend_30_90.round(3)
        A["bledy_60d"] = X.bledy_60
        A["awarie_60d"] = X.awarie_60
        hd = S.hd
        A["zgloszenia_odbior_ekspresu"] = hd[hd.kategoria == "odbiór ekspresu"].groupby("id_biura") \
            .size().reindex(ids).fillna(0)  # PRZECIEK: całość do dnia eksportu
        A["rabat_retencyjny_max"] = S.ct.groupby("id_biura").rabat_retencyjny_pct.max() \
            .reindex(ids).fillna(0)  # PRZECIEK
        A["kontakty_am_90d"] = X.kontakty_am_90
        A["sr_opoznienie_platnosci"] = X.opozn_sr_180.round(1)
        lastc = S.coffee.groupby("id_biura").data.max().reindex(ids)
        A["dni_od_ostatniego_zamowienia"] = (exp - lastc).dt.days.fillna(999)  # PRZECIEK: od eksportu
        A["nps_ostatni"] = X.nps_ostatni.replace(-1, np.nan)
        A["odejdzie_90d"] = X.y
        A["data_migawki"] = t0.date()
        rows.append(A)
    out = pd.concat(rows)
    # PRZECIEK: target encoding miasta na całym zbiorze (łącznie z migawką testową)
    te = out.groupby("miasto").odejdzie_90d.mean()
    out["miasto_te"] = out.miasto.map(te).round(4)
    out = out.reset_index(names="id_biura")
    return out[["id_biura", "data_migawki"] + AGENCY_COLS + ["odejdzie_90d"]]
