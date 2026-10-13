// Kształt odpowiedzi GET /api/wizyty (api/api/contexts_boundaries/retention_bc/prog/kalkulator.py).

export type KluczSuwaka = "V" | "C" | "s" | "budzet_wizyt";

export interface Suwak {
  klucz: KluczSuwaka;
  opis: string;
  jednostka: string;
  wartosc: number;
  przedzial: [number, number] | null;
  min: number;
  max: number;
  krok: number;
  wlasciciel: string;
  rachunek: string | null;
  otwarte: string[];
}

export type Zalozenia = Record<KluczSuwaka, number>;

export interface Biuro {
  id_biura: number;
  nazwa: string | null;
  miasto: string | null;
  opiekun: string | null;
  p: number;
  wartosc_wizyty: number;
  grupa: "wizyta" | "kontrola";
  /** do 3 powodów ryzyka prostym językiem, od najważniejszego */
  powody: string[];
}

/** Grupa kontrolna: udział listy losowo bez wizyty, żeby za kwartał zmierzyć skuteczność wizyty. */
export interface Kontrola {
  udzial: number;
  kwartal: string;
  biura: number;
  koszt: number;
  odejscia_bez_wizyty: number | null;
  /** połowa 90% przedziału zmierzonego s po 1, 4 i 8 kwartałach; null, gdy nie da się policzyć */
  przedzial_90: Record<"1" | "4" | "8", number> | null;
}

export interface PunktKrzywej {
  prog: number;
  wizyty_dzis: number;
  zysk_oczekiwany_dzis: number;
  wizyty_historia: number;
  zysk_historia: number;
}

export interface WynikKalkulatora {
  suwaki: Suwak[];
  /** udział grupy kontrolnej z zalozenia.yaml: od niego startuje przełącznik */
  kontrola_startowa: number;
  model: string;
  dzis: string;
  baza: string;
  zalozenia: Zalozenia;
  prog: number;
  zysk_trafionej: number;
  biura_dzis: number;
  max_p: number;
  nad_progiem: number;
  zysk_oczekiwany_nad_progiem: number;
  lista: Biuro[];
  zysk_oczekiwany: number;
  kontrola: Kontrola;
  historia: { snapszoty: number; od: string; do: string; wizyty: number; zysk: number };
  krzywa: PunktKrzywej[];
}
