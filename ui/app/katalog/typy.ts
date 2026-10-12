// Kształt odpowiedzi GET /api/katalog (api/api/ai/features/katalog.py).

export interface PsiCechy {
  t0: string; // ostatni tydzień z pomiarem
  psi: number;
  alert: boolean; // psi > próg
  alerty: number; // tygodnie z alertem wśród ostatnich `tygodnie`
  tygodnie: number;
}

export interface KartaCechy {
  cecha: string;
  rodzina: string;
  opis: string;
  sql: string; // względem api/api/ai/features/
  system: string;
  tabele: string[];
  okno: string;
  opoznienie: string;
  wlasciciel: string;
  wersja: string;
  modele: string[]; // wyliczone z wersji w ai/churn_model/versions/
  psi: PsiCechy | null;
}

export interface WersjaModelu {
  wersja: string;
  z_katalogu: boolean; // czy liczy cechy plikami z ai/features/sql/
  cechy: number;
}

export interface DaneKatalogu {
  karty: KartaCechy[];
  rodziny: string[];
  wersje: WersjaModelu[];
  pominiete: { cecha: string; powod: string }[];
  psi_t0: string | null;
  psi_prog: number;
  psi_tygodnie: number;
  baza: string;
}
