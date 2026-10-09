"""Materializacja tabel CRM / ERP / IoT / helpdesk w kształcie widocznym dla uczestników."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .signals import crm_state
from .timeutil import DAYS, to_date


def _date(days) -> np.ndarray:
    return DAYS[np.asarray(days)].date if np.all(np.asarray(days) >= 0) else \
        (pd.Timestamp("2024-01-01") + pd.to_timedelta(np.asarray(days), unit="D")).date


def crm_tables(W, price_mult: float, rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    off = W.off
    ids = off.id_biura.to_numpy()
    biura = crm_state(off, W.sim, W.events, price_mult)
    # przeprowadzka: CRM pokazuje nowy adres (stan na dziś), ERP często stary
    moved = W.sim.events_extra[W.sim.events_extra.typ == "przeprowadzka"].office.unique()
    for o in moved:
        old = biura.at[o, "kod_pocztowy"]
        biura.at[o, "kod_pocztowy"] = f"{old[:2]}-{rng.integers(0, 1000):03d}"
    ev = W.events[(W.events.day >= 0) | (W.events.typ == "start")].copy()
    hist = pd.DataFrame({
        "id_biura": ids[ev.office.to_numpy()],
        "data_zdarzenia": _date(ev.day.to_numpy()),
        "typ": ev.typ.to_numpy(), "plan": ev.plan.to_numpy(),
        "cena": (ev.cena_base.to_numpy() * price_mult).round(2),
    }).sort_values(["data_zdarzenia", "id_biura"]).reset_index(drop=True)
    ct = W.contacts
    kontakty = pd.DataFrame({
        "id_biura": ids[ct.office.to_numpy()], "data": _date(ct.day.to_numpy()), "typ": ct.typ.to_numpy(),
        "rabat_retencyjny_pct": ct.rabat_retencyjny_pct.to_numpy(),
        "czy_retencyjna": ct.czy_retencyjna.to_numpy(),
    })
    nps = W.nps
    nps_t = pd.DataFrame({
        "id_biura": ids[nps.office.to_numpy()], "data_wysylki": _date(nps.send_day.to_numpy()),
        "data_odpowiedzi": [to_date(d) if d >= 0 else None for d in nps.resp_day],
        "wynik": pd.array([w if w >= 0 else pd.NA for w in nps.wynik], dtype="Int64"),
    })
    return {"crm_biura": biura, "crm_umowy_historia": hist, "crm_kontakty_am": kontakty,
            "ankiety_nps": nps_t}


def iot_tables(W) -> dict[str, pd.DataFrame]:
    ids = W.off.id_biura.to_numpy()
    m = W.machines
    eksp = pd.DataFrame({
        "id_ekspresu": m.id_ekspresu, "id_biura": ids[m.office.to_numpy()], "model": m.model,
        "data_instalacji": (pd.Timestamp("2024-01-01") + pd.to_timedelta(m.install_day, unit="D")).dt.date,
    })
    tel = W.telemetry[["id_ekspresu", "data", "zaparzenia", "bledy", "firmware", "data_dostarczenia"]]
    return {"iot_ekspresy": eksp, "iot_telemetria": tel}


def helpdesk_table(W) -> pd.DataFrame:
    ids = W.off.id_biura.to_numpy()
    hd = W.helpdesk
    return pd.DataFrame({"id": hd.id, "id_biura": ids[hd.office.to_numpy()],
                         "utworzono": hd.utworzono.dt.floor("min"),
                         "kategoria": hd.kategoria,
                         "rozwiazano": hd.rozwiazano.dt.floor("min")})


def erp_tables(W) -> dict[str, pd.DataFrame]:
    e = W.erp
    reg = W.kontr_reg[["id_kontrahenta", "nazwa", "nip", "adres", "kod_pocztowy", "id_biura_crm"]]
    arch = W.kontr_arch[["id_kontrahenta", "nazwa", "nip", "adres", "kod_pocztowy", "id_biura_crm"]]
    fak = e["faktury"][["nr_faktury", "id_kontrahenta", "data", "typ", "waluta", "kwota_netto", "vat"]]
    poz = e["pozycje"]
    plat = e["platnosci"][["nr_faktury", "data_platnosci", "kwota", "spor"]]
    kart = W.kart[["indeks", "nazwa", "kategoria"]]
    return {"erp_kontrahenci": reg, "erp_kontrahenci_archiwum": arch, "erp_faktury": fak,
            "erp_pozycje": poz, "erp_platnosci": plat, "erp_kartoteka": kart}
