import type { Metadata } from "next";

import Katalog from "./Katalog";
import type { DaneKatalogu } from "./typy";

export const metadata: Metadata = {
  title: "Katalog cech",
  description: "Karty cech modelu churnu: definicja, źródło, okno, opóźnienie, właściciel, modele i ostatnie PSI.",
};

// Karty zmieniają się z kodem, a PSI co tydzień: zawsze świeże z API, bez cache.
export const dynamic = "force-dynamic";

const API = process.env.KAWOSZ_API ?? "http://127.0.0.1:8101";

async function pobierz(): Promise<{ dane: DaneKatalogu } | { blad: string; szczegoly: string }> {
  try {
    const odpowiedz = await fetch(`${API}/api/katalog`, { cache: "no-store" });
    if (!odpowiedz.ok) {
      const tresc = await odpowiedz.json().catch(() => null);
      return {
        blad: odpowiedz.status === 503 ? "Dane są właśnie aktualizowane." : "Katalog nie ma jeszcze danych.",
        szczegoly: tresc?.detail ?? `API odpowiedziało kodem ${odpowiedz.status}.`,
      };
    }
    return { dane: (await odpowiedz.json()) as DaneKatalogu };
  } catch {
    return {
      blad: "Katalog nie może teraz pobrać danych.",
      szczegoly: `Brak połączenia z API pod adresem ${API}. Zespół danych uruchamia je poleceniem: pypyr start_api.`,
    };
  }
}

export default async function Strona() {
  const wynik = await pobierz();
  if ("blad" in wynik)
    return (
      <main>
        <h1>Katalog cech</h1>
        <p className="ostrzezenie blad-ladowania">
          <strong>{wynik.blad}</strong> Spróbuj odświeżyć stronę za kilka minut. Jeśli to nie pomoże, przekaż ten
          komunikat zespołowi danych: {wynik.szczegoly}
        </p>
      </main>
    );
  return <Katalog dane={wynik.dane} />;
}
