"""Powody ryzyka biura prostym językiem: które cechy najbardziej podnoszą jego p, np. „zaparzenia −45% w ostatnim
miesiącu” albo „3 awarie w 60 dni”.

Liczymy tylko przez kontrakt ChurnModel (predict_proba i lista cech), więc działa dla każdej wersji z current.yaml.
Dla każdej cechy biura podstawiamy typową wartość dzisiejszych biur (mediana, dla cech tekstowych najczęstsza
wartość; pustą wartość też zastępujemy) i patrzymy, o ile spada p. Powody to cechy z największym spadkiem, co
najmniej MIN_WPLYW. To przybliżenie: wpływ liczymy osobno dla każdej cechy, a cechy powiązane (zaparzenia i ich
trend) dzielą się wpływem.

Pomijamy am_id: opiekun nie jest cechą biura, a na liście opiekuna „powód: opiekun” niczego mu nie mówi.
"""

import math

import pandas as pd

from api.ai.churn_model.base import ChurnModel

POMIJANE = {"am_id"}
LICZBA_POWODOW = 3
MIN_WPLYW = 0.005  # 0,5 pp: mniejszy wpływ to szum, a nie powód do rozmowy z biurem
MINUS = "−"


def _liczba(n: int) -> str:
    """1 250: odstęp co tysiąc."""
    return f"{n:,}".replace(",", " ")


def _odmiana(n: int, jeden: str, kilka: str, wiele: str) -> str:
    """1 awaria, 2–4 awarie, 5+ awarii (też 12–14)."""
    slowo = jeden if n == 1 else kilka if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else wiele
    return f"{_liczba(n)} {slowo}"


def _pusta(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NA


def _trend(v) -> str:
    if _pusta(v):
        return "brak zaparzeń w poprzednim miesiącu"
    zmiana = round((float(v) - 1) * 100)
    return f"zaparzenia {MINUS if zmiana < 0 else '+'}{abs(zmiana)}% w ostatnim miesiącu"


def _platnosci(v) -> str:
    if _pusta(v):
        return "brak płatności w ostatnich 90 dniach"
    dni = round(float(v))
    if dni == 0:
        return "płaci w terminie"
    kiedy = "po terminie" if dni > 0 else "przed terminem"
    return f"płaci średnio {_odmiana(abs(dni), 'dzień', 'dni', 'dni')} {kiedy}"


def _zaparzenia(v, typowa=None) -> str:
    """Liczba kaw sama nic nie mówi (zależy od wielkości biura), więc obok wartość typowego biura."""
    n = round(float(v))
    if n == 0:
        return "brak zaparzeń w ostatnich 30 dniach"
    tekst = f"{_odmiana(n, 'zaparzenie', 'zaparzenia', 'zaparzeń')} w 30 dni"
    return tekst if typowa is None else f"{tekst} (typowo {_liczba(round(float(typowa)))})"


def _kontakty(v) -> str:
    n = round(float(v))
    if n == 0:
        return "brak kontaktu z opiekunem od 90 dni"
    return f"{_odmiana(n, 'kontakt', 'kontakty', 'kontaktów')} z opiekunem w 90 dni"


OPISY = {
    "trend_zaparzen": _trend,
    "zaparzenia_30d": _zaparzenia,
    "bledy_60d": lambda v: f"{_odmiana(round(float(v)), 'błąd', 'błędy', 'błędów')} ekspresu w 60 dni",
    "awarie_60d": lambda v: f"{_odmiana(round(float(v)), 'awaria', 'awarie', 'awarii')} w 60 dni",
    "dni_od_ostatniego_zamowienia": lambda v: (
        "brak zamówień kawy" if _pusta(v) else f"{_odmiana(round(float(v)), 'dzień', 'dni', 'dni')} od ostatniego "
        "zamówienia kawy"
    ),
    "sr_opoznienie_platnosci": _platnosci,
    "kontakty_am_90d": _kontakty,
    "nps_ostatni": lambda v: "brak odpowiedzi w ankiecie NPS" if _pusta(v) else f"NPS {round(float(v))}/10",
    "dni_do_rocznicy": lambda v: f"odnowienie umowy za {_odmiana(round(float(v)), 'dzień', 'dni', 'dni')}",
    "staz_mies": lambda v: f"klient od {round(float(v))} mies.",
    "cena_mies": lambda v: (
        "umowa bez zmian od ponad roku" if _pusta(v) else f"abonament {_liczba(round(float(v)))} zł/mies."
    ),
    "liczba_pracownikow": lambda v: _odmiana(round(float(v)), "pracownik", "pracowników", "pracowników"),
    "plan": lambda v: f"pakiet {v}",
    "branza": lambda v: f"branża: {v}",
    "miasto": lambda v: f"lokalizacja: {v}",
}


# cechy, przy których opis pokazuje też wartość typowego biura
Z_TYPOWA = {"zaparzenia_30d"}


def opis(cecha: str, wartosc, typowa=None) -> str:
    """Wartość cechy prostym językiem; cecha spoza OPISY (nowa w modelu) jako „nazwa: wartość”."""
    if cecha not in OPISY:
        return f"{cecha}: {wartosc}"
    return OPISY[cecha](wartosc, typowa) if cecha in Z_TYPOWA else OPISY[cecha](wartosc)


def typowe(populacja: pd.DataFrame, cechy: list[str]) -> dict:
    """Typowa wartość każdej cechy: mediana liczb, najczęstsza wartość tekstu."""
    return {
        c: populacja[c].median() if pd.api.types.is_numeric_dtype(populacja[c]) else populacja[c].mode().iloc[0]
        for c in cechy
    }


def wplywy(model: ChurnModel, biura: pd.DataFrame, populacja: pd.DataFrame) -> pd.DataFrame:
    """O ile spada p biura, gdy jedną cechę zastąpimy typową wartością: wiersz = biuro, kolumna = cecha modelu."""
    cechy = [c for c in model.cechy if c not in POMIJANE]
    ref = typowe(populacja, cechy)
    p = model.predict_proba(biura).to_numpy()
    bez_cechy = pd.concat([biura.assign(**{c: ref[c]}) for c in cechy], ignore_index=True)
    p_bez = model.predict_proba(bez_cechy).to_numpy().reshape(len(cechy), len(biura)).T
    return pd.DataFrame(p[:, None] - p_bez, index=biura.index, columns=cechy)


def powody(model: ChurnModel, biura: pd.DataFrame, populacja: pd.DataFrame) -> list[list[str]]:
    """Do LICZBA_POWODOW opisów na biuro (w kolejności wierszy biura), od cechy, która najbardziej podnosi p."""
    if biura.empty:
        return []
    w = wplywy(model, biura, populacja)
    ref = typowe(populacja, list(w.columns))
    wynik = []
    for i, wiersz in w.iterrows():
        najwieksze = wiersz[wiersz >= MIN_WPLYW].sort_values(ascending=False, kind="stable").head(LICZBA_POWODOW)
        wynik.append([opis(c, biura.at[i, c], ref[c]) for c in najwieksze.index])
    return wynik
