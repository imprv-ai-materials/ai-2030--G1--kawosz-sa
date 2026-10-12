"use client";

import { Fragment, useState } from "react";

import type { PokazDymek } from "./Dymek";
import { dataKrotka, dataZDniem, liczba, odmiana, weekend, zlote } from "./format";
import type { Wycinek } from "./licz";
import type { DanePanelu, Wsad } from "./typy";

const SLOWO = { opublikowany: "w raportach", kwarantanna: "zatrzymana w kwarantannie" } as const;
const IKONA = { opublikowany: "✓", kwarantanna: "✕" } as const;

interface Props {
  wycinek: Wycinek;
  dane: DanePanelu;
  pokaz: PokazDymek;
  ukryj: () => void;
}

export function StatusDostaw({ wycinek, dane, pokaz, ukryj }: Props) {
  const ostatniaZatrzymana = [...wycinek.wsady].reverse().find((w) => w.status === "kwarantanna");
  const [wybrany, ustawWybrany] = useState<string | null>(null);
  const [tabela, ustawTabele] = useState(false);
  const klucz = (w: Wsad) => `${w.zrodlo}/${w.dzien}`;
  const wybranyWsad =
    wycinek.wsady.find((w) => klucz(w) === wybrany) ?? (wybrany === null ? ostatniaZatrzymana : undefined);
  const nazwa = (id: string) => dane.zrodla.find((z) => z.id === id)?.nazwa ?? id;
  const kolumny = `minmax(150px, 210px) repeat(${wycinek.dni.length}, minmax(22px, 1fr))`;

  const opisWsadu = (w: Wsad) => (
    <>
      <div className="wartosc">{w.przychod_netto === null ? "bez wyceny" : zlote(w.przychod_netto)}</div>
      <div className="pod">
        {nazwa(w.zrodlo)}, {dataZDniem(w.dzien)}
      </div>
      <div className={`status ${w.status}`} style={{ marginTop: 4 }}>
        <span className={`znacznik ${w.status}`}>{IKONA[w.status]}</span> {SLOWO[w.status]}
      </div>
      {w.blokujace.length > 0 && <div className="pod">Zatrzymały ją reguły: {w.blokujace.join(", ")}</div>}
    </>
  );

  return (
    <section className="karta" aria-labelledby="status">
      <div className="naglowek-karty">
        <div>
          <h2 id="status">Dostawy dzień po dniu</h2>
          <p className="lead">
            Każdy system co noc przysyła dane z poprzedniego dnia. Zielona dostawa jest w raportach, czerwona czeka
            w kwarantannie na poprawkę u źródła. Kliknij dzień, żeby zobaczyć, co jest nie tak i kto to poprawia.
          </p>
        </div>
        <button className="przycisk-tekstowy" onClick={() => ustawTabele(!tabela)}>
          {tabela ? "Pokaż siatkę" : "Pokaż jako tabelę"}
        </button>
      </div>

      {tabela ? (
        <div className="przewijane">
          <table>
            <thead>
              <tr>
                <th>Dzień</th>
                <th>System</th>
                <th>Status</th>
                <th className="kwota">Przychód netto</th>
                <th>Reguły, które zatrzymały dostawę</th>
              </tr>
            </thead>
            <tbody>
              {wycinek.wsady.map((w) => (
                <tr key={klucz(w)}>
                  <td className="liczby">{dataKrotka(w.dzien)}</td>
                  <td>{nazwa(w.zrodlo)}</td>
                  <td>
                    <span className={`status ${w.status}`}>
                      <span className={`znacznik ${w.status}`}>{IKONA[w.status]}</span> {SLOWO[w.status]}
                    </span>
                  </td>
                  <td className="kwota">{w.przychod_netto === null ? "—" : zlote(w.przychod_netto)}</td>
                  <td>{w.blokujace.join(", ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="przewijane">
          <div className="siatka-statusow" style={{ gridTemplateColumns: kolumny }}>
            <span />
            {wycinek.dni.map((d) => (
              <span key={d} className={`os-dni${weekend(d) ? " weekend" : ""}`} title={dataZDniem(d)}>
                {Number(d.slice(8, 10))}
              </span>
            ))}
            {wycinek.zrodla.map((z) => (
              <Fragment key={z}>
                <span className="wiersz-etykieta">
                  <span className="kropka" style={{ background: `var(--${z})` }} />
                  {nazwa(z)}
                </span>
                {wycinek.dni.map((d) => {
                  const w = wycinek.wsady.find((x) => x.zrodlo === z && x.dzien === d);
                  if (!w)
                    return (
                      <span key={d} className="komorka brak" title={`${nazwa(z)}, ${dataZDniem(d)}: brak wyniku nocy`}>
                        ·
                      </span>
                    );
                  return (
                    <button
                      key={d}
                      className={`komorka ${w.status}`}
                      aria-pressed={wybranyWsad ? klucz(wybranyWsad) === klucz(w) : false}
                      aria-label={`${nazwa(z)}, ${dataZDniem(d)}: ${SLOWO[w.status]}`}
                      onClick={() => ustawWybrany(klucz(w))}
                      onPointerMove={(e) => pokaz(e, opisWsadu(w))}
                      onPointerLeave={ukryj}
                      onFocus={(e) => pokaz(e.currentTarget, opisWsadu(w))}
                      onBlur={ukryj}
                    >
                      {IKONA[w.status]}
                    </button>
                  );
                })}
              </Fragment>
            ))}
          </div>
        </div>
      )}

      {!tabela && (
        <div className="legenda">
          <span>
            <span className="znacznik opublikowany">✓</span> dostawa w raportach
          </span>
          <span>
            <span className="znacznik kwarantanna">✕</span> dostawa zatrzymana (kwarantanna)
          </span>
          <span>
            <span className="znacznik brak">·</span> brak wyniku nocy
          </span>
          <span className="drobne">Pogrubione numery dni to weekendy.</span>
        </div>
      )}

      {wybranyWsad && <Szczegoly wsad={wybranyWsad} dane={dane} />}
    </section>
  );
}

function Szczegoly({ wsad, dane }: { wsad: Wsad; dane: DanePanelu }) {
  const nazwa = dane.zrodla.find((z) => z.id === wsad.zrodlo)?.nazwa ?? wsad.zrodlo;
  const wyniki = dane.naruszenia.filter((n) => n.zrodlo === wsad.zrodlo && n.dzien === wsad.dzien);
  const regula = (id: string) => dane.reguly.find((r) => r.id === id);
  const blokujace = wsad.blokujace.map((id) => ({ r: regula(id), n: wyniki.find((x) => x.regula === id) }));
  const ostrzezenia = wyniki
    .filter((n) => n.bledne > 0 && regula(n.regula)?.poziom === "ostrzega")
    .map((n) => ({ r: regula(n.regula), n }));

  return (
    <div className="szczegoly" aria-live="polite">
      <h3>
        {nazwa}, {dataZDniem(wsad.dzien)}:{" "}
        <span className={`status ${wsad.status}`}>
          <span className={`znacznik ${wsad.status}`}>{IKONA[wsad.status]}</span> {SLOWO[wsad.status]}
        </span>
      </h3>
      <p>
        Dostawa niesie {wsad.przychod_netto === null ? "przychód, którego nie udało się wycenić" : zlote(wsad.przychod_netto)}{" "}
        przychodu netto
        {wsad.status === "kwarantanna"
          ? ". Tej kwoty nie ma w raportach, dopóki właściciel systemu nie poprawi danych i dostawa nie przejdzie kontroli."
          : " i ta kwota jest w raportach."}
        {(wsad.zawyzenie ?? 0) > 0 && (
          <>
            {" "}
            W dostawie są zdublowane dokumenty: gdyby przeszła, raport pokazałby o <strong>{zlote(wsad.zawyzenie ?? 0)}</strong>{" "}
            za dużo.
          </>
        )}
        {wsad.wycena_uwaga && <> Wycena niemożliwa: {wsad.wycena_uwaga}</>}
      </p>
      {blokujace.length > 0 && (
        <>
          <h3 style={{ marginTop: 12 }}>Dlaczego zatrzymana</h3>
          <ul className="lista-regul">
            {blokujace.map(({ r, n }) =>
              r ? (
                <li key={r.id}>
                  <span className="plakietka blokuje">blokuje</span> <strong>{r.id}</strong> niespełniona: „{r.opis}”.
                  {n && (
                    <span className="drobne">
                      {" "}
                      {n.blad
                        ? "Reguły nie udało się wykonać, więc nie wiemy, czy dane są dobre."
                        : `Nie spełnia jej ${liczba(n.bledne)} z ${liczba(n.sprawdzone)} sprawdzonych (jednostka: ${r.jednostka}).`}
                    </span>
                  )}
                  <div className="co-zrobic">
                    <strong>Poprawia: {r.wlasciciel}.</strong> {r.co_zrobic}
                  </div>
                </li>
              ) : null,
            )}
          </ul>
        </>
      )}
      {ostrzezenia.length > 0 && (
        <details style={{ marginTop: 12 }}>
          <summary>
            {odmiana(ostrzezenia.length, ["ostrzeżenie", "ostrzeżenia", "ostrzeżeń"])}: dane idą dalej, właściciel
            dostaje listę do poprawy
          </summary>
          <ul className="lista-regul">
            {ostrzezenia.map(({ r, n }) =>
              r ? (
                <li key={r.id}>
                  <span className="plakietka ostrzega">ostrzega</span> <strong>{r.id}</strong> niespełniona: „{r.opis}”.{" "}
                  <span className="drobne">
                    {liczba(n.bledne)} z {liczba(n.sprawdzone)} (jednostka: {r.jednostka}).
                  </span>
                  <div className="co-zrobic">
                    <strong>Poprawia: {r.wlasciciel}.</strong> {r.co_zrobic}
                  </div>
                </li>
              ) : null,
            )}
          </ul>
        </details>
      )}
      {wsad.raport && <p className="drobne" style={{ marginTop: 10 }}>Raport techniczny dla zespołu danych: {wsad.raport}</p>}
    </div>
  );
}
