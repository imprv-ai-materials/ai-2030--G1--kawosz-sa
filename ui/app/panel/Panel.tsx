"use client";

import { useMemo, useState } from "react";

import { Dymek, useDymek } from "./Dymek";
import { dataZDniem, odmiana } from "./format";
import { Kafle } from "./Kafle";
import { Koszt } from "./Koszt";
import { kpi, WSZYSTKIE, wytnij } from "./licz";
import { Mapa } from "./Mapa";
import { Most } from "./Most";
import { Slowniczek } from "./Slowniczek";
import { StatusDostaw } from "./StatusDostaw";
import type { DanePanelu } from "./typy";
import { Wnioski } from "./Wnioski";

const OKRESY = [7, 14, 30];

export default function Panel({ dane }: { dane: DanePanelu }) {
  const [okres, ustawOkres] = useState(Math.min(30, dane.dni));
  const [zrodlo, ustawZrodlo] = useState(WSZYSTKIE);
  const { dymek, pokaz, ukryj } = useDymek();

  const wycinek = useMemo(() => wytnij(dane, okres, zrodlo), [dane, okres, zrodlo]);
  const liczby = useMemo(() => kpi(wycinek), [wycinek]);
  const symulacja = dane.baza.includes("_symulacja");

  return (
    <main>
      <header>
        <h1>Jakość danych przychodu</h1>
        <p className="lead">
          Co noc o 3:00 sprawdzamy dane z kas, systemu faktur i sklepu internetowego, zanim trafią do raportów
          przychodu. Dostawa z błędem, który zmieniłby kwoty w raportach, zostaje zatrzymana (kwarantanna), a raporty
          pokazują ostatni poprawny stan. Ten panel mówi, co przeszło, co zatrzymaliśmy, dlaczego i ile to kosztuje.
        </p>
        <p className="drobne">
          Stan po nocy z dnia: {dataZDniem(dane.do)}. Wszystkie kwoty to przychód netto według definicji firmy (bez
          VAT, w złotych).
        </p>
        {symulacja && (
          <p className="ostrzezenie">
            <strong>To symulacja.</strong> Nocna kontrola nie ma jeszcze własnej historii, więc panel pokazuje, jak
            wyglądałby wrzesień 2026, gdyby działała od 1 września: każda noc przeszła przez te same kontrole na
            prawdziwych danych z września. Liczby w raportach finansowych liczonych dotąd bez kontroli są inne.
          </p>
        )}
      </header>

      <div className="filtry" role="group" aria-label="Filtry panelu">
        <div>
          <span className="etykieta-filtra">Okres</span>
          <span className="przelacznik">
            {OKRESY.filter((o) => o <= dane.dni).map((o) => (
              <button key={o} aria-pressed={okres === o} onClick={() => ustawOkres(o)}>
                ostatnie {o} dni
              </button>
            ))}
          </span>
        </div>
        <div>
          <span className="etykieta-filtra">System</span>
          <span className="przelacznik">
            <button aria-pressed={zrodlo === WSZYSTKIE} onClick={() => ustawZrodlo(WSZYSTKIE)}>
              wszystkie
            </button>
            {dane.zrodla.map((z) => (
              <button key={z.id} aria-pressed={zrodlo === z.id} onClick={() => ustawZrodlo(z.id)}>
                {z.nazwa}
              </button>
            ))}
          </span>
        </div>
        <span className="drobne">
          {odmiana(wycinek.wsady.length, ["dostawa", "dostawy", "dostaw"])} w okresie; filtry zmieniają wszystko
          poniżej poza mostem przychodu, który jest miesięczny.
        </span>
      </div>

      <Kafle liczby={liczby} dane={dane} />
      <Wnioski wycinek={wycinek} dane={dane} />
      <StatusDostaw wycinek={wycinek} dane={dane} pokaz={pokaz} ukryj={ukryj} />
      <Koszt wycinek={wycinek} dane={dane} pokaz={pokaz} ukryj={ukryj} />
      <Mapa wycinek={wycinek} dane={dane} pokaz={pokaz} ukryj={ukryj} />
      <Most dane={dane} />
      <Slowniczek />

      <p className="drobne" style={{ marginTop: 24 }}>
        Źródło: tabele nocnej kontroli w bazie <code>{dane.baza}</code> (wsady, naruszenia, most_przychodu).
        Reguły i to, co zrobić przy naruszeniu, pochodzą z kontraktów danych uzgodnionych z właścicielami systemów.
      </p>
      <Dymek dymek={dymek} />
    </main>
  );
}
