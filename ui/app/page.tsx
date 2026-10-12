import type { Metadata } from "next";

import Panel from "./panel/Panel";
import type { DanePanelu } from "./panel/typy";

export const metadata: Metadata = {
  title: "Jakość danych przychodu",
  description: "Nocna kontrola danych przychodu: dostawy, kwarantanna, koszt błędów i most przychodu.",
};

// Dane zmieniają się co noc: zawsze świeże z API, bez cache.
export const dynamic = "force-dynamic";

const API = process.env.KAWOSZ_API ?? "http://127.0.0.1:8101";

async function pobierz(): Promise<{ dane: DanePanelu } | { blad: string; szczegoly: string }> {
  try {
    const odpowiedz = await fetch(`${API}/api/jakosc?dni=30`, { cache: "no-store" });
    if (!odpowiedz.ok) {
      const tresc = await odpowiedz.json().catch(() => null);
      return {
        blad: odpowiedz.status === 503 ? "Dane są właśnie aktualizowane." : "Panel nie ma jeszcze danych.",
        szczegoly: tresc?.detail ?? `API odpowiedziało kodem ${odpowiedz.status}.`,
      };
    }
    return { dane: (await odpowiedz.json()) as DanePanelu };
  } catch {
    return {
      blad: "Panel nie może teraz pobrać danych.",
      szczegoly: `Brak połączenia z API pod adresem ${API}. Zespół danych uruchamia je poleceniem: pypyr start_api.`,
    };
  }
}

export default async function Strona() {
  const wynik = await pobierz();
  if ("blad" in wynik)
    return (
      <main>
        <h1>Jakość danych przychodu</h1>
        <p className="ostrzezenie blad-ladowania">
          <strong>{wynik.blad}</strong> Spróbuj odświeżyć stronę za kilka minut. Jeśli to nie pomoże, przekaż ten
          komunikat zespołowi danych: {wynik.szczegoly}
        </p>
      </main>
    );
  return <Panel dane={wynik.dane} />;
}
