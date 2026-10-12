"use client";

import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";

export interface StanDymka {
  x: number;
  y: number;
  tresc: ReactNode;
}

export type PokazDymek = (cel: { clientX: number; clientY: number } | Element, tresc: ReactNode) => void;

/** Jeden dymek na cały panel: pokazuje go najechanie myszą albo fokus z klawiatury (te same treści). */
export function useDymek(): { dymek: StanDymka | null; pokaz: PokazDymek; ukryj: () => void } {
  const [dymek, ustaw] = useState<StanDymka | null>(null);
  const pokaz = useCallback<PokazDymek>((cel, tresc) => {
    if (cel instanceof Element) {
      const r = cel.getBoundingClientRect();
      ustaw({ x: r.right, y: r.bottom, tresc });
    } else {
      ustaw({ x: cel.clientX, y: cel.clientY, tresc });
    }
  }, []);
  const ukryj = useCallback(() => ustaw(null), []);
  useEffect(() => {
    const zamknij = (e: KeyboardEvent) => e.key === "Escape" && ustaw(null);
    window.addEventListener("keydown", zamknij);
    window.addEventListener("scroll", ukryj, { passive: true });
    return () => {
      window.removeEventListener("keydown", zamknij);
      window.removeEventListener("scroll", ukryj);
    };
  }, [ukryj]);
  return { dymek, pokaz, ukryj };
}

export function Dymek({ dymek }: { dymek: StanDymka | null }) {
  const ref = useRef<HTMLDivElement>(null);
  const [pozycja, ustawPozycje] = useState<{ left: number; top: number } | null>(null);
  useEffect(() => {
    if (!dymek || !ref.current) return;
    const { width, height } = ref.current.getBoundingClientRect();
    const left = Math.min(dymek.x + 14, window.innerWidth - width - 8);
    const top = dymek.y + 14 + height > window.innerHeight ? dymek.y - height - 10 : dymek.y + 14;
    ustawPozycje({ left: Math.max(8, left), top: Math.max(8, top) });
  }, [dymek]);
  if (!dymek) return null;
  return (
    <div
      ref={ref}
      className="dymek"
      role="tooltip"
      style={pozycja ? { left: pozycja.left, top: pozycja.top } : { left: -9999, top: -9999 }}
    >
      {dymek.tresc}
    </div>
  );
}

/** Szerokość elementu (dla wykresów SVG, które liczą skalę w pikselach). */
export function useSzerokosc<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [szerokosc, ustaw] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const obserwator = new ResizeObserver(([wpis]) => ustaw(Math.floor(wpis.contentRect.width)));
    obserwator.observe(ref.current);
    return () => obserwator.disconnect();
  }, []);
  return [ref, szerokosc];
}
