"use client";

import { Fragment, useState } from "react";

import type { PokazDymek } from "./Dymek";
import { dataZDniem, liczba, odmiana, proc, weekend } from "./format";
import { klasa, KLASY, mapaNaruszen, type WierszMapy, type Wycinek } from "./licz";
import type { DanePanelu, Naruszenie, Regula } from "./typy";

interface Props {
  wycinek: Wycinek;
  dane: DanePanelu;
  pokaz: PokazDymek;
  ukryj: () => void;
}

const kolor = (k: number) => (k === 0 ? "var(--empty)" : `var(--seq-${k})`);

export function Mapa({ wycinek, dane, pokaz, ukryj }: Props) {
  const [tabela, ustawTabele] = useState(false);
  const [rozwinieta, ustawRozwinieta] = useState<string | null>(null);
  const { z, bez } = mapaNaruszen(wycinek, dane.reguly);
  const blokujace = z.filter((w) => w.regula.poziom === "blokuje");
  const ostrzegajace = z.filter((w) => w.regula.poziom === "ostrzega");
  const kolumny = `340px repeat(${wycinek.dni.length}, minmax(14px, 1fr)) 120px`;

  const dymekPola = (r: Regula, dzien: string, n: Naruszenie | undefined) => (
    <>
      <div className="wartosc">
        {n?.blad
          ? "reguły nie udało się wykonać"
          : n
            ? `${liczba(n.bledne)} z ${liczba(n.sprawdzone)}`
            : "brak wyniku"}
      </div>
      <div className="pod">
        {r.id}, {dataZDniem(dzien)}
      </div>
      {n && !n.blad && n.sprawdzone > 0 && (
        <div className="pod">
          {proc(n.bledne / n.sprawdzone)} sprawdzonych (jednostka: {r.jednostka})
        </div>
      )}
    </>
  );

  const wiersz = (w: WierszMapy) => (
    <Fragment key={w.regula.id}>
      <button
        className="opis-reguly"
        aria-expanded={rozwinieta === w.regula.id}
        onClick={() => ustawRozwinieta(rozwinieta === w.regula.id ? null : w.regula.id)}
        title={w.regula.opis}
      >
        <span className="id">{w.regula.id}</span>
        <span className="tekst">{w.regula.opis}</span>
      </button>
      {wycinek.dni.map((d) => {
        const n = w.dni[d];
        return (
          <span
            key={d}
            className="pole"
            tabIndex={0}
            style={{
              background: n?.blad ? "var(--critical)" : kolor(klasa(n?.bledne ?? 0)),
            }}
            onPointerMove={(e) => pokaz(e, dymekPola(w.regula, d, n))}
            onPointerLeave={ukryj}
            onFocus={(e) => pokaz(e.currentTarget, dymekPola(w.regula, d, n))}
            onBlur={ukryj}
          />
        );
      })}
      <span className="podsumowanie-wiersza">
        {w.dniZNaruszeniem} z {wycinek.dni.length} dni
      </span>
      {rozwinieta === w.regula.id && (
        <div style={{ gridColumn: "1 / -1" }} className="lista-regul">
          <div style={{ padding: "8px 12px", border: "1px solid var(--border)", borderRadius: 8 }}>
            <span className={`plakietka ${w.regula.poziom}`}>{w.regula.poziom}</span> <strong>{w.regula.id}</strong>:{" "}
            {w.regula.opis}.
            <div className="co-zrobic">
              <strong>Poprawia: {w.regula.wlasciciel}.</strong> {w.regula.co_zrobic}
            </div>
          </div>
        </div>
      )}
    </Fragment>
  );

  const sekcja = (tytul: string, opis: string, wiersze: WierszMapy[]) =>
    wiersze.length > 0 && (
      <>
        <span className="sekcja" style={{ gridColumn: "1 / -1" }}>
          {tytul} <span style={{ textTransform: "none", fontWeight: 400 }}>· {opis}</span>
        </span>
        {wiersze.map(wiersz)}
      </>
    );

  return (
    <section className="karta" aria-labelledby="trend">
      <div className="naglowek-karty">
        <div>
          <h2 id="trend">Naruszenia reguł dzień po dniu</h2>
          <p className="lead">
            Każdy wiersz to jedna reguła kontroli, każda kratka to jedna noc. Im ciemniejsza kratka, tym więcej
            rekordów łamało regułę. Reguła blokująca z choćby jednym naruszeniem zatrzymuje całą dostawę; ostrzegająca
            jej nie zatrzymuje. Opis przy regule mówi, czego wymaga. Kliknij regułę, żeby zobaczyć, kto ją poprawia i jak.
          </p>
        </div>
        <button className="przycisk-tekstowy" onClick={() => ustawTabele(!tabela)}>
          {tabela ? "Pokaż mapę" : "Pokaż jako tabelę"}
        </button>
      </div>

      {tabela ? (
        <div className="przewijane">
          <table>
            <thead>
              <tr>
                <th>Reguła</th>
                <th>Poziom</th>
                <th>Poprawia</th>
                <th className="kwota">Dni z naruszeniem</th>
                <th className="kwota">Rekordy z naruszeniem</th>
              </tr>
            </thead>
            <tbody>
              {z.map((w) => (
                <tr key={w.regula.id}>
                  <td>
                    <strong>{w.regula.id}</strong> <span className="drobne">{w.regula.opis}</span>
                  </td>
                  <td>
                    <span className={`plakietka ${w.regula.poziom}`}>{w.regula.poziom}</span>
                  </td>
                  <td>{w.regula.wlasciciel}</td>
                  <td className="kwota">
                    {w.dniZNaruszeniem} z {wycinek.dni.length}
                  </td>
                  <td className="kwota">
                    {liczba(w.rekordy)} <span className="drobne">({w.regula.jednostka})</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="przewijane">
          <div className="mapa" style={{ gridTemplateColumns: kolumny }}>
            <span />
            {wycinek.dni.map((d) => (
              <span key={d} className={`os-dni${weekend(d) ? " weekend" : ""}`} title={dataZDniem(d)}>
                {Number(d.slice(8, 10))}
              </span>
            ))}
            <span />
            {sekcja("Blokujące", "zatrzymują dostawę", blokujace)}
            {sekcja("Ostrzegające", "dane idą dalej, właściciel dostaje listę", ostrzegajace)}
          </div>
        </div>
      )}

      <div className="legenda">
        <span>Rekordy z naruszeniem w nocy:</span>
        {KLASY.map((k, i) => (
          <span key={k}>
            <i className="skala" style={{ display: "inline-block", width: 18, height: 12, borderRadius: 2, background: kolor(i) }} />
            {k}
          </span>
        ))}
      </div>
      <p className="drobne" style={{ marginTop: 8 }}>
        Rekordem jest to, co sprawdza reguła: paragon, pozycja, faktura albo dzień lokalu (patrz dymek), więc liczb
        z różnych reguł nie porównujemy wprost.
      </p>
      {bez.length > 0 && (
        <details style={{ marginTop: 8 }}>
          <summary>{odmiana(bez.length, ["reguła", "reguły", "reguł"])} bez żadnego naruszenia w tym okresie</summary>
          <ul className="wnioski" style={{ marginTop: 8 }}>
            {bez.map((r) => (
              <li key={r.id} className="drobne">
                <strong>{r.id}</strong> ({r.poziom}): {r.opis}.
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
