"""Nocne zadanie Inngest: o 3:00 czasu polskiego wczytuje dostawę z poprzedniego dnia, sprawdza reguły jakości,
publikuje dobre wsady, odkłada złe do kwarantanny i przelicza most przychodu za miesiąc tego dnia.

Każdy krok to osobny `step.run`, więc po awarii Inngest ponawia tylko krok, który padł; wyniki wcześniejszych
kroków ma zapamiętane. Kroki (api/api/data_platform/noc.py) są idempotentne, więc ponowienie kroku, który
zdążył zapisać dane, i drugi przebieg tej samej nocy dają te same liczby.

    wczytaj-pos, wczytaj-erp, wczytaj-ecom          pliki z _dostawy/D/{źródło}/ → schemat roboczy wsad_D
    sprawdz-pos, sprawdz-erp, sprawdz-ecom          reguły jakości źródła za dzień D
    publikuj-{źródło} albo kwarantanna-{źródło}     zależnie od tego, czy złamano regułę blokującą
    most                                            most przychodu za miesiąc dnia D → most_przychodu
    sprzatanie                                      usuwa schemat roboczy

Ręczne uruchomienie dla wybranego dnia (np. po poprawionej dostawie): zdarzenie `kawosz/noc.uruchom`
z `{"dzien": "2026-09-30"}`. Bez serwera Inngest, te same kroki po kolei:

    PYTHONPATH=api poetry run python -m api.inngest_app --dzien 2026-09-30
"""

import argparse
import json
import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import inngest

from api.adapters.duckdb_conn import connect
from api.contexts_boundaries.revenue_bc.most import most as most_przychodu
from api.data_platform import noc

STREFA = ZoneInfo("Europe/Warsaw")
CRON = "TZ=Europe/Warsaw 0 3 * * *"
ZDARZENIE = "kawosz/noc.uruchom"

client = inngest.Inngest(app_id="kawosz", logger=logging.getLogger("uvicorn"))


def dzien_nocy(event: inngest.Event) -> date:
    """Dzień D, za który liczymy noc: `dzien` ze zdarzenia ręcznego, a z crona dzień przed chwilą uruchomienia
    (czas polski). Liczony ze zdarzenia, a nie z zegara, więc powtórka funkcji po awarii bierze ten sam dzień."""
    if event.data and event.data.get("dzien"):
        return date.fromisoformat(str(event.data["dzien"]))
    return (datetime.fromtimestamp(event.ts / 1000, STREFA) - timedelta(days=1)).date()


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


Krok = Callable[..., object]


def _od_razu(_nazwa: str, funkcja: Callable, *argumenty):
    return funkcja(*argumenty)


def przebieg(dzien: date, ust: noc.Ustawienia, krok: Krok = _od_razu) -> dict:
    """Cała noc dla dnia D. `krok(nazwa, funkcja, *argumenty)` to `ctx.step.run` w Inngest, a poza nim zwykłe
    wywołanie, więc obie drogi wykonują ten sam kod w tej samej kolejności."""
    wczytane = {z: krok(f"wczytaj-{z}", noc.wczytaj, ust, z, dzien) for z in noc.ZRODLA}
    sprawdzone = {z: krok(f"sprawdz-{z}", noc.sprawdz, ust, z, dzien) for z in noc.ZRODLA}
    wsady = {}
    for z, wynik in sprawdzone.items():
        if wynik["blokujace"]:
            wiersze = krok(f"kwarantanna-{z}", noc.odloz, ust, z, dzien, wynik["blokujace"])
            wsady[z] = {"status": "kwarantanna", "wiersze": wiersze, **wynik}
        else:
            wiersze = krok(f"publikuj-{z}", noc.opublikuj, ust, z, dzien)
            wsady[z] = {"status": "opublikowany", "wiersze": wiersze, **wynik}
    most = krok("most", przelicz_most, ust, dzien)
    krok("sprzatanie", noc.sprzataj, ust, dzien)
    return {"dzien": str(dzien), "wczytane": wczytane, "wsady": wsady, "most": most}


@client.create_function(
    fn_id="kawosz-noc",
    name="Kawosz: nocne ładowanie, reguły jakości i most przychodu",
    trigger=[inngest.TriggerCron(cron=CRON), inngest.TriggerEvent(event=ZDARZENIE)],
    # DuckDB ma jednego piszącego: dwie noce naraz (cron i ręczne uruchomienie) czekają na siebie.
    concurrency=[inngest.Concurrency(limit=1)],
    retries=3,
)
def kawosz_noc(ctx: inngest.ContextSync) -> dict:
    return przebieg(dzien_nocy(ctx.event), noc.Ustawienia.z_env(), ctx.step.run)


FUNKCJE = [kawosz_noc]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dzien", type=date.fromisoformat, required=True, help="dzień dostawy RRRR-MM-DD")
    args = parser.parse_args()
    print(json.dumps(przebieg(args.dzien, noc.Ustawienia.z_env()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
