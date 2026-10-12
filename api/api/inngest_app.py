"""Nocne zadanie Inngest: o 3:00 czasu polskiego wczytuje dostawę z poprzedniego dnia, sprawdza reguły jakości,
publikuje dobre wsady, odkłada złe do kwarantanny, przelicza most przychodu za miesiąc tego dnia i odświeża aktualne
cechy modelu churnu.

Każdy krok to osobny `step.run`, więc po awarii Inngest ponawia tylko krok, który padł; wyniki wcześniejszych
kroków ma zapamiętane. Kroki (api/api/data_platform/noc.py) są idempotentne, więc ponowienie kroku, który
zdążył zapisać dane, i drugi przebieg tej samej nocy dają te same liczby.

    wczytaj-pos, wczytaj-erp, wczytaj-ecom          pliki z _dostawy/D/{źródło}/ → schemat roboczy wsad_D
    sprawdz-pos, sprawdz-erp, sprawdz-ecom          reguły jakości źródła za dzień D
    wycen-pos, wycen-erp, wycen-ecom                ile przychodu netto niesie wsad i ile zawyżyłyby go duplikaty
    publikuj-{źródło} albo kwarantanna-{źródło}     zależnie od tego, czy złamano regułę blokującą
    most                                            most przychodu za miesiąc dnia D → most_przychodu
    cechy-aktualne                                  cechy churnu na początek dnia D + 1 → cechy_aktualne
    sprzatanie                                      usuwa schemat roboczy

Ręczne uruchomienie dla wybranego dnia (np. po poprawionej dostawie): zdarzenie `kawosz/noc.uruchom`
z `{"dzien": "2026-09-30"}`, np. `pypyr noc dzien=2026-09-30` (wysyła je do serwera Inngest z INNGEST_DEV).
Bez serwera Inngest, te same kroki po kolei w tym procesie:

    PYTHONPATH=api poetry run python -m api.inngest_app --dzien 2026-09-30

Cotygodniowe zadanie: w poniedziałek o 5:00 (po nocy) sprawdza, czy rozkład cech churnu na początek tego dnia
(t0) nie odjechał od zbioru uczącego modelu (PSI, api/api/ai/churn_model/psi.py):

    psi                                             PSI każdej cechy w t0 → psi_cech, PSI > 0,25 → alerty_psi
    wykresy-psi                                     rozkład przed i po dla cech z alertem → docs/img/psi/

Ręcznie: zdarzenie `kawosz/psi.uruchom` z `{"t0": "2026-09-28"}`. Wstecz, dla każdego poniedziałku z przedziału,
bez serwera Inngest:

    PYTHONPATH=api poetry run python -m api.inngest_app --psi-od 2026-01-01 [--psi-do 2026-10-01]
"""

import argparse
import json
import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import inngest

from api.adapters.duckdb_conn import PROJECT_ROOT, connect
from api.ai.churn_model import psi as psi_cech
from api.ai.features import build as cechy_churnu
from api.contexts_boundaries.revenue_bc.most import most as most_przychodu
from api.contexts_boundaries.revenue_bc.przychod import definicja
from api.data_platform import noc

STREFA = ZoneInfo("Europe/Warsaw")
CRON = "TZ=Europe/Warsaw 0 3 * * *"
ZDARZENIE = "kawosz/noc.uruchom"
CRON_PSI = "TZ=Europe/Warsaw 0 5 * * 1"
ZDARZENIE_PSI = "kawosz/psi.uruchom"
# DuckDB ma jednego piszącego: kroki wszystkich funkcji z tym kluczem (noc i PSI) wykonują się po jednym.
JEDEN_PISZACY = inngest.Concurrency(limit=1, key='"kawosz-duckdb"', scope="env")

client = inngest.Inngest(app_id="kawosz", logger=logging.getLogger("uvicorn"))


def dzien_nocy(event: inngest.Event) -> date:
    """Dzień D, za który liczymy noc: `dzien` ze zdarzenia ręcznego, a z crona dzień przed chwilą uruchomienia
    (czas polski). Liczony ze zdarzenia, a nie z zegara, więc powtórka funkcji po awarii bierze ten sam dzień."""
    if event.data and event.data.get("dzien"):
        return date.fromisoformat(str(event.data["dzien"]))
    return (datetime.fromtimestamp(event.ts / 1000, STREFA) - timedelta(days=1)).date()


def wycen(ust: noc.Ustawienia, zrodlo: str, dzien: date) -> dict:
    """Przychód netto według definicji, który niesie sam wsad (ujęty w miesiącu dnia D), i zawyżenie: o ile
    więcej wyszłoby, gdyby zdublowane dokumenty (np. kopia pliku z kasy) policzyć dwa razy.

    Dla wsadu w kwarantannie to przychód, którego nie ma w raportach, i zawyżenie, które nie trafiło do raportów.
    Wsadu z błędem, przy którym definicja nie umie policzyć kwoty (np. paragon bez pozycji), nie wyceniamy: krok
    zwraca powód zamiast kwoty, żeby noc szła dalej.
    """
    miesiac = dzien.replace(day=1)
    con = connect(read_only=True, db_path=ust.baza)
    try:
        noc.widok_wsadu(con, zrodlo, dzien)
        try:
            netto = definicja.suma(con, miesiac, definicja.KROKI, bez_duplikatow=True)["kwota_pln"].sum()
            z_duplikatami = definicja.suma(con, miesiac, definicja.KROKI, bez_duplikatow=False)["kwota_pln"].sum()
        except ValueError as e:
            return {"przychod_netto": None, "zawyzenie": None, "uwaga": str(e).splitlines()[0]}
    finally:
        con.close()
    netto = round(float(netto), 2)
    return {"przychod_netto": netto, "zawyzenie": round(float(z_duplikatami) - netto, 2), "uwaga": None}


