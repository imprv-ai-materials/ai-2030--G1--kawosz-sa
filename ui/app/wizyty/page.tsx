import type { Metadata } from "next";

import Kalkulator from "./Kalkulator";
import type { WynikKalkulatora } from "./typy";

export const metadata: Metadata = {
  title: "Kalkulator wizyt",
  description: "Do których biur wysłać opiekuna: próg ryzyka, lista biur, zysk i krzywa wartości dla własnych założeń.",
};

// Lista biur zmienia się co noc, a założenia z kodem: zawsze świeże z API, bez cache.
export const dynamic = "force-dynamic";

const API = process.env.KAWOSZ_API ?? "http://127.0.0.1:8101";

// Link z założeniami (?s=0.3&V=24192&C=1260&budzet=60&kontrola=0.1) otwiera kalkulator od razu z nimi.
const PARAMETRY = ["s", "V", "C", "budzet", "kontrola"];

type Szukane = Record<string, string | string[] | undefined>;

async function pobierz(szukane: Szukane): Promise<{ dane: WynikKalkulatora } | { blad: string; szczegoly: string }> {
  const zapytanie = new URLSearchParams();
  for (const klucz of PARAMETRY) {
    const wartosc = szukane[klucz];
    if (typeof wartosc === "string" && wartosc !== "") zapytanie.set(klucz, wartosc);
  }
  try {
    const odpowiedz = await fetch(`${API}/api/wizyty?${zapytanie}`, { cache: "no-store" });
    if (!odpowiedz.ok) {
      const tresc = await odpowiedz.json().catch(() => null);
      return {
        blad:
          odpowiedz.status === 503
            ? "Dane są właśnie aktualizowane."
            : odpowiedz.status === 422
              ? "Link ma niepoprawne założenia."
              : "Kalkulator nie ma jeszcze danych.",
        szczegoly: tresc?.detail ?? `API odpowiedziało kodem ${odpowiedz.status}.`,
      };
    }
    return { dane: (await odpowiedz.json()) as WynikKalkulatora };
  } catch {
    return {
      blad: "Kalkulator nie może teraz pobrać danych.",
      szczegoly: `Brak połączenia z API pod adresem ${API}. Zespół danych uruchamia je poleceniem: pypyr start_api.`,
    };
  }
}

export default async function Strona({ searchParams }: { searchParams: Promise<Szukane> }) {
  const wynik = await pobierz(await searchParams);
  if ("blad" in wynik)
    return (
      <main>
        <h1>Kalkulator wizyt opiekunów</h1>
        <p className="ostrzezenie blad-ladowania">
          <strong>{wynik.blad}</strong> Spróbuj odświeżyć stronę za kilka minut. Jeśli to nie pomoże, przekaż ten
          komunikat zespołowi danych: {wynik.szczegoly}
        </p>
      </main>
    );
  return <Kalkulator start={wynik.dane} />;
}
