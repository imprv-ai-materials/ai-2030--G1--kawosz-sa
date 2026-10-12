// Agregaty panelu liczone z odpowiedzi API: niczego nie dopowiadamy, tylko sumujemy to, co zapisała noc.
import type { DanePanelu, Naruszenie, Regula, Wsad } from "./typy";

export const WSZYSTKIE = "wszystkie";

export function dniOkresu(doDnia: string, ile: number): string[] {
  const [r, m, d] = doDnia.split("-").map(Number);
  const koniec = Date.UTC(r, m - 1, d);
  return Array.from({ length: ile }, (_, i) =>
    new Date(koniec - (ile - 1 - i) * 86_400_000).toISOString().slice(0, 10),
  );
}

export interface Wycinek {
  dni: string[];
  zrodla: string[];
  wsady: Wsad[];
  naruszenia: Naruszenie[];
}

export function wytnij(dane: DanePanelu, ileDni: number, zrodlo: string): Wycinek {
  const dni = dniOkresu(dane.do, ileDni);
  const od = dni[0];
  const zrodla = zrodlo === WSZYSTKIE ? dane.zrodla.map((z) => z.id) : [zrodlo];
  return {
    dni,
    zrodla,
    wsady: dane.wsady.filter((w) => w.dzien >= od && zrodla.includes(w.zrodlo)),
    naruszenia: dane.naruszenia.filter((n) => n.dzien >= od && zrodla.includes(n.zrodlo)),
  };
}

const kwota = (x: number | null) => x ?? 0;

export interface Kpi {
  wstrzymane: number;
  opublikowane: number;
  zawyzenie: number;
  dostawWstrzymanych: number;
  dostaw: number;
  bezWyceny: number;
}

export function kpi(w: Wycinek): Kpi {
  const zatrzymane = w.wsady.filter((x) => x.status === "kwarantanna");
  return {
    wstrzymane: zatrzymane.reduce((s, x) => s + kwota(x.przychod_netto), 0),
    opublikowane: w.wsady.filter((x) => x.status === "opublikowany").reduce((s, x) => s + kwota(x.przychod_netto), 0),
    zawyzenie: zatrzymane.reduce((s, x) => s + kwota(x.zawyzenie), 0),
    dostawWstrzymanych: zatrzymane.length,
    dostaw: w.wsady.length,
    bezWyceny: w.wsady.filter((x) => x.przychod_netto === null).length,
  };
}

/** Przychód netto zatrzymany w kwarantannie narastająco: dzień → źródło → suma od początku okresu. */
export function narastajaco(w: Wycinek): { dzien: string; zrodla: Record<string, number>; dnia: Record<string, number> }[] {
  const suma: Record<string, number> = Object.fromEntries(w.zrodla.map((z) => [z, 0]));
  return w.dni.map((dzien) => {
    const dnia: Record<string, number> = {};
    for (const z of w.zrodla) {
      const wsad = w.wsady.find((x) => x.dzien === dzien && x.zrodlo === z);
      dnia[z] = wsad?.status === "kwarantanna" ? kwota(wsad.przychod_netto) : 0;
      suma[z] += dnia[z];
    }
    return { dzien, zrodla: { ...suma }, dnia };
  });
}

export interface PrzyczynaKosztu {
  regula: Regula;
  dostawy: number;
  wstrzymane: number;
  zawyzenie: number;
  dni: string[];
}

/** Reguły blokujące, które zatrzymały dostawy w okresie, z kwotą zatrzymanego przychodu (dostawa zatrzymana
 *  przez kilka reguł liczy się przy każdej z nich). */
