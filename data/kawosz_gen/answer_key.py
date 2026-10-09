"""Klucz odpowiedzi (krok 7) — niewidoczny dla uczestników.

Zapisuje `klucz_odpowiedzi.json` (pełne dane) oraz `klucz_odpowiedzi.md` (opis).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .config import Params, SNAPSHOT_TEST
from .features import prepare, Snapshotter
from . import models
from .pos import TYPO_DAY, TYPO_LOKAL
from .products import shared_mapping
from .revenue import BRIDGE_STEPS, BRIDGE_ORDER, is_test_order
from .timeutil import day_index, to_date

BRIDGE_LABELS = {
    "vat": "VAT w POS i e-commerce", "zwroty": "Zwroty i korekty nieodjęte",
    "fanout": "Fan-out na zdublowanych kontrahentach", "subskrypcje": "Subskrypcje roczne w miesiącu płatności",
    "pos_duplikaty": "Zdublowane pliki POS lokalu 17 (3 dni)", "karty": "Karty podarunkowe przy sprzedaży",
    "testowe": "Zamówienia testowe", "eur": "EUR zapisane jako PLN", "utc": "Granica doby w UTC",
}

REPORTS = {
    "bi": "Dashboard BI — surowa suma źródeł: ERP (dokumenty typu 'faktura', złączone z kontrahentami po "
          "surowym NIP → fan-out), POS kwota_brutto ze wszystkich plików (z duplikatami), e-commerce `brutto` "
          "(kwoty EUR traktowane jak PLN, miesiąc wg UTC, z testowymi i zwrotami), subskrypcje w miesiącu "
          "płatności (UTC), karty podarunkowe w dniu sprzedaży.",
    "sprzedaz": "Raport sprzedaży — te same źródła co BI, „netto” liczone jedną stawką 8% (stawka gastronomiczna) "
                "dla POS i e-commerce; bez odjęcia zwrotów, bez deduplikacji (fan-out, duplikaty plików POS).",
    "ksiegowosc": "Księgowość — ERP (widok hurtowni z fan-outem po NIP; korekty i zwroty z września nie są jeszcze "
                  "zaksięgowane na dzień eksportu) + POS netto z pozycji (bez duplikatów plików) + e-commerce netto "
                  "(EUR po kursie NBP, doba warszawska, z zamówieniami testowymi opłaconymi bramką), subskrypcje "
                  "nierozłożone (w miesiącu płatności), karty przy sprzedaży.",
    "definicja": "Definicja — netto (POS wg stawek z pozycji, e-commerce/karty/subskrypcje 23%), po odjęciu korekt "
                 "ERP i zwrotów e-commerce, bez fan-outu, subskrypcje roczne rozłożone na 12 miesięcy, karty w dniu "
                 "realizacji, EUR po kursie NBP z dnia sprzedaży (dzień bez notowania → ostatni wcześniejszy kurs), "
                 "bez zamówień testowych (notatka zawiera „test” lub e-mail w domenie kawosz.pl), doba Europe/Warsaw.",
}


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest(root: Path) -> dict:
    out = {}
    for p in sorted([*root.rglob("*.parquet"), *root.rglob("*.zip")]):
        out[str(p.relative_to(root))] = {"bajty": p.stat().st_size, "sha256": _sha(p)}
    return out


def build_answer_key(P: Params, W, T: dict, cal: dict, pos_info: dict, orders, subs, gift, lok, pos_cat,
                     ecom_prod, root: Path, key_dir: Path) -> dict:
    key_dir.mkdir(parents=True, exist_ok=True)
    off, sim = W.off, W.sim
    ids = off.id_biura.to_numpy()
    rep = cal["reports"]
    mln = lambda v: round(float(v) / 1e6, 4)

    # --- przychód -----------------------------------------------------------
    parts = {k: {kk: round(float(vv), 2) for kk, vv in v.items() if not kk.startswith("_")}
             for k, v in rep["parts"].items()}
    revenue = {
        "miesiac": "2026-09",
        "raporty_mln": {k: mln(rep[k]) for k in ("bi", "sprzedaz", "ksiegowosc", "definicja")},
        "raporty_opis": REPORTS,
        "most_mln": {BRIDGE_LABELS[k]: mln(-rep["bridge"][k] if k not in ("eur", "utc") else rep["bridge"][k])
                     for k in BRIDGE_STEPS},
        "most_znak": "wartości dodatnie odejmujemy od BI (oprócz EUR i UTC, które dodajemy)",
        "most_kolejnosc_obliczen": BRIDGE_ORDER,
        "skladniki_pln": parts,
        "parametry_kalibracji": {k: getattr(P, k) for k in (
            "b2b_price_mult", "pos_traffic_mult", "ecom_price_mult", "lokal17_mult", "de_share",
            "sub_billing_window_min", "return_prob", "n_fanout_pairs", "sept_campaign_annual", "gift_breakage",
            "test_amount_mult")},
        "iteracje_kalibracji": cal["iterations"],
    }

    # --- usterki ------------------------------------------------------------
    info = W.kontr_info
    dups = info["dups"]
    kid = info["kid"]
    reg = W.kontr_reg
    dup_pairs = [{"id_biura": int(ids[r.office]), "id_kontrahenta_oryginal": int(kid[r.office]),
                  "id_kontrahenta_duplikat": int(r.id_kontrahenta), "nazwa_duplikatu": r.nazwa, "nip_duplikatu": r.nip,
                  "identyczny_nip_fanout": bool(r.fanout)} for r in dups.itertuples()]
    nip9 = reg[reg.nip.str.replace("-", "").str.len() == 9][["id_kontrahenta", "nip"]]
    o = orders.copy()
    o["waw"] = o.data_lokalna
    sept = o[(o.waw >= "2026-09-01") & (o.waw < "2026-10-01")]
    det = is_test_order(o)
    fak = W.erp["faktury"]
    big = fak[(fak.office == W.big_sale["office"]) & (fak.day == W.big_sale["day"]) & (fak.typ == "faktura")]
    big = big.sort_values("kwota_netto").iloc[-1]
    kart = T["erp_kartoteka"]
    pay = o.metoda_platnosci
    neg = pos_info["neg"]
    stats = pos_info["stats"]
    defects = {
        "kontrahenci": {"wiersze": int(len(reg)), "duplikaty": int(len(dups)),
                        "duplikaty_z_identycznym_nip_fanout": int(dups.fanout.sum()),
                        "pary": dup_pairs,
                        "archiwum": "erp_kontrahenci_archiwum.parquet — kontrahenci z zakończonymi umowami (ERP "
                                    "przenosi ich z rejestru); potrzebni do łączenia historycznych faktur"},
        "nip_9_cyfr": {"liczba": int(len(nip9)), "lista": nip9.to_dict("records")},
        "kartoteka_bez_kategorii": {"liczba": int((kart.kategoria == "").sum()), "udzial": round(float((kart.kategoria == "").mean()), 4),
                                    "indeksy": W.refs["missing_category"]},
        "pozycje_ujemne_bez_storno": {"liczba": int(len(neg)), "opis": "zwrot towaru przy kasie zapisany jako "
                                      "pozycja z ilością -1 na zwykłym paragonie (storno = 0)"},
        "storno": {"paragony_storno": int(stats.storno.sum()), "opis": "anulowanie = osobny paragon z ujemnymi kwotami"},
        "paragon_literowka": {"lokal": TYPO_LOKAL, "data": str(to_date(TYPO_DAY)), "kwota_brutto": 48000.0,
                              "kod_produktu": "P0999", "opis": "kasjer wpisał 48000 zamiast 48,00"},
        "faktura_40_ekspresow": {"nr_faktury": big.nr_faktury, "data": str(big.data),
                                 "id_biura": int(ids[W.big_sale["office"]]), "kwota_netto": float(big.kwota_netto),
                                 "opis": "prawdziwa sprzedaż 40 ekspresów — wartość odstająca, której NIE należy usuwać"},
        "mcar_lokal_9": {"paragony": int(stats.loc[9, "paragony"]), "bez_metody_platnosci": int(stats.loc[9, "bez_metody"])},
        "mar_email": {"brak_email_pobranie": round(float((o.email == "")[pay == "pobranie"].mean()), 4),
                      "brak_email_inne": round(float((o.email == "")[pay != "pobranie"].mean()), 4)},
        "pos_nowa_kolumna": {"od": "2026-06-01", "kolumna": "kanal", "pozycja": "czwarta (po data_czas)"},
        "pos_duplikaty_plikow": [f"pos_paragony.zip: paragony/pos_paragony_17_{d.isoformat()} (1).csv" for d in P.pos_dup_days],
        "trzy_kody_produktu": shared_mapping(W.refs, pos_cat, ecom_prod).to_dict("records"),
        "zamowienia_testowe": {"wszystkie": int(o.test.sum()), "wrzesien_2026": int(sept.test.sum()),
                               "wykrywalnosc_reguly": bool((det == o.test).all()),
                               "regula": "notatka zawiera 'test' (bez względu na wielkość liter) LUB e-mail w domenie @kawosz.pl"},
        "zamowienia_eur_wrzesien": int((sept.waluta == "EUR").sum()),
        "zwroty_ecom_udzial": round(float(o.zwrot.mean()), 4),
        "fanout_biura": [int(ids[i]) for i in info["fanout_offices"]],
    }

    # --- odejścia, przecieki, modele -----------------------------------------
    S = Snapshotter(prepare(T))
    hon = models.honest_model(S)
    ag = models.agency_model(S, T["agencja_features"])
    dr = models.drift(S)
    mn = models.nps_mnar(S)
    a = day_index(SNAPSHOT_TEST)
    ch = sim.churn
    in_win = ch[ch.churned & (ch.event_day >= a) & (ch.event_day < a + 90)]
    churn = {
        "migawka_testowa": str(SNAPSHOT_TEST), "populacja": 1400, "odejscia_90d": int(len(in_win)),
        "odchodzace_id_biura": sorted(int(ids[x]) for x in in_win.office),
        "typy": {"wypowiedzenie": int((in_win.typ == "A").sum()), "brak_odnowienia": int((in_win.typ == "B").sum())},
        "definicja_targetu": "odejdzie_90d = 1, jeśli data wypowiedzenia (crm_umowy_historia, typ "
                             "'wypowiedzenie') albo — przy braku odnowienia — dzień po data_konca_umowy biura "
                             "o statusie 'zakończony' wypada w [t0, t0 + 90 dni). Populacja: data_startu < t0 i brak "
                             "wcześniejszego odejścia.",
        "mechanizm": "ukryte epizody ryzyka (awarie / finanse / spadek zaangażowania / obsługa) narastają 100–200 "
                     "dni; obniżają faktyczne spożycie kawy, zwiększają opóźnienia płatności (finanse), awarie "
                     "(3+ w ~50 dni), korekty, brak odpowiedzi NPS; hazard odejścia rośnie z ryzykiem, najmocniej "
                     "w 60 dniach przed rocznicą umowy. Część odejść jest „cicha” (fuzja, przeprowadzka, losowe).",
        "model_uczciwy": hon, "model_agencji": ag,
        "przecieki_agencji": {
            "status_crm": "stan z dnia eksportu (2026-09-30), a nie z migawki",
            "plan, cena_mies, dni_do_konca_umowy": "z eksportu CRM (po downgrade'ach i odnowieniach po t0)",
            "zaparzenia_30d": "okno [t0, t0+30) — przyszłość względem migawki",
            "zgloszenia_odbior_ekspresu": "zgłoszenie powstaje 1–20 dni PO wypowiedzeniu; liczone do dnia eksportu",
            "rabat_retencyjny_max": "rabat przyznawany dopiero PO wypowiedzeniu",
            "dni_od_ostatniego_zamowienia": "liczone od daty eksportu zamiast od t0",
            "miasto_te": "target encoding policzony na całym zbiorze (także migawka testowa)",
        },
    }

    # --- dryf i wizyty ----------------------------------------------------------
    v = sim.visits
    vv = v[~v.dropped]
    att = 1 - vv.W_with.sum() / vv.W_without.sum()
    grp = {g: {"udzial_biur": round(float((off.uplift == g).mean()), 4), "mnoznik_hazardu_po_wizycie": P.uplift_mult[g],
               "wizyty": int((vv.group == g).sum())} for g in P.uplift_shares}
    decyzja = {
        "firmware": {"wdrozenie": [d.isoformat() for d in P.firmware_rollout],
                     "opis": "nowy firmware liczy podwójne espresso jako 1 zaparzenie (wcześniej 2); spożycie bez zmian",
                     "psi": dr, "porownanie": "zaparzenia_30d (dostarczone przed t0): 2026-04-01 vs 2026-07-01, 10 przedziałów kwantylowych"},
        "wizyty_retencyjne": {
            "sredni_efekt_wzgledny": round(float(att), 4),
            "definicja_efektu": "1 − Σ hazard z wizytą / Σ hazard bez wizyty (wśród odwiedzonych, w bloku 90 dni)",
            "przydzial": "na początku każdego bloku AM odwiedza z p=%.2f biura spełniające regułę "
                         "(do końca umowy < 90 dni i trend zaparzeń ≤ 0,7), pozostałe z p=%.3f; wizyta w pierwszych %d dniach bloku"
                         % (P.visit_prob_flagged, P.visit_prob_other, P.visit_window_days),
            "grupy": grp,
            "grupa_biura": {int(i): g for i, g in zip(ids, off.uplift)},
        },
        "nps_mnar": mn,
    }

    key = {"seed": P.seed, "parametry": P.to_dict(), "przychod": revenue, "usterki": defects,
           "odejscia": churn, "decyzja": decyzja, "manifest": manifest(root)}
    (key_dir / "klucz_odpowiedzi.json").write_text(json.dumps(key, ensure_ascii=False, indent=1, default=str))
    (key_dir / "klucz_odpowiedzi.md").write_text(render_md(key), encoding="utf-8")
    return key


def render_md(k: dict) -> str:
    r = k["przychod"]
    L = ["# Kawosz S.A. — klucz odpowiedzi (NIE dla uczestników)", "",
         f"Ziarno losowania: **{k['seed']}**. Pełne dane: `klucz_odpowiedzi.json`.", "",
         "## Przychód netto — wrzesień 2026", "", "| Raport | mln PLN |", "|---|---|"]
    for n, v in r["raporty_mln"].items():
        L.append(f"| {n} | {v:.4f} |")
    L += ["", "### Most BI → definicja", "", "| Pozycja | Wpływ (mln PLN) |", "|---|---|"]
    for n, v in r["most_mln"].items():
        sign = "+" if n.startswith(("EUR", "Granica")) else "−"
        L.append(f"| {n} | {sign}{abs(v):.4f} |")
    L += ["", "Pozycje liczone sekwencyjnie w kolejności: " + ", ".join(r["most_kolejnosc_obliczen"]) +
          " — dzięki temu sumują się dokładnie, a księgowość = BI − VAT − duplikaty POS + EUR + UTC.", ""]
    for n, d in r["raporty_opis"].items():
        L.append(f"- **{n}**: {d}")
    d = k["usterki"]
    L += ["", "## Usterki jakości (projekt Fundament)", "",
          f"- Kontrahenci: {d['kontrahenci']['wiersze']} wierszy, {d['kontrahenci']['duplikaty']} rozmytych duplikatów "
          f"(w tym {d['kontrahenci']['duplikaty_z_identycznym_nip_fanout']} z identycznym NIP → fan-out w hurtowni).",
          f"- NIP z 9 cyframi: {d['nip_9_cyfr']['liczba']}.",
          f"- Kartoteka bez kategorii: {d['kartoteka_bez_kategorii']['liczba']} ({d['kartoteka_bez_kategorii']['udzial']:.1%}).",
          f"- Pozycje POS z ujemną ilością bez storno: {d['pozycje_ujemne_bez_storno']['liczba']}.",
          f"- Paragon-literówka: lokal {d['paragon_literowka']['lokal']}, {d['paragon_literowka']['data']}, 48 000 zł.",
          f"- Faktura na 40 ekspresów: {d['faktura_40_ekspresow']['nr_faktury']} ({d['faktura_40_ekspresow']['kwota_netto']:,.2f} zł netto) — prawdziwa.",
          f"- MCAR lokal 9: {d['mcar_lokal_9']['bez_metody_platnosci']} z {d['mcar_lokal_9']['paragony']} paragonów bez metody płatności.",
          f"- MAR e-mail: brak e-maila przy pobraniu {d['mar_email']['brak_email_pobranie']:.1%}, przy innych metodach {d['mar_email']['brak_email_inne']:.1%}.",
          f"- Nowa kolumna POS `kanal` od {d['pos_nowa_kolumna']['od']}.",
          "- Zdublowane pliki: " + ", ".join(d["pos_duplikaty_plikow"]) + ".",
          f"- Zamówienia testowe: {d['zamowienia_testowe']['wszystkie']} (wrzesień 2026: {d['zamowienia_testowe']['wrzesien_2026']}); "
          f"reguła: {d['zamowienia_testowe']['regula']}.",
          "", "## Odejścia (projekt Sygnały)", ""]
    c = k["odejscia"]
    h = c["model_uczciwy"]
    L += [f"- Migawka {c['migawka_testowa']}: {c['populacja']} biur, {c['odejscia_90d']} odejść "
          f"({c['typy']['wypowiedzenie']} wypowiedzeń, {c['typy']['brak_odnowienia']} braków odnowienia).",
          f"- Uczciwy model (regresja logistyczna na cechach znanych w t0, migawki 2024-04…2025-07, kalibracja Platta na 2025-10 i 2026-01): "
          f"AUC {h['auc_test']:.3f}; próg 0,5 → {h['thr_0_5_n']} biur (TP {h['thr_0_5_tp']}); top 60 → TP {h['top60_tp']}; "
          f"próg 0,175 → {h['thr_0_175_n']} biur (TP {h['thr_0_175_tp']}).",
          f"- Reguła AM (do końca umowy < 90 dni i trend 30/90 ≤ 0,7): AUC {h['am_rule_auc']:.3f} "
          f"({h['am_rule_n']} biur, TP {h['am_rule_tp']}).",
          f"- Model agencji: AUC {c['model_agencji']['auc_agency_test']:.3f} (migawka testowa), "
          f"{c['model_agencji']['auc_agency_random_split']:.3f} (losowy podział).",
          "- Przecieki: " + "; ".join(f"`{a}` — {b}" for a, b in c["przecieki_agencji"].items()) + ".",
          "", "## Dryf i wizyty (projekt Decyzja)", ""]
    dd = k["decyzja"]
    L += [f"- Firmware {dd['firmware']['wdrozenie'][0]}–{dd['firmware']['wdrozenie'][1]}: {dd['firmware']['opis']}; "
          f"PSI zaparzenia_30d = {dd['firmware']['psi']['psi_zaparzenia_30d']:.3f}.",
          f"- Wizyty retencyjne: średni efekt {dd['wizyty_retencyjne']['sredni_efekt_wzgledny']:.1%} "
          f"({dd['wizyty_retencyjne']['definicja_efektu']}).",
          f"- NPS (MNAR): odejścia bez odpowiedzi {dd['nps_mnar']['churn_no_response']:.3f} vs z odpowiedzią "
          f"{dd['nps_mnar']['churn_response']:.3f} (×{dd['nps_mnar']['ratio']:.2f}).", "",
          "| Grupa | udział biur | mnożnik hazardu po wizycie | wizyty |", "|---|---|---|---|"]
    for g, v in dd["wizyty_retencyjne"]["grupy"].items():
        L.append(f"| {g} | {v['udzial_biur']:.1%} | {v['mnoznik_hazardu_po_wizycie']} | {v['wizyty']} |")
    L += ["", "Grupa każdego biura: `decyzja.wizyty_retencyjne.grupa_biura` w pliku JSON.", ""]
    return "\n".join(L)
