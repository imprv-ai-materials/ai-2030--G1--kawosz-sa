"use client";

import { useEffect, useRef, useState } from "react";

import { Dymek, useDymek } from "../panel/Dymek";
import { dataDluga, liczba, miesiac, odmiana, proc, zlote, zloteKrotko } from "../panel/format";
import { Kontrola } from "./Kontrola";
import { Krzywa } from "./Krzywa";
import type { KluczSuwaka, Suwak, WynikKalkulatora, Zalozenia } from "./typy";

const NAZWY: Record<KluczSuwaka, string> = {
  V: "Wartość utrzymanego biura (V)",
  C: "Koszt wizyty z rabatem (C)",
  s: "Skuteczność wizyty (s)",
  budzet_wizyt: "Budżet wizyt na kwartał",
};

// założenia z suwaków i udział grupy kontrolnej (0: bez kontroli)
type Parametry = Zalozenia & { kontrola: number };

// parametry adresu: ten sam zestaw czyta strona (page.tsx) i API
const W_ADRESIE: Record<keyof Parametry, string> = {
  s: "s",
  V: "V",
  C: "C",
  budzet_wizyt: "budzet",
  kontrola: "kontrola",
};
const KLUCZE = Object.keys(W_ADRESIE) as (keyof Parametry)[];

function pokazWartosc(klucz: KluczSuwaka, v: number): string {
  if (klucz === "s") return proc(v);
  if (klucz === "budzet_wizyt") return odmiana(v, ["wizyta", "wizyty", "wizyt"]);
  return `${liczba(v)} zł`;
}

/** „koszt_wizyty + rabat_pct × … = 300 + 0.10 × 3200 × 3” → „300 + 0,10 × 3200 × 3”: same liczby, po polsku. */
function rachunek(tekst: string): string {
  return tekst.slice(tekst.indexOf(" = ") + 3).replace(/(\d)\.(\d)/g, "$1,$2");
}

function poprawne(z: Parametry): boolean {
  return (
    Object.values(z).every(Number.isFinite) &&
    z.s > 0 &&
    z.s <= 1 &&
    z.V > 0 &&
    z.C >= 0 &&
    z.budzet_wizyt >= 0 &&
    z.kontrola >= 0 &&
    z.kontrola <= 0.5
  );
}

function rowne(a: Parametry, b: Parametry, klucze: (keyof Parametry)[] = KLUCZE): boolean {
  return klucze.every((k) => a[k] === b[k]);
}

function zapytanie(z: Parametry): string {
  return new URLSearchParams(KLUCZE.map((k) => [W_ADRESIE[k], String(z[k])])).toString();
}

function parametry(w: WynikKalkulatora): Parametry {
  return { ...w.zalozenia, kontrola: w.kontrola.udzial };
}

function PoleSuwaka({
  suwak,
  wartosc,
  ustaw,
}: {
  suwak: Suwak;
  wartosc: number;
  ustaw: (v: number) => void;
}) {
  const id = `suwak-${suwak.klucz}`;
  const procent = suwak.klucz === "s";
  // pole liczbowe w jednostce, którą widać (s w procentach), suwak w jednostce API
  const naTekst = (v: number) => String(procent ? Math.round(v * 1000) / 10 : v);
  const [tekst, ustawTekst] = useState(naTekst(wartosc));
  useEffect(() => {
    ustawTekst(naTekst(wartosc));
  }, [wartosc]);
  const zmieniony = wartosc !== suwak.wartosc;
  return (
    <div className="suwak">
      <div className="naglowek-suwaka">
        <label htmlFor={id}>{NAZWY[suwak.klucz]}</label>
        <span className="pole-wartosci">
          <input
            type="number"
            aria-label={`${NAZWY[suwak.klucz]}, dokładna wartość${procent ? " w procentach" : ""}`}
            value={tekst}
            min={procent ? 1 : 0}
            max={procent ? 100 : undefined}
            step={procent ? 1 : suwak.krok}
            onChange={(e) => {
              ustawTekst(e.target.value);
              const v = Number(e.target.value);
              if (e.target.value !== "" && Number.isFinite(v)) ustaw(procent ? v / 100 : v);
            }}
          />
          <span className="jednostka">{procent ? "%" : suwak.klucz === "budzet_wizyt" ? "wizyt" : "zł"}</span>
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={suwak.min}
        max={suwak.max}
        step={suwak.krok}
        value={Math.min(suwak.max, Math.max(suwak.min, wartosc))}
        aria-valuetext={pokazWartosc(suwak.klucz, wartosc)}
        onChange={(e) => ustaw(Number(e.target.value))}
      />
      <div className="skala-suwaka drobne liczby">
        <span>{pokazWartosc(suwak.klucz, suwak.min)}</span>
        <span>{pokazWartosc(suwak.klucz, suwak.max)}</span>
      </div>
      <p className="drobne opis-suwaka">
        {zmieniony ? (
          <>
            W założeniach: <strong>{pokazWartosc(suwak.klucz, suwak.wartosc)}</strong>.{" "}
          </>
        ) : (
          <>Wartość z założeń. </>
        )}
        {suwak.przedzial && (
          <>
            Możliwy zakres: {pokazWartosc(suwak.klucz, suwak.przedzial[0])} –{" "}
            {pokazWartosc(suwak.klucz, suwak.przedzial[1])}.{" "}
          </>
        )}
        {suwak.rachunek && <>Rachunek: {rachunek(suwak.rachunek)}. </>}
        Podaje: {suwak.wlasciciel}.
      </p>
    </div>
  );
}