def przelicz_most(ust: noc.Ustawienia, dzien: date) -> dict:
    """Most przychodu za miesiąc dnia D, zapisany w most_przychodu w miejsce poprzedniego zapisu miesiąca."""
    miesiac = dzien.replace(day=1)
    con = connect(read_only=False, db_path=ust.baza)
    try:
        tabela = most_przychodu.most(con, miesiac)
        most_przychodu.zapisz(con, miesiac, tabela)
    finally:
        con.close()
    kwoty = dict(zip(tabela["krok"], tabela["kwota_pln"]))
    return {
        "miesiac": f"{miesiac:%Y-%m}",
        "surowa_suma_bi": float(kwoty["0. Surowa suma BI"]),
        "przychod_netto": float(kwoty["Przychód netto"]),
        "niewyjasniona_reszta": float(kwoty["Niewyjaśniona reszta"]),
    }


def odswiez_cechy(ust: noc.Ustawienia, dzien: date) -> dict:
    """Cechy churnu z ai/features/sql/ (te same pliki co w treningu) → cechy_aktualne w miejsce poprzedniego stanu.

    t0 = D + 1: noc dla D działa o 3:00 w D + 1, a cechy to stan na początek dnia t0, tak jak w cechy_treningowe.
    Wsad z dnia D jest już opublikowany, ale cechy go nie widzą: w t0 znane są dane ERP, CRM i helpdesku do t0 − 2
    (opóźnienie D+1), czyli tak jak w treningu."""
    t0 = dzien + timedelta(days=1)
    con = connect(read_only=False, db_path=ust.baza)
    try:
        wiersze = cechy_churnu.zbuduj_cechy_aktualne(t0, con)
    finally:
        con.close()
    return {"t0": str(t0), "wiersze": wiersze}


Krok = Callable[..., object]


def _od_razu(_nazwa: str, funkcja: Callable, *argumenty):
    return funkcja(*argumenty)


def przebieg(dzien: date, ust: noc.Ustawienia, krok: Krok = _od_razu) -> dict:
    """Cała noc dla dnia D. `krok(nazwa, funkcja, *argumenty)` to `ctx.step.run` w Inngest, a poza nim zwykłe
    wywołanie, więc obie drogi wykonują ten sam kod w tej samej kolejności."""
    wczytane = {z: krok(f"wczytaj-{z}", noc.wczytaj, ust, z, dzien) for z in noc.ZRODLA}
    sprawdzone = {z: krok(f"sprawdz-{z}", noc.sprawdz, ust, z, dzien) for z in noc.ZRODLA}
    wycenione = {z: krok(f"wycen-{z}", wycen, ust, z, dzien) for z in noc.ZRODLA}
    wsady = {}
    for z, wynik in sprawdzone.items():
        if wynik["blokujace"]:
            status, wiersze = "kwarantanna", krok(f"kwarantanna-{z}", noc.odloz, ust, z, dzien, wynik, wycenione[z])
        else:
            status, wiersze = "opublikowany", krok(f"publikuj-{z}", noc.opublikuj, ust, z, dzien, wynik, wycenione[z])
        wsady[z] = {"status": status, "wiersze": wiersze, "wycena": wycenione[z]} | {
            k: v for k, v in wynik.items() if k != "reguly"
        }
    most = krok("most", przelicz_most, ust, dzien)
    cechy = krok("cechy-aktualne", odswiez_cechy, ust, dzien)
    krok("sprzatanie", noc.sprzataj, ust, dzien)
    return {"dzien": str(dzien), "wczytane": wczytane, "wsady": wsady, "most": most, "cechy": cechy}


@client.create_function(
    fn_id="kawosz-noc",
    name="Kawosz: nocne ładowanie, reguły jakości, most przychodu i cechy churnu",
    trigger=[inngest.TriggerCron(cron=CRON), inngest.TriggerEvent(event=ZDARZENIE)],
    # DuckDB ma jednego piszącego: dwie noce naraz (cron i ręczne uruchomienie) czekają na siebie.
    concurrency=[inngest.Concurrency(limit=1), JEDEN_PISZACY],
    retries=3,
)
def kawosz_noc(ctx: inngest.ContextSync) -> dict:
    return przebieg(dzien_nocy(ctx.event), noc.Ustawienia.z_env(), ctx.step.run)


