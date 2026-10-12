// Liczby i daty po polsku: 1 979 415,18 zł, 1,98 mln zł, 30.09, 30 września 2026.

const zl = new Intl.NumberFormat("pl-PL", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  useGrouping: "always",
});
const calkowita = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 0, useGrouping: "always" });
const krotka = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 2, minimumFractionDigits: 0 });
const procent = new Intl.NumberFormat("pl-PL", { style: "percent", maximumFractionDigits: 1 });

export const MINUS = "−";

function znak(tekst: string): string {
  return tekst.replace("-", MINUS);
}

/** 1 979 415,18 zł */
export function zlote(x: number): string {
  return znak(`${zl.format(x)} zł`);
}

/** 1,98 mln zł · 63,6 tys. zł · 950 zł */
export function zloteKrotko(x: number): string {
  const a = Math.abs(x);
  if (a >= 1_000_000) return znak(`${krotka.format(x / 1_000_000)} mln zł`);
  if (a >= 10_000) return znak(`${new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 1 }).format(x / 1000)} tys. zł`);
  return znak(`${calkowita.format(x)} zł`);
}

export function liczba(x: number): string {
  return znak(calkowita.format(x));
}

export function proc(x: number): string {
  return znak(procent.format(x));
}

const MIESIACE = [
  "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
  "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
];
const MIESIACE_MIANOWNIK = [
  "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
  "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
];
const DNI_TYGODNIA = ["niedziela", "poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota"];

function czesci(iso: string): [number, number, number] {
  const [r, m, d] = iso.slice(0, 10).split("-").map(Number);
  return [r, m, d];
}

/** 30.09 */
export function dataKrotka(iso: string): string {
  const [, m, d] = czesci(iso);
  return `${String(d).padStart(2, "0")}.${String(m).padStart(2, "0")}`;
}

/** 30 września 2026 */
export function dataDluga(iso: string): string {
  const [r, m, d] = czesci(iso);
  return `${d} ${MIESIACE[m - 1]} ${r}`;
}

/** środa, 30 września 2026 */
export function dataZDniem(iso: string): string {
  const [r, m, d] = czesci(iso);
  return `${DNI_TYGODNIA[new Date(Date.UTC(r, m - 1, d)).getUTCDay()]}, ${dataDluga(iso)}`;
}

/** wrzesień 2026 */
export function miesiac(iso: string): string {
  const [r, m] = czesci(iso);
  return `${MIESIACE_MIANOWNIK[m - 1]} ${r}`;
}

export function weekend(iso: string): boolean {
  const [r, m, d] = czesci(iso);
  const dzien = new Date(Date.UTC(r, m - 1, d)).getUTCDay();
  return dzien === 0 || dzien === 6;
}

/** „1 dzień”, „3 dni”. */
export function dni(n: number): string {
  return n === 1 ? "1 dzień" : `${n} dni`;
}

/** Odmiana: 1 dostawa, 2–4 dostawy, 5+ dostaw (też 12–14). */
export function odmiana(n: number, [jeden, kilka, wiele]: [string, string, string]): string {
  if (n === 1) return `1 ${jeden}`;
  const d = n % 10, s = n % 100;
  return `${liczba(n)} ${d >= 2 && d <= 4 && (s < 12 || s > 14) ? kilka : wiele}`;
}