export default function Kalkulator({ start }: { start: WynikKalkulatora }) {
  const [z, ustawZ] = useState<Parametry>(parametry(start));
  const [wynik, ustawWynik] = useState(start);
  const [stan, ustawStan] = useState<{ licze: boolean; blad: string | null }>({ licze: false, blad: null });
  const [skopiowano, ustawSkopiowano] = useState(false);
  const { dymek, pokaz, ukryj } = useDymek();
  const pokazane = useRef(parametry(start));

  const zalozenia = {
    ...(Object.fromEntries(start.suwaki.map((s) => [s.klucz, s.wartosc])) as Zalozenia),
    kontrola: 0,
  };
  // grupa kontrolna to decyzja o planie, a nie założenie: „Przywróć założenia” jej nie wyłącza
  const zmienione = !rowne(
    z,
    zalozenia,
    start.suwaki.map((s) => s.klucz),
  );

  // po każdej zmianie: przeliczenie w API (retention_bc), ostatnia zmiana wygrywa
  useEffect(() => {
    if (!poprawne(z)) {
      ustawStan({
        licze: false,
        blad: "Popraw wartości: skuteczność 1–100%, wartość biura większa od zera, grupa kontrolna 0–50%.",
      });
      return;
    }
    if (rowne(z, pokazane.current)) {
      ustawStan({ licze: false, blad: null });
      return;
    }
    const przerwij = new AbortController();
    ustawStan((s) => ({ ...s, licze: true }));
    const czekaj = setTimeout(async () => {
      try {
        const odpowiedz = await fetch(`/wizyty/wynik?${zapytanie(z)}`, { signal: przerwij.signal });
        if (!odpowiedz.ok) {
          const tresc = await odpowiedz.json().catch(() => null);
          throw new Error(tresc?.detail ?? `API odpowiedziało kodem ${odpowiedz.status}.`);
        }
        const nowy = (await odpowiedz.json()) as WynikKalkulatora;
        pokazane.current = parametry(nowy);
        ustawWynik(nowy);
        ustawStan({ licze: false, blad: null });
      } catch (e) {
        if (!przerwij.signal.aborted)
          ustawStan({ licze: false, blad: `Nie udało się przeliczyć. ${e instanceof Error ? e.message : ""}` });
      }
    }, 150);
    return () => {
      clearTimeout(czekaj);
      przerwij.abort();
    };
  }, [z]);

  // adres strony niesie założenia: link otwiera ten sam scenariusz
  useEffect(() => {
    const adres = rowne(z, zalozenia) ? window.location.pathname : `${window.location.pathname}?${zapytanie(z)}`;
    window.history.replaceState(null, "", adres);
    ustawSkopiowano(false);
  }, [z]);

  const w = wynik;
  const { s, V, C, budzet_wizyt: budzet } = w.zalozenia;
  const wizyty = w.lista.filter((b) => b.grupa === "wizyta");
  const zKontrola = w.kontrola.biura > 0;
  const opiekunowie = Object.entries(
    wizyty.reduce<Record<string, number>>((acc, b) => {
      const kto = b.opiekun ?? "bez opiekuna";
      acc[kto] = (acc[kto] ?? 0) + 1;
      return acc;
    }, {}),
  ).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "pl"));

  const pobierzCsv = () => {
    // plik jest też zapisem eksperymentu: kto był w kontroli, z jakim p i przy jakich założeniach
    const ulamek = (x: number, miejsca: number) => x.toFixed(miejsca).replace(".", ",");
    const wiersze = [
      [
        "lp", "id_biura", "biuro", "miasto", "opiekun", "ryzyko_odejscia_90d", "wartosc_wizyty_zl", "grupa",
        "powod_1", "powod_2", "powod_3",
        "kwartal", "data_listy", "model", "s", "V_zl", "C_zl", "udzial_kontroli",
      ],
      ...w.lista.map((b, i) => [
        i + 1,
        b.id_biura,
        b.nazwa ?? "",
        b.miasto ?? "",
        b.opiekun ?? "",
        ulamek(b.p, 4),
        ulamek(b.wartosc_wizyty, 2),
        b.grupa,
        ...[0, 1, 2].map((i) => b.powody[i] ?? ""),
        w.kontrola.kwartal,
        w.dzis,
        w.model,
        ulamek(s, 2),
        V,
        C,
        ulamek(w.kontrola.udzial, 2),
      ]),
    ];
    const csv = wiersze.map((r) => r.map((p) => `"${String(p).replaceAll('"', '""')}"`).join(";")).join("\r\n");
    const url = URL.createObjectURL(new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" }));
    const a = Object.assign(document.createElement("a"), {
      href: url,
      download: `wizyty_${w.kontrola.kwartal}_${w.dzis}.csv`,
    });
    // link musi być w dokumencie, a adres pliku żyć, dopóki przeglądarka nie zacznie pobierania
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <main>
      <header>
        <h1>Kalkulator wizyt opiekunów</h1>
        <p className="lead">
          Do których biur wysłać opiekuna z ofertą rabatu, żeby nie odeszły. Wizyta się opłaca, gdy szansa odejścia
          biura (p) razy skuteczność wizyty (s) razy wartość biura (V) przekracza koszt wizyty (C). Zmień założenia
          suwakami, a kalkulator od razu przeliczy próg, listę biur, zysk i krzywą wartości.
        </p>
        <p className="drobne">
          Biura: stan na {dataDluga(w.dzis)}, {liczba(w.biura_dzis)} biur z aktywną umową. Ryzyko odejścia w 90 dni
          z modelu {w.model}. Założenia startowe: <code>retention_bc/zalozenia.yaml</code>.
        </p>
        {w.baza.includes("_symulacja") && (
          <p className="ostrzezenie">
            <strong>To symulacja.</strong> Dzisiejsze biura pochodzą z symulacji nocnego potoku (
            <code>{w.baza}</code>), a nie z produkcyjnych danych, więc lista służy do sprawdzenia kalkulatora.
          </p>
        )}
      </header>

      <section className="karta" aria-labelledby="zalozenia">
        <div className="naglowek-karty">
          <div>
            <h2 id="zalozenia">Założenia</h2>
            <p className="lead">
              Zmieniła się cena rabatu albo koszt dojazdu? Przesuń koszt wizyty. Link do strony zapisuje Twoje
              założenia, więc możesz go wysłać dalej.
            </p>
          </div>
          <span className="przyciski">
            <button
              className="przycisk-tekstowy"
              onClick={() => {
                navigator.clipboard?.writeText(window.location.href).then(() => ustawSkopiowano(true));
              }}
            >
              {skopiowano ? "Skopiowano link" : "Kopiuj link"}
            </button>
            <button
              className="przycisk-tekstowy"
              disabled={!zmienione}
              onClick={() => ustawZ((stare) => ({ ...zalozenia, kontrola: stare.kontrola }))}
            >
              Przywróć założenia
            </button>
          </span>
        </div>
        <div className="suwaki">
          {start.suwaki.map((suwak) => (
            <PoleSuwaka
              key={suwak.klucz}
              suwak={suwak}
              wartosc={z[suwak.klucz]}
              ustaw={(v) => ustawZ((stare) => ({ ...stare, [suwak.klucz]: v }))}
            />
          ))}
        </div>
        <div className="przelacznik-kontroli">
          <label className="pole-wyboru">
            <input
              type="checkbox"
              checked={z.kontrola > 0}
              onChange={(e) => ustawZ((stare) => ({ ...stare, kontrola: e.target.checked ? start.kontrola_startowa : 0 }))}
            />
            <span>
              <strong>Grupa kontrolna</strong>: część listy losowo bez wizyty, żeby zmierzyć prawdziwą skuteczność
              wizyty
            </span>
          </label>
          {z.kontrola > 0 && (
            <span className="udzial-kontroli">
              <label htmlFor="udzial-kontroli">Udział listy bez wizyty</label>
              <input
                id="udzial-kontroli"
                type="range"
                min={0.05}
                max={0.5}
                step={0.05}
                value={z.kontrola}
                aria-valuetext={proc(z.kontrola)}
                onChange={(e) => ustawZ((stare) => ({ ...stare, kontrola: Number(e.target.value) }))}
              />
              <strong className="liczby">{proc(z.kontrola)}</strong>
            </span>
          )}
        </div>
        <p className="drobne stan-przeliczenia" role="status">
          {stan.blad ? <span className="blad-przeliczenia">{stan.blad}</span> : stan.licze ? "Przeliczam…" : ""}
        </p>
      </section>

      <div className={stan.licze || stan.blad ? "wynik nieaktualny" : "wynik"} aria-busy={stan.licze}>
        <section className="kafle" aria-label="Wynik">
          <div className="kafel glowny">
            <span className="etykieta">Próg: jedź, gdy ryzyko odejścia wynosi co najmniej</span>
            <span className="wartosc">{w.prog > 1 ? "ponad 100%" : proc(w.prog)}</span>
            <span className="opis">
              C / (s × V) = {liczba(C)} / ({proc(s)} × {liczba(V)} zł). Trafiona wizyta daje{" "}
              {zlote(w.zysk_trafionej)}, zbędna kosztuje {zlote(C)}.
            </span>
          </div>
          <div className="kafel">
            <span className="etykieta">Biura do odwiedzenia</span>
            <span className="wartosc">{liczba(wizyty.length)}</span>
            <span className="opis">
              {odmiana(w.nad_progiem, ["biuro", "biura", "biur"])} nad progiem, budżet{" "}
              {odmiana(budzet, ["wizyta", "wizyty", "wizyt"])} na kwartał.
              {zKontrola && <> Do tego {liczba(w.kontrola.biura)} w grupie kontrolnej, bez wizyty.</>}
            </span>
          </div>
          <div className="kafel">
            <span className="etykieta">Zysk z listy według modelu</span>
            <span className="wartosc">{zloteKrotko(w.zysk_oczekiwany)}</span>
            <span className="opis">
              Na kwartał: suma p × s × V − C po odwiedzonych biurach. Dzisiejszych odejść jeszcze nie znamy.
              {zKontrola && <> Grupa kontrolna obniża go o {zlote(w.kontrola.koszt)}.</>}
            </span>
          </div>
          <div className="kafel">
            <span className="etykieta">Ten sam próg w historii</span>
            <span className="wartosc">{zloteKrotko(w.historia.zysk)}</span>
            <span className="opis">
              Faktyczny zysk średnio na kwartał przy średnio {liczba(Math.round(w.historia.wizyty))} wizytach,{" "}
              {w.historia.snapszoty} snapszotów od {miesiac(w.historia.od)} do {miesiac(w.historia.do)}, najwyżej{" "}
              {liczba(budzet)} wizyt.
            </span>
          </div>
        </section>

        <section className="karta" aria-labelledby="wnioski">
          <h2 id="wnioski">Co z tego wynika</h2>
          <ul className="wnioski">
            {w.nad_progiem === 0 ? (
              <li>
                <strong>Przy tych założeniach żadna wizyta się nie opłaca.</strong> Najwyższe ryzyko odejścia wśród
                dzisiejszych biur to {proc(w.max_p)}, a próg wynosi {w.prog > 1 ? "ponad 100%" : proc(w.prog)}.
              </li>
            ) : w.nad_progiem > budzet ? (
              <li>
                <strong>Budżet jest za mały.</strong> Próg przekracza {odmiana(w.nad_progiem, ["biuro", "biura", "biur"])},
                a lista bierze {liczba(budzet)} z najwyższym ryzykiem. Wizyty u wszystkich dałyby według modelu{" "}
                {zlote(w.zysk_oczekiwany_nad_progiem)} zamiast {zlote(w.zysk_oczekiwany)}.
              </li>
            ) : (
              <li>
                <strong>
                  Opłaca się {odmiana(w.lista.length, ["wizyta", "wizyty", "wizyt"])} z budżetu {liczba(budzet)}.
                </strong>{" "}
                Nie dopełniaj budżetu: pozostałe biura mają ryzyko poniżej progu, więc według modelu każda taka wizyta
                kosztuje więcej, niż daje.
              </li>
            )}
            <li>
              Zysk według modelu i zysk w historii to dwie różne miary. W historii, na prawdziwych odejściach, ten sam
              próg dawał {zloteKrotko(w.historia.zysk)} na kwartał, a model spodziewa się dziś{" "}
              {zloteKrotko(w.zysk_oczekiwany)}. Szczegóły i niepewność: <code>docs/prog.md</code>.
            </li>
            <li>
              Najsłabiej znana liczba to skuteczność wizyty (pilotaż: 12 z 40 biur, bez grupy kontrolnej). Sprawdź,
              jak zmienia się lista przy 20% i 40%.
            </li>
          </ul>
        </section>

        {z.kontrola > 0 && <Kontrola w={w} />}

        <Krzywa krzywa={w.krzywa} prog={w.prog} budzet={budzet} historia={w.historia} pokaz={pokaz} ukryj={ukryj} />

        <section className="karta" aria-labelledby="lista">
          <div className="naglowek-karty">
            <div>
              <h2 id="lista">Biura do odwiedzenia</h2>
              <p className="lead">
                Biura z ryzykiem co najmniej {w.prog > 1 ? "100%" : proc(w.prog)}, od najbardziej zagrożonych,
                najwyżej {odmiana(budzet, ["wizyta", "wizyty", "wizyt"])}. Wartość wizyty to p × s × V − C: tyle
                średnio daje wizyta u tego biura. Pod nazwą biura są do trzech powodów ryzyka: cechy, które według
                modelu najbardziej podnoszą jego ryzyko w porównaniu z typowym biurem.
                {zKontrola && <> Biura z grupy kontrolnej zostają na liście, ale opiekun do nich nie jedzie.</>}
              </p>
            </div>
            <button className="przycisk-tekstowy" disabled={w.lista.length === 0} onClick={pobierzCsv}>
              Pobierz CSV
            </button>
          </div>
          {w.lista.length === 0 ? (
            <p className="drobne">Przy tych założeniach nie ma biur do odwiedzenia.</p>
          ) : (
            <>
              <p className="drobne">
                Wizyty na opiekuna: {opiekunowie.map(([kto, n]) => `${kto} ${n}`).join(", ")}.
              </p>
              <div className="przewijane">
                <table>
                  <thead>
                    <tr>
                      <th className="kwota">Lp.</th>
                      <th>Biuro</th>
                      <th>Miasto</th>
                      <th>Opiekun</th>
                      <th className="kwota">Ryzyko odejścia</th>
                      <th className="kwota">Wartość wizyty</th>
                      {zKontrola && <th>Grupa</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {w.lista.map((b, i) => (
                      <tr key={b.id_biura} className={b.grupa === "kontrola" ? "kontrola" : undefined}>
                        <td className="kwota">{i + 1}</td>
                        <td className="komorka-biura">
                          {b.nazwa ?? "—"} <span className="drobne">#{b.id_biura}</span>
                          {b.powody.length > 0 && (
                            <ul className="powody" aria-label="Powody ryzyka">
                              {b.powody.map((p) => (
                                <li key={p}>{p}</li>
                              ))}
                            </ul>
                          )}
                        </td>
                        <td>{b.miasto ?? "—"}</td>
                        <td>{b.opiekun ?? "—"}</td>
                        <td className="kwota">{proc(b.p)}</td>
                        <td className="kwota">{zlote(b.wartosc_wizyty)}</td>
                        {zKontrola && (
                          <td>
                            {b.grupa === "kontrola" ? <span className="plakietka-kontroli">bez wizyty</span> : "wizyta"}
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>
      </div>
      <Dymek dymek={dymek} />
    </main>
  );
}
