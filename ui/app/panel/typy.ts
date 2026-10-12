// Kształt odpowiedzi GET /api/jakosc (api/api/data_platform/panel_jakosci.py).

export type Status = "opublikowany" | "kwarantanna";
export type Poziom = "blokuje" | "ostrzega";

export interface Zrodlo {
  id: string;
  nazwa: string;
  opis: string;
}

export interface Wsad {
  dzien: string;
  zrodlo: string;
  status: Status;
  blokujace: string[];
  przychod_netto: number | null; // przychód netto według definicji, który niesie dostawa
  zawyzenie: number | null; // o ile duplikaty z dostawy zawyżyłyby przychód
  wycena_uwaga: string | null;
  raport: string | null;
  wiersze: number;
  zapisano: string;
}

export interface Naruszenie {
  dzien: string;
  zrodlo: string;
  regula: string;
  sprawdzone: number;
  bledne: number;
  blad: string | null;
}

export interface Regula {
  id: string;
  zrodlo: string;
  opis: string;
  poziom: Poziom;
  wlasciciel: string;
  jednostka: string;
  co_zrobic: string;
}

export interface KrokMostu {
  miesiac: string;
  krok: string;
  opis: string;
  kwota_pln: number;
  suma_po_kroku: number;
}

export interface DanePanelu {
  baza: string;
  od: string;
  do: string;
  dni: number;
  zrodla: Zrodlo[];
  reguly: Regula[];
  wsady: Wsad[];
  naruszenia: Naruszenie[];
  most: KrokMostu[];
}