def tydzien_psi(event: inngest.Event) -> date:
    """t0 sprawdzania PSI: `t0` ze zdarzenia ręcznego, a z crona dzień uruchomienia (czas polski), czyli cechy na
    początek tego poniedziałku. Ze zdarzenia, a nie z zegara, więc powtórka po awarii bierze to samo t0."""
    if event.data and event.data.get("t0"):
        return date.fromisoformat(str(event.data["t0"]))
    return datetime.fromtimestamp(event.ts / 1000, STREFA).date()


def sprawdz_psi(ust: noc.Ustawienia, t0: date) -> dict:
    """PSI każdej cechy w t0 → psi_cech, alerty → alerty_psi. Zwraca PSI cech i rozkłady cech z alertem (dla
    kroku wykresy-psi). t0 po DZIS przerywa bez ponawiania: dane kończą się na eksporcie, więc okna cech byłyby
    częściowo puste, a PSI pokazałby dryf, którego nie ma."""
    if t0 > cechy_churnu.DZIS:
        raise inngest.NonRetriableError(f"t0 = {t0} jest po dniu dzisiejszym ({cechy_churnu.DZIS})")
    con = connect(read_only=False, db_path=ust.baza)
    try:
        wyniki = psi_cech.policz(con, t0)
        alerty = [w for w in wyniki if w["psi"] > psi_cech.PROG]
        wykresy = {w["cecha"]: _wzgledna(psi_cech.sciezka_wykresu(ust.wykresy_psi, t0, w["cecha"])) for w in alerty}
        psi_cech.zapisz(con, t0, wyniki, wykresy)
    finally:
        con.close()
    return {
        "t0": str(t0),
        "psi": {w["cecha"]: round(w["psi"], 4) for w in wyniki},
        "alerty": [w | {"wykres": wykresy[w["cecha"]]} for w in alerty],
    }


def narysuj_alerty(ust: noc.Ustawienia, wynik: dict) -> list[str]:
    """Wykres rozkładu przed i po dla każdej cechy z alertem; nadpisuje wykres z poprzedniego przebiegu tygodnia."""
    t0 = date.fromisoformat(wynik["t0"])
    for alert in wynik["alerty"]:
        psi_cech.narysuj(alert, t0, psi_cech.sciezka_wykresu(ust.wykresy_psi, t0, alert["cecha"]))
    return [alert["wykres"] for alert in wynik["alerty"]]


def _wzgledna(sciezka) -> str:
    """Ścieżka względem katalogu repozytorium (np. docs/img/psi/…), poza nim pełna."""
    return str(sciezka.relative_to(PROJECT_ROOT)) if sciezka.is_relative_to(PROJECT_ROOT) else str(sciezka)


def przebieg_psi(t0: date, ust: noc.Ustawienia, krok: Krok = _od_razu) -> dict:
    """Sprawdzanie PSI dla t0; `krok` jak w przebieg()."""
    wynik = krok("psi", sprawdz_psi, ust, t0)
    krok("wykresy-psi", narysuj_alerty, ust, wynik)
    return {"t0": wynik["t0"], "psi": wynik["psi"], "alerty": {a["cecha"]: a["wykres"] for a in wynik["alerty"]}}


@client.create_function(
    fn_id="kawosz-psi",
    name="Kawosz: tygodniowy PSI cech churnu względem treningu",
    trigger=[inngest.TriggerCron(cron=CRON_PSI), inngest.TriggerEvent(event=ZDARZENIE_PSI)],
    concurrency=[JEDEN_PISZACY],
    retries=3,
)
def kawosz_psi(ctx: inngest.ContextSync) -> dict:
    return przebieg_psi(tydzien_psi(ctx.event), noc.Ustawienia.z_env(), ctx.step.run)


FUNKCJE = [kawosz_noc, kawosz_psi]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    tryb = parser.add_mutually_exclusive_group(required=True)
    tryb.add_argument("--dzien", type=date.fromisoformat, help="noc: dzień dostawy RRRR-MM-DD")
    tryb.add_argument("--psi-od", type=date.fromisoformat, help="PSI dla każdego poniedziałku od tego dnia")
    parser.add_argument("--psi-do", type=date.fromisoformat, help="ostatni dzień dla --psi-od (domyślnie DZIS)")
    parser.add_argument(
        "--wyslij", action="store_true", help="wyślij zdarzenie do serwera Inngest zamiast liczyć noc w tym procesie"
    )
    args = parser.parse_args()
    if args.psi_od:
        ust = noc.Ustawienia.z_env()
        for t0 in psi_cech.poniedzialki(args.psi_od, args.psi_do or cechy_churnu.DZIS):
            wynik = przebieg_psi(t0, ust)
            print(f"{t0}: {len(wynik['alerty'])} alertów {sorted(wynik['alerty'])}")
        return
    if args.wyslij:
        ids = client.send_sync(inngest.Event(name=ZDARZENIE, data={"dzien": str(args.dzien)}))
        print(f"Wysłano {ZDARZENIE} dla {args.dzien} (zdarzenie {ids[0]}). Przebieg widać w panelu Inngest.")
        return
    print(json.dumps(przebieg(args.dzien, noc.Ustawienia.z_env()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
