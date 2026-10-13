"use client";

import { useState } from "react";

import { type PokazDymek, useSzerokosc } from "../panel/Dymek";
import { liczba, proc, zlote, zloteKrotko } from "../panel/format";
import type { PunktKrzywej } from "./typy";

const WYSOKOSC = 300;
const MARGINES = { gora: 22, prawo: 16, dol: 34, lewo: 72 };

interface Props {
  krzywa: PunktKrzywej[];
  prog: number;
  budzet: number;
  historia: { snapszoty: number };
  pokaz: PokazDymek;
  ukryj: () => void;
}

/** Okrągłe podziałki od dol do gora (także ujemne), ok. 5 kresek. */
function podzialki(dol: number, gora: number): number[] {
  const surowy = (gora - dol) / 5 || 1;
  const rzad = 10 ** Math.floor(Math.log10(surowy));
  const krok = [1, 2, 2.5, 5, 10].map((m) => m * rzad).find((k) => k >= surowy) ?? 10 * rzad;
  const wynik = [];
  for (let v = Math.ceil(dol / krok) * krok; v <= gora + 1e-9; v += krok) wynik.push(Math.round(v));
  return wynik;
}

export function Krzywa({ krzywa, prog, budzet, historia, pokaz, ukryj }: Props) {
  const [tabela, ustawTabele] = useState(false);
  const [ref, szerokosc] = useSzerokosc<HTMLDivElement>();
  const [aktywny, ustawAktywny] = useState<number | null>(null);

  // oś x od 0 do 0,5 (najwyższe p dziś to ok. 0,45), dalej tylko gdy próg jest wyżej
  const xMax = Math.min(1, Math.max(0.5, Math.ceil((prog + 0.05) * 10) / 10));
  const punkty = krzywa.filter((k) => k.prog <= xMax + 1e-9);
  const wartosci = punkty.flatMap((k) => [k.zysk_historia, k.zysk_oczekiwany_dzis]);
  const najwyzej = Math.max(0, ...wartosci);
  const najnizej = Math.min(0, ...wartosci);
  // przy niskich progach strata rośnie do ponad miliona: ucinamy oś, żeby było widać część z zyskiem
  const dolOsi = Math.max(najnizej, -Math.max(najwyzej, 20_000));
  const ucieta = dolOsi > najnizej;
  const osY = podzialki(dolOsi, najwyzej * 1.08 || 10_000);
  const yMin = Math.min(osY[0], dolOsi);
  const yMax = Math.max(osY.at(-1)!, najwyzej);

  const w = Math.max(0, szerokosc - MARGINES.lewo - MARGINES.prawo);
  const h = WYSOKOSC - MARGINES.gora - MARGINES.dol;
  const x = (t: number) => MARGINES.lewo + (t / xMax) * w;
  const y = (v: number) => MARGINES.gora + h - ((v - yMin) / (yMax - yMin || 1)) * h;
  const linia = (pole: "zysk_historia" | "zysk_oczekiwany_dzis") =>
    punkty.map((k) => `${x(k.prog)},${y(k[pole])}`).join(" ");

  const ponadBudzet = punkty.filter((k) => k.wizyty_dzis > budzet).at(-1)?.prog;
  const osX = Array.from({ length: Math.round(xMax * 10) + 1 }, (_, i) => i / 10);

  const dymekProgu = (k: PunktKrzywej) => (
    <>
      <div className="wartosc">próg {proc(k.prog)}</div>
      <div className="pod">wizyty u biur z ryzykiem odejścia co najmniej {proc(k.prog)}</div>
      <div className="wiersz">
        <span>
          <span className="klucz-linii" style={{ background: "var(--pos)" }} /> historia, średnio na kwartał
        </span>
        <span className="liczby">{zlote(k.zysk_historia)}</span>
      </div>
      <div className="wiersz">
        <span className="pod">wizyt średnio</span>
        <span className="liczby pod">{liczba(Math.round(k.wizyty_historia))}</span>
      </div>
      <div className="wiersz">
        <span>
          <span className="klucz-linii przerywany" /> dziś, według modelu
        </span>
        <span className="liczby">{zlote(k.zysk_oczekiwany_dzis)}</span>
      </div>
      <div className="wiersz">
        <span className="pod">wizyt dziś</span>
        <span className="liczby pod">
          {liczba(k.wizyty_dzis)}
          {k.wizyty_dzis > budzet ? ` (budżet ${liczba(budzet)})` : ""}
        </span>
      </div>
    </>
  );

  const ustaw = (i: number, cel: Parameters<PokazDymek>[0]) => {
    ustawAktywny(i);
    pokaz(cel, dymekProgu(punkty[i]));
  };
  const najblizszy = (clientX: number, el: Element) => {
    const t = ((clientX - el.getBoundingClientRect().left - MARGINES.lewo) / (w || 1)) * xMax;
    const i = punkty.findIndex((k) => k.prog >= t - 0.005);
    return i < 0 ? punkty.length - 1 : i;
  };

  return (
    <section className="karta" aria-labelledby="krzywa">
      <div className="naglowek-karty">
        <div>
          <h2 id="krzywa">Krzywa wartości: ile daje każdy próg</h2>
          <p className="lead">
            Zysk z wizyt u wszystkich biur z ryzykiem co najmniej równym progowi, bez limitu budżetu. Niebieska linia
            pokazuje faktyczny wynik tej reguły w historii (średnio na kwartał, {historia.snapszoty} snapszotów
            z prawdziwymi odejściami). Szara przerywana linia pokazuje, ile według modelu dają dzisiejsze biura.
          </p>
        </div>
        <button className="przycisk-tekstowy" onClick={() => ustawTabele(!tabela)}>
          {tabela ? "Pokaż wykres" : "Pokaż jako tabelę"}
        </button>
      </div>

      {tabela ? (
        <div className="przewijane tabela-krzywej">
          <table>
            <thead>
              <tr>
                <th>Próg</th>
                <th className="kwota">Historia: wizyty średnio</th>
                <th className="kwota">Historia: zysk na kwartał</th>
                <th className="kwota">Dziś: wizyty</th>
                <th className="kwota">Dziś: zysk według modelu</th>
              </tr>
            </thead>
            <tbody>
              {punkty.map((k) => (
                <tr key={k.prog} className={Math.abs(k.prog - prog) < 0.005 ? "wyrozniony" : undefined}>
                  <td className="liczby">{proc(k.prog)}</td>
                  <td className="kwota">{liczba(Math.round(k.wizyty_historia))}</td>
                  <td className="kwota">{zlote(k.zysk_historia)}</td>
                  <td className="kwota">{liczba(k.wizyty_dzis)}</td>
                  <td className="kwota">{zlote(k.zysk_oczekiwany_dzis)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="wykres" ref={ref}>
          {szerokosc > 0 && (
            <svg width={szerokosc} height={WYSOKOSC} role="img" aria-label="Zysk z wizyt w zależności od progu ryzyka">
              <defs>
                <clipPath id="obszar-krzywej">
                  <rect x={MARGINES.lewo} y={MARGINES.gora} width={w} height={h} />
                </clipPath>
              </defs>
              {ponadBudzet !== undefined && (
                <g>
                  <rect
                    x={MARGINES.lewo}
                    y={MARGINES.gora}
                    width={Math.max(0, x(ponadBudzet + 0.005) - MARGINES.lewo)}
                    height={h}
                    fill="var(--surface-2)"
                  />
                  <text x={MARGINES.lewo + 6} y={MARGINES.gora + 14} fontSize={11} fill="var(--muted)">
                    dziś ponad budżet {liczba(budzet)} wizyt
                  </text>
                </g>
              )}
              <g className="os">
                {osY.map((v) => (
                  <g key={v}>
                    <line x1={MARGINES.lewo} x2={MARGINES.lewo + w} y1={y(v)} y2={y(v)} stroke="var(--grid)" />
                    <text x={MARGINES.lewo - 8} y={y(v) + 4} textAnchor="end">
                      {zloteKrotko(v)}
                    </text>
                  </g>
                ))}
                <line x1={MARGINES.lewo} x2={MARGINES.lewo + w} y1={y(0)} y2={y(0)} stroke="var(--axis)" />
                {osX.map((t) => (
                  <text key={t} x={x(t)} y={WYSOKOSC - 16} textAnchor="middle">
                    {proc(t)}
                  </text>
                ))}
                <text x={MARGINES.lewo + w} y={WYSOKOSC - 2} textAnchor="end">
                  próg: ryzyko odejścia w 90 dni (p) →
                </text>
              </g>
              <g clipPath="url(#obszar-krzywej)">
                <polyline
                  fill="none"
                  stroke="var(--neutral-bar)"
                  strokeWidth={2}
                  strokeDasharray="5 4"
                  strokeLinejoin="round"
                  points={linia("zysk_oczekiwany_dzis")}
                />
                <polyline
                  fill="none"
                  stroke="var(--pos)"
                  strokeWidth={2}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  points={linia("zysk_historia")}
                />
              </g>
              {prog <= xMax && (
                <g>
                  <line x1={x(prog)} x2={x(prog)} y1={MARGINES.gora - 6} y2={MARGINES.gora + h} stroke="var(--ink)" />
                  <text
                    x={x(prog) + (x(prog) > MARGINES.lewo + w - 120 ? -6 : 6)}
                    y={MARGINES.gora - 8}
                    textAnchor={x(prog) > MARGINES.lewo + w - 120 ? "end" : "start"}
                    fontSize={12}
                    fontWeight={600}
                    fill="var(--ink)"
                  >
                    Twój próg: {proc(prog)}
                  </text>
                </g>
              )}
              {aktywny !== null && (
                <g>
                  <line
                    x1={x(punkty[aktywny].prog)}
                    x2={x(punkty[aktywny].prog)}
                    y1={MARGINES.gora}
                    y2={MARGINES.gora + h}
                    stroke="var(--axis)"
                  />
                  {(["zysk_historia", "zysk_oczekiwany_dzis"] as const).map((pole) =>
                    punkty[aktywny][pole] >= yMin ? (
                      <circle
                        key={pole}
                        cx={x(punkty[aktywny].prog)}
                        cy={y(punkty[aktywny][pole])}
                        r={4}
                        fill={pole === "zysk_historia" ? "var(--pos)" : "var(--neutral-bar)"}
                        stroke="var(--surface)"
                        strokeWidth={2}
                      />
                    ) : null,
                  )}
                </g>
              )}
              <rect
                x={MARGINES.lewo}
                y={MARGINES.gora}
                width={w}
                height={h}
                fill="transparent"
                tabIndex={0}
                aria-label="Najedź albo użyj strzałek, żeby zobaczyć zysk przy danym progu"
                onPointerMove={(ev) => ustaw(najblizszy(ev.clientX, ev.currentTarget.ownerSVGElement!), ev)}
                onPointerLeave={() => {
                  ustawAktywny(null);
                  ukryj();
                }}
                onKeyDown={(ev) => {
                  if (ev.key !== "ArrowLeft" && ev.key !== "ArrowRight") return;
                  const start = aktywny ?? Math.max(0, punkty.findIndex((k) => k.prog >= prog - 0.005));
                  const i = Math.min(punkty.length - 1, Math.max(0, start + (ev.key === "ArrowRight" ? 1 : -1)));
                  ustaw(i, ev.currentTarget);
                }}
                onBlur={() => {
                  ustawAktywny(null);
                  ukryj();
                }}
              />
            </svg>
          )}
          <div className="legenda">
            <span>
              <span className="klucz-linii" style={{ background: "var(--pos)" }} /> historia: faktyczny zysk, średnio
              na kwartał
            </span>
            <span>
              <span className="klucz-linii przerywany" /> dziś: zysk według modelu
            </span>
            {ucieta && <span className="drobne">oś ucięta: przy progu 1% strata to {zloteKrotko(najnizej)}</span>}
          </div>
        </div>
      )}
    </section>
  );
}
