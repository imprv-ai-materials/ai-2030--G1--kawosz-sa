"""Katalogi produktów: kartoteka ERP, produkty POS i e-commerce.

Te same produkty detaliczne występują w trzech systemach pod różnymi kodami
(usterka „trzy różne kody tego samego produktu”).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ORIGINS = ["Brazylia Santos", "Brazylia Cerrado", "Kolumbia Huila", "Kolumbia Supremo",
           "Etiopia Yirgacheffe", "Etiopia Sidamo", "Etiopia Guji", "Kenia AA", "Kenia Nyeri",
           "Gwatemala Antigua", "Honduras Marcala", "Kostaryka Tarrazu", "Salwador Santa Ana",
           "Nikaragua Jinotega", "Peru Cajamarca", "Rwanda Huye", "Burundi Kayanza",
           "Tanzania Kilimandżaro", "Indie Monsooned Malabar", "Sumatra Mandheling",
           "Jawa", "Papua Nowa Gwinea", "Meksyk Chiapas", "Uganda Bugisu"]

# Produkty detaliczne wspólne dla trzech systemów:
# (nazwa ERP, nazwa POS, nazwa e-com, cena brutto PLN, waga popularności)
SHARED_RETAIL = [
    ("KAWA ZIARN. ESPRESSO BLEND 1KG", "Espresso Blend 1kg", "Kawosz Espresso Blend – kawa ziarnista 1000 g", 169.0, 3.0),
    ("KAWA ZIARN. ESPRESSO BLEND 250G", "Espresso Blend 250g", "Kawosz Espresso Blend – kawa ziarnista 250 g", 52.0, 6.0),
    ("KAWA ZIARN. POZNAŃSKA 250G", "Poznańska 250g", "Mieszanka Poznańska – kawa ziarnista 250 g", 49.0, 5.0),
    ("KAWA ZIARN. ETIOPIA YIRG. 250G", "Etiopia Yirgacheffe 250g", "Etiopia Yirgacheffe – kawa ziarnista 250 g", 64.0, 4.0),
    ("KAWA ZIARN. KOLUMBIA HUILA 250G", "Kolumbia Huila 250g", "Kolumbia Huila – kawa ziarnista 250 g", 58.0, 4.0),
    ("KAWA ZIARN. BRAZYLIA SANTOS 1KG", "Brazylia Santos 1kg", "Brazylia Santos – kawa ziarnista 1000 g", 149.0, 2.0),
    ("KAWA ZIARN. KENIA AA 250G", "Kenia AA 250g", "Kenia AA – kawa ziarnista 250 g", 69.0, 2.5),
    ("KAWA ZIARN. DECAF 250G", "Decaf 250g", "Kawosz Decaf (bezkofeinowa) – kawa ziarnista 250 g", 55.0, 1.5),
    ("DRIP BAG KAWOSZ 5 SZT", "Drip bag 5 szt.", "Drip bagi Kawosz – zestaw 5 szt.", 35.0, 3.0),
    ("DRIPPER V60 CERAMICZNY", "Dripper V60", "Dripper V60 ceramiczny, rozmiar 02", 119.0, 0.8),
    ("KUBEK TERMICZNY KAWOSZ 350ML", "Kubek termiczny", "Kubek termiczny Kawosz 350 ml", 89.0, 1.2),
    ("FILTRY PAPIEROWE V60 100 SZT", "Filtry V60", "Filtry papierowe V60, 100 szt.", 29.0, 1.0),
    ("MLYNEK RECZNY KAWOSZ HAND", "Młynek ręczny", "Młynek ręczny Kawosz Hand Grinder", 349.0, 0.25),
]

PLAN_NAMES = {"S": "Abonament Kawosz dla Biur – plan S", "M": "Abonament Kawosz dla Biur – plan M",
              "L": "Abonament Kawosz dla Biur – plan L", "XL": "Abonament Kawosz dla Biur – plan XL"}

MACHINE_MODELS = ["Kawosz Mini 1", "Kawosz Office 2", "Kawosz Office 2 Plus", "Kawosz Duo",
                  "Kawosz Pro X8", "Kawosz Pro X12", "Jura WE8", "Jura X8", "Franke A400",
                  "Franke A600", "WMF 1300 S", "Schaerer Coffee Soul"]
MODEL_PRICE_NET = [3900, 5400, 6200, 7400, 8900, 10900, 6900, 12900, 14900, 19900, 16900, 21900]


def build_erp_kartoteka(rng: np.random.Generator) -> tuple[pd.DataFrame, dict]:
    rows: list[tuple[str, str, str, float]] = []  # (indeks, nazwa, kategoria, cena netto)
    counters: dict[str, int] = {}

    def add(group: str, name: str, cat: str, price: float) -> str:
        counters[group] = counters.get(group, 0) + 1
        idx = f"{group}.{counters[group]:04d}"
        rows.append((idx, name, cat, round(price, 2)))
        return idx

    house, house6 = {}, {}
    for blend, price in [("BIURO CLASSIC", 78), ("BIURO CREMA", 84), ("BIURO STRONG", 81),
                         ("BIURO DECAF", 92), ("BIURO ORGANIC", 98)]:
        house[blend] = add("10.01", f"KAWA ZIARN. {blend} 1KG", "Kawa ziarnista", price)
        house6[blend] = add("10.01", f"KAWA ZIARN. {blend} 6KG (KARTON)", "Kawa ziarnista", price * 5.7)
    for o in ORIGINS:
        p = rng.uniform(95, 150)
        add("10.02", f"KAWA ZIARN. {o.upper()} 1KG", "Kawa ziarnista", p)
        add("10.02", f"KAWA ZIARN. {o.upper()} 250G", "Kawa ziarnista", p * 0.3)
    for o in ORIGINS[:14]:
        add("10.03", f"KAWA MIEL. {o.upper()} 250G", "Kawa mielona", rng.uniform(30, 45))
    shared_idx = []
    for erp_name, _, _, gross, _ in SHARED_RETAIL:
        shared_idx.append(add("10.09", erp_name, "Detal", gross / 1.23 * 0.62))
    consumables = {}
    for n, p in [("MLEKO UHT 3,2% 1L", 3.9), ("MLEKO UHT 2% 1L", 3.6), ("NAPÓJ OWSIANY BARISTA 1L", 9.4),
                 ("NAPÓJ SOJOWY BARISTA 1L", 9.1), ("MLEKO BEZ LAKTOZY 1L", 5.2),
                 ("ŚMIETANKA PORCJOWANA 10 SZT", 2.9), ("CUKIER SASZETKI 1000 SZT", 39.0),
                 ("CUKIER TRZCINOWY SASZETKI 500 SZT", 34.0), ("SŁODZIK TABLETKI 1200 SZT", 24.0),
                 ("MIESZADEŁKA DREWNIANE 1000 SZT", 19.0), ("KAKAO W PROSZKU 1KG", 38.0),
                 ("CZEKOLADA DO PICIA 1KG", 44.0)]:
        consumables[n] = add("20.01", n, "Mleko i dodatki", p)
    for flavor in ["WANILIA", "KARMEL", "ORZECH LASKOWY", "PIERNIK", "KOKOS", "CYNAMON", "MIĘTA",
                   "SŁONY KARMEL", "MIGDAŁ", "IRISH", "LAWENDA", "DYNIA", "TOFFEE", "MALINA",
                   "CZEKOLADA", "PISTACJA", "GRUSZKA", "WIŚNIA", "AMARETTO", "CHAI"]:
        add("20.02", f"SYROP {flavor} 0,7L", "Syropy", rng.uniform(26, 34))
    for t in ["EARL GREY", "ENGLISH BREAKFAST", "ZIELONA SENCHA", "MIĘTA", "RUMIANEK", "OWOCOWA",
              "ROOIBOS", "BIAŁA", "YERBA MATE", "CHAI MASALA", "MATCHA CEREMONIALNA 100G",
              "ZIELONA JAŚMINOWA", "CZARNA ASSAM", "DARJEELING", "MELISA", "IMBIR-CYTRYNA",
              "HIBISKUS", "LIPA", "POKRZYWA", "OOLONG"]:
        add("20.03", f"HERBATA {t} (100 SZT)" if "100G" not in t else f"HERBATA {t}", "Herbata",
            rng.uniform(22, 60))
    cups = {}
    for n in ["KUBEK PAPIEROWY 250ML (1000 SZT)", "KUBEK PAPIEROWY 350ML (1000 SZT)",
              "KUBEK PAPIEROWY 450ML (1000 SZT)", "POKRYWKA 80MM (1000 SZT)", "POKRYWKA 90MM (1000 SZT)",
              "KUBEK PORCELANOWY KAWOSZ 300ML", "FILIŻANKA ESPRESSO KAWOSZ", "FILIŻANKA CAPPUCCINO KAWOSZ",
              "SZKLANKA LATTE 300ML", "SERWETKI KAWOSZ (2000 SZT)", "TACKA DO KUBKÓW (300 SZT)",
              "TORBA PAPIEROWA (500 SZT)", "KUBEK WIELORAZOWY KAWOSZ", "MIESZADŁO METALOWE",
              "PODSTAWKA KORKOWA (50 SZT)", "SŁOMKI PAPIEROWE (500 SZT)", "OPAKOWANIE PREZENTOWE",
              "PUSZKA NA KAWĘ KAWOSZ", "DZBANEK DO MLEKA 600ML", "DZBANEK DO MLEKA 350ML",
              "TERMOS POMPKOWY 2,2L", "TERMOS POMPKOWY 3L", "POJEMNIK NA FUSY", "TACA SERWISOWA",
              "KUBEK PAPIEROWY 180ML (1000 SZT)"]:
        cups[n] = add("30.01", n, "Kubki i opakowania", rng.uniform(15, 140))
    for n in ["TAMPER 58MM", "MATA DO TAMPOWANIA", "PITCHER 0,6L", "WAGA BARISTYCZNA", "TERMOMETR",
              "SZCZOTKA DO GRUPY", "CZAJNIK GOOSENECK", "CHEMEX 6 FILIŻANEK", "AEROPRESS", "FRENCH PRESS 1L",
              "MOKA 6 FILIŻANEK", "DRIPPER KALITA WAVE", "FILTRY CHEMEX 100 SZT", "FILTRY KALITA 100 SZT",
              "MŁYNEK ELEKTRYCZNY", "SPIENIACZ DO MLEKA", "KNOCKBOX", "RĘCZNIK BARISTY",
              "DOZOWNIK SYROPU", "STOJAK NA KUBKI", "PUDEŁKO NA KAPSUŁKI", "ŁYŻECZKA DO KAWY 12 SZT",
              "ZESTAW CUPPINGOWY", "SITKO DO SPIENIANIA", "MIARKA DO KAWY", "SERWER SZKLANY 600ML",
              "COLD BREW DZBANEK 1L", "LEJEK DOZUJĄCY", "PĘDZELEK DO MŁYNKA", "PODKŁADKA SILIKONOWA"]:
        add("40.01", n, "Akcesoria baristyczne", rng.uniform(19, 450))
    machine_idx = []
    for m, p in zip(MACHINE_MODELS, MODEL_PRICE_NET):
        machine_idx.append(add("50.01", f"EKSPRES {m.upper()}", "Ekspresy", p))
    for m in MACHINE_MODELS:
        for part in ["USZCZELKA GRUPY", "GRUPA ZAPARZAJĄCA", "ŻARNA MŁYNKA", "POMPA", "ZAWÓR",
                     "BOJLER", "CZUJNIK TEMPERATURY", "PŁYTA STEROWNIKA", "DYSZA PARY", "FILTR WODY"]:
            add("50.02", f"{part} – {m.upper()}", "Części zamienne", rng.uniform(25, 900))
    cleaning = {}
    for n in ["TABLETKI CZYSZCZĄCE (100 SZT)", "ODKAMIENIACZ 1L", "ŚRODEK DO SPIENIACZA 1L",
              "FILTR WODY UNIWERSALNY", "PROSZEK CZYSZCZĄCY 900G", "TABLETKI ODKAMIENIAJĄCE (36 SZT)",
              "ŚCIERECZKI MIKROFIBRA (10 SZT)", "SZCZOTKI DO DYSZ (5 SZT)", "ŻEL CZYSZCZĄCY 1L",
              "TESTER TWARDOŚCI WODY", "PASKI DO pH", "PŁYN DO MLEKA 0,5L", "ZESTAW SERWISOWY MINI",
              "ZESTAW SERWISOWY PRO", "ŚRODEK DO MŁYNKA 430G"]:
        cleaning[n] = add("60.01", n, "Środki czystości", rng.uniform(19, 180))
    services = {}
    for n, p in [("SERWIS GWARANCYJNY", 0.0), ("SERWIS POGWARANCYJNY – ROBOCIZNA", 180.0),
                 ("DOJAZD SERWISU", 90.0), ("INSTALACJA EKSPRESU", 250.0), ("PRZEGLĄD OKRESOWY", 220.0),
                 ("SZKOLENIE BARISTYCZNE DLA BIURA", 900.0), ("DEINSTALACJA I ODBIÓR EKSPRESU", 0.0),
                 ("WYMIANA EKSPRESU", 0.0), ("WYNAJEM EKSPRESU DODATKOWEGO", 290.0),
                 ("OPŁATA ZA OPÓŹNIONY ZWROT", 150.0), ("DEGUSTACJA W BIURZE", 600.0), ("TRANSPORT", 60.0)]:
        services[n] = add("70.01", n, "Usługi", p)
    plans = {}
    for code, name in PLAN_NAMES.items():
        plans[code] = add("80.01", name.upper(), "Abonamenty", 0.0)

    # uzupełnienie do ~400 pozycji wariantami opakowań
    i = 0
    while len(rows) < 398:
        o = ORIGINS[i % len(ORIGINS)]
        add("10.04", f"KAWA ZIARN. {o.upper()} 500G (WYPRZEDANE)", "Kawa ziarnista", rng.uniform(55, 80))
        i += 1

    df = pd.DataFrame(rows, columns=["indeks", "nazwa", "kategoria", "cena_netto"])
    # usterka: 6% indeksów bez kategorii
    n_missing = round(0.06 * len(df))
    miss = rng.choice(len(df), size=n_missing, replace=False)
    df.loc[miss, "kategoria"] = ""
    refs = {"house": house, "house6": house6, "shared": shared_idx, "consumables": consumables, "cups": cups,
            "cleaning": cleaning, "services": services, "plans": plans, "machines": machine_idx,
            "missing_category": df.loc[miss, "indeks"].tolist()}
    return df, refs


def build_pos_products() -> pd.DataFrame:
    """Katalog POS: kod, nazwa, kategoria, cena brutto, VAT, waga popularności."""
    items = [
        # napoje (8%)
        ("Espresso", "napoje", 10.0, 8, 6.0), ("Doppio", "napoje", 13.0, 8, 3.0),
        ("Americano", "napoje", 14.0, 8, 7.0), ("Cortado", "napoje", 15.0, 8, 2.5),
        ("Cappuccino", "napoje", 17.0, 8, 10.0), ("Flat white", "napoje", 19.0, 8, 8.0),
        ("Latte", "napoje", 19.0, 8, 9.0), ("Latte smakowe", "napoje", 21.0, 8, 4.0),
        ("Kawa przelewowa V60", "napoje", 21.0, 8, 3.0), ("Chemex (2 os.)", "napoje", 34.0, 8, 1.0),
        ("Cold brew", "napoje", 19.0, 8, 3.0), ("Espresso tonic", "napoje", 22.0, 8, 2.0),
        ("Matcha latte", "napoje", 23.0, 8, 2.5), ("Chai latte", "napoje", 21.0, 8, 2.0),
        ("Herbata", "napoje", 13.0, 8, 3.0), ("Czekolada na gorąco", "napoje", 19.0, 8, 2.0),
        ("Lemoniada", "napoje", 17.0, 8, 2.0), ("Woda", "napoje", 8.0, 8, 2.0),
        ("Sok wyciskany", "napoje", 18.0, 8, 1.2),
        # jedzenie (8%)
        ("Croissant", "jedzenie", 10.0, 8, 5.0), ("Croissant migdałowy", "jedzenie", 15.0, 8, 2.5),
        ("Cynamonka", "jedzenie", 14.0, 8, 3.5), ("Sernik", "jedzenie", 19.0, 8, 3.0),
        ("Brownie", "jedzenie", 15.0, 8, 2.5), ("Ciasto dnia", "jedzenie", 18.0, 8, 3.0),
        ("Kanapka", "jedzenie", 26.0, 8, 3.5), ("Bajgiel", "jedzenie", 24.0, 8, 2.0),
        ("Tost", "jedzenie", 22.0, 8, 2.0), ("Owsianka", "jedzenie", 21.0, 8, 1.5),
        ("Sałatka", "jedzenie", 34.0, 8, 1.2), ("Quiche", "jedzenie", 29.0, 8, 1.2),
        ("Ciastko owsiane", "jedzenie", 9.0, 8, 2.0), ("Tarta sezonowa", "jedzenie", 22.0, 8, 1.5),
    ]
    rows = []
    for i, (n, cat, p, vat, w) in enumerate(items, start=1):
        rows.append((f"P{100 + i:04d}", n, cat, p, vat, w))
    for j, (_, pos_name, _, gross, w) in enumerate(SHARED_RETAIL, start=1):
        rows.append((f"P{300 + j:04d}", pos_name, "detal", gross, 23, w))
    rows.append(("P0999", "Kawa ziarnista na wagę", "detal", 0.0, 23, 0.0))  # cena ręczna
    return pd.DataFrame(rows, columns=["kod_produktu", "nazwa", "kategoria", "cena_brutto", "vat", "waga"])


def build_ecom_products(rng: np.random.Generator) -> pd.DataFrame:
    rows = []

    def sku_of(name: str, n: int) -> str:
        base = "".join(ch for ch in name.upper() if ch.isalnum())[:8]
        return f"KW-{base}-{n:03d}"

    n = 0
    for _, _, ecom_name, gross, w in SHARED_RETAIL:
        n += 1
        rows.append((sku_of(ecom_name, n), ecom_name, gross, w * 1.6))
    for o in ORIGINS:
        n += 1
        p = float(np.round(rng.uniform(52, 76)))
        rows.append((sku_of(o, n), f"{o} – kawa ziarnista 250 g", p, 1.0))
    for o in ORIGINS[:8]:
        n += 1
        p = float(np.round(rng.uniform(149, 219)))
        rows.append((sku_of(o, n), f"{o} – kawa ziarnista 1000 g", p, 0.6))
    for name, p, w in [("Zestaw prezentowy Degustacja 3×100 g", 129.0, 1.0),
                       ("Zestaw prezentowy Barista Home", 249.0, 0.4),
                       ("Waga baristyczna z timerem", 159.0, 0.3),
                       ("Czajnik gooseneck 0,8 l", 249.0, 0.25),
                       ("Młynek elektryczny Kawosz E1", 899.0, 0.08),
                       ("Chemex 6 filiżanek", 229.0, 0.2), ("AeroPress Original", 179.0, 0.3),
                       ("Filtry Chemex 100 szt.", 49.0, 0.4), ("Kubek ceramiczny Kawosz", 59.0, 0.6),
                       ("Syrop waniliowy 0,7 l", 39.0, 0.4), ("Matcha ceremonialna 30 g", 69.0, 0.4),
                       ("Herbata Earl Grey sypana 100 g", 34.0, 0.3)]:
        n += 1
        rows.append((sku_of(name, n), name, p, w))
    df = pd.DataFrame(rows, columns=["sku", "nazwa", "cena_brutto_pln", "waga"])
    df.loc[df.cena_brutto_pln > 100, "waga"] *= 0.5  # akcesoria i duże opakowania rzadziej
    return df


def shared_mapping(kartoteka_refs: dict, pos: pd.DataFrame, ecom: pd.DataFrame) -> pd.DataFrame:
    pos_codes = pos[pos.kategoria == "detal"].kod_produktu.tolist()[: len(SHARED_RETAIL)]
    ecom_codes = ecom.sku.tolist()[: len(SHARED_RETAIL)]
    return pd.DataFrame({
        "produkt": [s[1] for s in SHARED_RETAIL],
        "indeks_erp": kartoteka_refs["shared"],
        "kod_pos": pos_codes,
        "sku_ecom": ecom_codes,
    })
