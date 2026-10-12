"use client";

import { useState } from "react";

import { miesiac, proc, zlote } from "./format";
import type { DanePanelu } from "./typy";

const POCZATEK = "0. Surowa suma BI";
const NETTO = "Przychód netto";
const RESZTA = "Niewyjaśniona reszta";

export function Most({ dane }: { dane: DanePanelu }) {
  const miesiace = [...new Set(dane.most.map((k) => k.miesiac))].sort();
  const [wybrany, ustawWybrany] = useState(miesiace.at(-1) ?? "");
  const kroki = dane.most.filter((k) => k.miesiac === wybrany);
  const zmiany = kroki.filter((k) => k.krok !== POCZATEK && k.krok !== NETTO);
  const skala = Math.max(1, ...zmiany.map((k) => Math.abs(k.kwota_pln)));
  const netto = kroki.find((k) => k.krok === NETTO)?.kwota_pln ?? 0;
  const reszta = kroki.find((k) => k.krok === RESZTA)?.kwota_pln ?? 0;
  const naMiesiac = (d: string) => d.slice(0, 7) === wybrany.slice(0, 7);
  const zatrzymane = dane.wsady.filter((w) => w.status === "kwarantanna" && naMiesiac(w.dzien));
  const wstrzymane = zatrzymane.reduce((s, w) => s + (w.przychod_netto ?? 0), 0);
  const duplikaty = zatrzymane.reduce((s, w) => s + (w.zawyzenie ?? 0), 0);

  return (
    <section className="karta" aria-labelledby="most">
      <div className="naglowek-karty">
        <div>
          <h2 id="most">Most przychodu: od dashboardu BI do przychodu netto</h2>
          <p className="lead">
            Dashboard BI sumuje kwoty tak, jak leżą w systemach (brutto, w euro jak w złotych, czas sklepu w UTC).
            Most pokazuje krok po kroku, jak z tej sumy powstaje przychód netto według definicji firmy. Liczony co noc
            z danych, które są w raportach, za cały miesiąc i wszystkie systemy, więc filtry wyżej go nie zmieniają.
          </p>
        </div>
        {miesiace.length > 1 && (
          <span className="przelacznik">
            {miesiace.map((m) => (
              <button key={m} aria-pressed={wybrany === m} onClick={() => ustawWybrany(m)}>
                {miesiac(m)}
              </button>
            ))}
          </span>
        )}
      </div>

      {kroki.length === 0 ? (
        <p className="drobne">Most przychodu nie był jeszcze liczony.</p>
      ) : (
        <>
          {wstrzymane !== 0 && (
            <p className="ostrzezenie" style={{ marginTop: 0, marginBottom: 12 }}>
              <strong>Ten miesiąc jest niepełny.</strong> W kwarantannie czeka {zlote(wstrzymane)} przychodu netto z{" "}
              {zatrzymane.length} zatrzymanych dostaw z tego miesiąca (w okresie panelu). Most i przychód netto poniżej
              ich nie zawierają, dopóki dostawy nie zostaną poprawione.
            </p>
          )}
          <div className="przewijane">
            <table>
              <thead>
                <tr>
                  <th>Krok</th>
                  <th>Co zmienia</th>
                  <th className="kwota">Zmiana</th>
                  <th style={{ width: 160 }} aria-hidden="true" />
                  <th className="kwota">Suma po kroku</th>
                </tr>
              </thead>
              <tbody>
                {kroki.map((k) => {
                  const klasa = k.krok === POCZATEK || k.krok === NETTO ? "wyrozniony" : k.krok === RESZTA ? "reszta" : "";
                  const zmiana = k.krok !== POCZATEK && k.krok !== NETTO;
                  const dl = zmiana ? (Math.abs(k.kwota_pln) / skala) * 50 : 0;
                  return (
                    <tr key={k.krok} className={klasa}>
                      <td style={{ whiteSpace: "nowrap" }}>{k.krok}</td>
                      <td className="drobne">{k.opis}</td>
                      <td className="kwota">{zmiana ? zlote(k.kwota_pln) : ""}</td>
                      <td aria-hidden="true">
                        {zmiana && (
                          <div className="pasek-tla">
                            <span style={{ left: "50%", width: 1, background: "var(--axis)" }} />
                            <span
                              style={{
                                left: k.kwota_pln < 0 ? `${50 - dl}%` : "50%",
                                width: `${dl}%`,
                                background: "var(--neutral-bar)",
                              }}
                            />
                          </div>
                        )}
                      </td>
                      <td className="kwota">{zlote(k.suma_po_kroku)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="drobne" style={{ marginTop: 8 }}>
            Pasek w lewo obniża sumę, w prawo ją podwyższa. Większość różnicy to VAT (kroki 1 i 2).
          </p>
          <div className="ostrzezenie" style={{ borderLeftColor: reszta === 0 ? "var(--good)" : "var(--critical)" }}>
            <strong>Niewyjaśniona reszta: {zlote(reszta)}</strong>
            {netto !== 0 && <> ({proc(reszta / netto)} przychodu netto)</>}.{" "}
            To różnica między przychodem netto według definicji a sumą po wszystkich krokach mostu, czyli ta część
            różnicy między BI a przychodem netto, której nie tłumaczy żadna reguła.{" "}
            {reszta === 0
              ? "0,00 zł znaczy, że most się domyka: każdą złotówkę różnicy da się wyjaśnić."
              : "Wartość różna od zera to sygnał błędu w danych, którego żaden krok nie opisuje, np. zdublowanych plików z kas, które BI liczy dwa razy."}
            {duplikaty > 0 && (
              <>
                {" "}
                W tym miesiącu kwarantanna zatrzymała zdublowane dokumenty warte {zlote(duplikaty)}. Bez niej trafiłyby do
                BI, a reszta wyniosłaby {zlote(reszta - duplikaty)}.
              </>
            )}
          </div>
        </>
      )}
    </section>
  );
}
