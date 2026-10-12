import { miesiac, odmiana, proc, zlote, zloteKrotko } from "./format";
import type { Kpi } from "./licz";
import type { DanePanelu } from "./typy";

export function ostatniMost(dane: DanePanelu) {
  const miesiace = [...new Set(dane.most.map((k) => k.miesiac))].sort();
  const ostatni = miesiace.at(-1);
  if (!ostatni) return null;
  const kroki = dane.most.filter((k) => k.miesiac === ostatni);
  return {
    miesiac: ostatni,
    reszta: kroki.find((k) => k.krok === "Niewyjaśniona reszta")?.kwota_pln ?? 0,
    netto: kroki.find((k) => k.krok === "Przychód netto")?.kwota_pln ?? 0,
  };
}

export function Kafle({ liczby, dane }: { liczby: Kpi; dane: DanePanelu }) {
  const razem = liczby.wstrzymane + liczby.opublikowane;
  const most = ostatniMost(dane);
  return (
    <section className="kafle" aria-label="Najważniejsze liczby">
      <div className="kafel glowny">
        <span className="etykieta">Przychód zatrzymany w kwarantannie</span>
        <span className="wartosc">{zloteKrotko(liczby.wstrzymane)}</span>
        <span className="opis">
          {zlote(liczby.wstrzymane)}: {liczby.dostawWstrzymanych} z{" "}
          {odmiana(liczby.dostaw, ["dostawy", "dostaw", "dostaw"])} zatrzymane
          {razem > 0 && <>, czyli {proc(liczby.wstrzymane / razem)} przychodu z okresu, którego nie ma w raportach</>}.
        </span>
      </div>
      <div className="kafel">
        <span className="etykieta">Przychód, który trafił do raportów</span>
        <span className="wartosc">{zloteKrotko(liczby.opublikowane)}</span>
        <span className="opis">{zlote(liczby.opublikowane)} z dostaw, które przeszły kontrolę.</span>
      </div>
      <div className="kafel">
        <span className="etykieta">Zawyżenie zatrzymane przed raportami</span>
        <span className="wartosc">{zloteKrotko(liczby.zawyzenie)}</span>
        <span className="opis">
          Zdublowane dokumenty (np. kopia pliku z kasy), które w raporcie policzyłyby się dwa razy.
        </span>
      </div>
      <div className="kafel">
        <span className="etykieta">Niewyjaśniona reszta mostu{most ? `, ${miesiac(most.miesiac)}` : ""}</span>
        <span className="wartosc">{most ? zlote(most.reszta) : "brak"}</span>
        <span className="opis">
          {most
            ? most.reszta === 0
              ? "Most się domyka: każdą złotówkę różnicy między BI a przychodem netto tłumaczy któraś reguła."
              : `${proc(most.reszta / most.netto)} przychodu netto miesiąca: różnica, której nie tłumaczy żadna reguła.`
            : "Most przychodu nie był jeszcze liczony."}
        </span>
      </div>
    </section>
  );
}