export function przyczyny(w: Wycinek, reguly: Regula[]): PrzyczynaKosztu[] {
  const wynik = new Map<string, PrzyczynaKosztu>();
  for (const wsad of w.wsady.filter((x) => x.status === "kwarantanna")) {
    for (const id of wsad.blokujace) {
      const regula = reguly.find((r) => r.id === id);
      if (!regula) continue;
      const p = wynik.get(id) ?? { regula, dostawy: 0, wstrzymane: 0, zawyzenie: 0, dni: [] };
      p.dostawy += 1;
      p.wstrzymane += kwota(wsad.przychod_netto);
      p.zawyzenie += kwota(wsad.zawyzenie);
      p.dni.push(wsad.dzien);
      wynik.set(id, p);
    }
  }
  return [...wynik.values()].sort((a, b) => b.wstrzymane - a.wstrzymane || b.dostawy - a.dostawy);
}

export interface WierszMapy {
  regula: Regula;
  dni: Record<string, Naruszenie>;
  dniZNaruszeniem: number;
  rekordy: number;
}

/** Reguły z naruszeniem w okresie (najpierw blokujące), z wynikiem każdego dnia; reszta osobno. */
export function mapaNaruszen(w: Wycinek, reguly: Regula[]): { z: WierszMapy[]; bez: Regula[] } {
  const wiersze: WierszMapy[] = [];
  const bez: Regula[] = [];
  for (const regula of reguly.filter((r) => w.zrodla.includes(r.zrodlo))) {
    const dni: Record<string, Naruszenie> = {};
    for (const n of w.naruszenia) if (n.regula === regula.id) dni[n.dzien] = n;
    const zle = Object.values(dni).filter((n) => n.bledne > 0 || n.blad);
    if (zle.length === 0) bez.push(regula);
    else
      wiersze.push({
        regula,
        dni,
        dniZNaruszeniem: zle.length,
        rekordy: zle.reduce((s, n) => s + n.bledne, 0),
      });
  }
  const waga = (p: string) => (p === "blokuje" ? 0 : 1);
  wiersze.sort(
    (a, b) =>
      waga(a.regula.poziom) - waga(b.regula.poziom) ||
      b.dniZNaruszeniem - a.dniZNaruszeniem ||
      a.regula.id.localeCompare(b.regula.id),
  );
  return { z: wiersze, bez };
}

/** Klasa skali dla liczby rekordów z naruszeniem: 0, 1, 2–9, 10–99, 100–999, ≥ 1000. */
export function klasa(bledne: number): number {
  if (bledne <= 0) return 0;
  if (bledne === 1) return 1;
  if (bledne < 10) return 2;
  if (bledne < 100) return 3;
  if (bledne < 1000) return 4;
  return 5;
}

export const KLASY = ["brak", "1", "2–9", "10–99", "100–999", "1000 i więcej"];

export interface Wniosek {
  zrodlo: string;
  zatrzymane: Wsad[];
  wszystkie: number;
  wstrzymane: number;
  glowna: PrzyczynaKosztu | null;
  najwiekszy: Wsad | null;
  ostrzegajace: number;
}

export function wnioski(w: Wycinek, reguly: Regula[]): Wniosek[] {
  return w.zrodla.map((zrodlo) => {
    const wsady = w.wsady.filter((x) => x.zrodlo === zrodlo);
    const zatrzymane = wsady.filter((x) => x.status === "kwarantanna");
    const tylko = { ...w, zrodla: [zrodlo], wsady };
    const glowna = [...przyczyny(tylko, reguly)].sort((a, b) => b.dostawy - a.dostawy || b.wstrzymane - a.wstrzymane)[0];
    const najwiekszy = [...zatrzymane].sort((a, b) => kwota(b.przychod_netto) - kwota(a.przychod_netto))[0] ?? null;
    const ostrzegajace = new Set(
      w.naruszenia
        .filter((n) => n.zrodlo === zrodlo && n.bledne > 0)
        .map((n) => n.regula)
        .filter((id) => reguly.find((r) => r.id === id)?.poziom === "ostrzega"),
    ).size;
    return {
      zrodlo,
      zatrzymane,
      wszystkie: wsady.length,
      wstrzymane: zatrzymane.reduce((s, x) => s + kwota(x.przychod_netto), 0),
      glowna: glowna ?? null,
      najwiekszy,
      ostrzegajace,
    };
  });
}
