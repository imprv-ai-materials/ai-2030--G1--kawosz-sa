"use client";

import { useState } from "react";

import { type PokazDymek, useSzerokosc } from "./Dymek";
import { dataKrotka, dataZDniem, odmiana, zlote, zloteKrotko } from "./format";
import { narastajaco, przyczyny, type Wycinek } from "./licz";
import type { DanePanelu } from "./typy";

const WYSOKOSC = 240;
const MARGINES = { gora: 12, prawo: 132, dol: 26, lewo: 64 };

interface Props {
  wycinek: Wycinek;
  dane: DanePanelu;
  pokaz: PokazDymek;
  ukryj: () => void;
}

/** Ładne podziałki osi: 0 i 3–5 okrągłych wartości do maksimum. */
function podzialki(max: number): number[] {
  if (max <= 0) return [0];
  const surowy = max / 4;
  const rzad = 10 ** Math.floor(Math.log10(surowy));
  const krok = [1, 2, 2.5, 5, 10].map((m) => m * rzad).find((k) => k >= surowy) ?? 10 * rzad;
  return Array.from({ length: Math.ceil(max / krok) + 1 }, (_, i) => i * krok);
}

export function Koszt({ wycinek, dane, pokaz, ukryj }: Props) {
  const [tabela, ustawTabele] = useState(false);
  const [ref, szerokosc] = useSzerokosc<HTMLDivElement>();
  const [aktywny, ustawAktywny] = useState<number | null>(null);
  const seria = narastajaco(wycinek);
  const lista = przyczyny(wycinek, dane.reguly);
  const nazwa = (id: string) => dane.zrodla.find((z) => z.id === id)?.nazwa ?? id;
  const krotkaNazwa = (id: string) => nazwa(id).replace(/ \(.*\)$/, "");

  const max = Math.max(0, ...seria.map((p) => Math.max(...wycinek.zrodla.map((z) => p.zrodla[z]))));
  const osY = podzialki(max);
  const gornaY = osY.at(-1) || 1;
  const w = Math.max(0, szerokosc - MARGINES.lewo - MARGINES.prawo);
  const h = WYSOKOSC - MARGINES.gora - MARGINES.dol;
  const x = (i: number) => MARGINES.lewo + (seria.length > 1 ? (i / (seria.length - 1)) * w : w / 2);
  const y = (v: number) => MARGINES.gora + h - (v / gornaY) * h;

  // etykiety na końcu linii: bez nakładania, z cienkim łącznikiem, gdy etykietę trzeba odsunąć
  const ostatni = seria.at(-1);
  const etykiety = wycinek.zrodla
    .map((z) => ({ z, v: ostatni?.zrodla[z] ?? 0, y0: y(ostatni?.zrodla[z] ?? 0), y: y(ostatni?.zrodla[z] ?? 0) }))
    .sort((a, b) => a.y0 - b.y0);
  for (let i = 1; i < etykiety.length; i++)
    etykiety[i].y = Math.max(etykiety[i].y, etykiety[i - 1].y + 30);

  const dymekDnia = (i: number) => {
    const p = seria[i];
    const razem = wycinek.zrodla.reduce((s, z) => s + p.zrodla[z], 0);
    return (
      <>
        <div className="wartosc">{zlote(razem)}</div>
        <div className="pod">zatrzymane od {dataKrotka(seria[0].dzien)} do {dataZDniem(p.dzien)}</div>
        {wycinek.zrodla.map((z) => (
          <div className="wiersz" key={z}>
            <span>
              <span className="klucz-linii" style={{ background: `var(--${z})` }} /> {krotkaNazwa(z)}
            </span>
            <span className="liczby">
              {zlote(p.zrodla[z])}
              {p.dnia[z] > 0 && <span className="pod"> (+{zloteKrotko(p.dnia[z])} tego dnia)</span>}
            </span>
          </div>
        ))}
      </>
    );
  };

  const najblizszy = (clientX: number, el: Element) => {
    const lewo = el.getBoundingClientRect().left;
    const i = Math.round(((clientX - lewo - MARGINES.lewo) / (w || 1)) * (seria.length - 1));
    return Math.min(seria.length - 1, Math.max(0, i));
  };

  return (
    <section className="karta" aria-labelledby="koszt">
      <div className="naglowek-karty">
        <div>
          <h2 id="koszt">Ile kosztują błędy w danych</h2>
          <p className="lead">
            Przychód netto z zatrzymanych dostaw, narastająco od początku okresu. Tych pieniędzy nie ma w raportach,
            dopóki źródło nie poprawi danych. To nie jest strata: sprzedaż się odbyła, tylko raport jej jeszcze nie
            pokazuje.
          </p>
        </div>
        <button className="przycisk-tekstowy" onClick={() => ustawTabele(!tabela)}>
          {tabela ? "Pokaż wykres" : "Pokaż jako tabelę"}
        </button>
      </div>

      <div>
        <div>
          {tabela ? (
            <div className="przewijane">
              <table>
                <thead>
                  <tr>
                    <th>Dzień</th>
                    {wycinek.zrodla.map((z) => (
                      <th key={z} className="kwota">
                        {krotkaNazwa(z)}, narastająco
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {seria.map((p) => (
                    <tr key={p.dzien}>
                      <td className="liczby">{dataKrotka(p.dzien)}</td>
                      {wycinek.zrodla.map((z) => (
                        <td key={z} className="kwota">
                          {zlote(p.zrodla[z])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="wykres" ref={ref}>
              {szerokosc > 0 && (
                <svg
                  width={szerokosc}
                  height={WYSOKOSC}
                  role="img"
                  aria-label="Przychód netto zatrzymany w kwarantannie narastająco, według systemów"
                >
                  <g className="os">
                    {osY.map((v) => (
                      <g key={v}>
                        <line x1={MARGINES.lewo} x2={MARGINES.lewo + w} y1={y(v)} y2={y(v)} stroke="var(--grid)" />
                        <text x={MARGINES.lewo - 8} y={y(v) + 4} textAnchor="end">
                          {zloteKrotko(v)}
                        </text>
                      </g>
                    ))}
                    <line
                      x1={MARGINES.lewo}
                      x2={MARGINES.lewo + w}
                      y1={y(0)}
                      y2={y(0)}
                      stroke="var(--axis)"
                    />
                    {seria.map((p, i) =>
                      (i % Math.ceil(seria.length / 8) === 0 && seria.length - 1 - i >= Math.ceil(seria.length / 16)) ||
                      i === seria.length - 1 ? (
                        <text key={p.dzien} x={x(i)} y={WYSOKOSC - 6} textAnchor="middle">
                          {dataKrotka(p.dzien)}
                        </text>
                      ) : null,
                    )}
                  </g>
                  {aktywny !== null && (
                    <line
                      x1={x(aktywny)}
                      x2={x(aktywny)}
                      y1={MARGINES.gora}
                      y2={MARGINES.gora + h}
                      stroke="var(--axis)"
                    />
                  )}
                  {wycinek.zrodla.map((z) => (
                    <polyline
                      key={z}
                      fill="none"
                      stroke={`var(--${z})`}
                      strokeWidth={2}
                      strokeLinejoin="round"
                      strokeLinecap="round"
                      points={seria.map((p, i) => `${x(i)},${y(p.zrodla[z])}`).join(" ")}
                    />
                  ))}
                  {aktywny !== null &&
                    wycinek.zrodla.map((z) => (
                      <circle
                        key={z}
                        cx={x(aktywny)}
                        cy={y(seria[aktywny].zrodla[z])}
                        r={4}
                        fill={`var(--${z})`}
                        stroke="var(--surface)"
                        strokeWidth={2}
                      />
                    ))}
                  {etykiety.map((e) => (
                    <g key={e.z}>
                      <circle cx={x(seria.length - 1)} cy={e.y0} r={4} fill={`var(--${e.z})`} stroke="var(--surface)" strokeWidth={2} />
                      {Math.abs(e.y - e.y0) > 1 && (
                        <line x1={x(seria.length - 1) + 6} x2={x(seria.length - 1) + 12} y1={e.y0} y2={e.y} stroke="var(--axis)" />
                      )}
                      <text x={x(seria.length - 1) + 14} y={e.y - 2} fontSize={12} fill="var(--ink-2)">
                        {krotkaNazwa(e.z)}
                      </text>
                      <text x={x(seria.length - 1) + 14} y={e.y + 12} fontSize={12} fontWeight={600} fill="var(--ink)">
                        {zloteKrotko(e.v)}
                      </text>
                    </g>
                  ))}
                  <rect
                    x={MARGINES.lewo}
                    y={MARGINES.gora}
                    width={w}
                    height={h}
                    fill="transparent"
                    tabIndex={0}
                    aria-label="Najedź albo użyj strzałek, żeby zobaczyć kwoty z dnia"
                    onPointerMove={(ev) => {
                      const i = najblizszy(ev.clientX, ev.currentTarget.ownerSVGElement!);
                      ustawAktywny(i);
                      pokaz(ev, dymekDnia(i));
                    }}
                    onPointerLeave={() => {
                      ustawAktywny(null);
                      ukryj();
                    }}
                    onKeyDown={(ev) => {
                      if (ev.key !== "ArrowLeft" && ev.key !== "ArrowRight") return;
                      const i = Math.min(
                        seria.length - 1,
                        Math.max(0, (aktywny ?? seria.length - 1) + (ev.key === "ArrowRight" ? 1 : -1)),
                      );
                      ustawAktywny(i);
                      pokaz(ev.currentTarget, dymekDnia(i));
                    }}
                    onBlur={() => {
                      ustawAktywny(null);
                      ukryj();
                    }}
                  />
                </svg>
              )}
              <div className="legenda">
                {wycinek.zrodla.map((z) => (
                  <span key={z}>
                    <span className="klucz-linii" style={{ background: `var(--${z})` }} /> {nazwa(z)}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        <div style={{ marginTop: 24 }}>
          <h3>Która reguła zatrzymała ile przychodu</h3>
          {lista.length === 0 ? (
            <p className="drobne">W tym okresie żadna dostawa nie została zatrzymana.</p>
          ) : (
            <div className="przewijane">
              <table>
                <thead>
                  <tr>
                    <th>Reguła</th>
                    <th>Czego wymaga reguła (niespełnione)</th>
                    <th>Poprawia</th>
                    <th className="kwota">Zatrzymane dostawy</th>
                    <th className="kwota">Przychód zatrzymany</th>
                    <th className="kwota">W tym duplikaty</th>
                  </tr>
                </thead>
                <tbody>
                  {lista.map((p) => (
                    <tr key={p.regula.id}>
                      <td style={{ whiteSpace: "nowrap" }}>
                        <strong>{p.regula.id}</strong>
                      </td>
                      <td>{p.regula.opis}</td>
                      <td className="drobne">{p.regula.wlasciciel}</td>
                      <td className="kwota">{odmiana(p.dostawy, ["dzień", "dni", "dni"])}</td>
                      <td className="kwota">{zlote(p.wstrzymane)}</td>
                      <td className="kwota">{p.zawyzenie > 0 ? zlote(p.zawyzenie) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="drobne" style={{ marginTop: 8 }}>
            Dostawę może zatrzymać kilka reguł naraz; wtedy jej kwota jest przy każdej z nich, więc kwot w tej tabeli
            nie sumujemy. Łączna kwota jest w pierwszym kaflu na górze.
          </p>
        </div>
      </div>
    </section>
  );
}
