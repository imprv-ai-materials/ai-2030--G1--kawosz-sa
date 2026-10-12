import { dataKrotka, odmiana, zlote } from "./format";
import { kpi, type Wycinek, wnioski } from "./licz";
import type { DanePanelu } from "./typy";

/** „Najważniejsze”: po jednym zdaniu na system, ułożone z tych samych liczb co reszta panelu. */
export function Wnioski({ wycinek, dane }: { wycinek: Wycinek; dane: DanePanelu }) {
  const lista = wnioski(wycinek, dane.reguly);
  const nazwa = (id: string) => dane.zrodla.find((z) => z.id === id)?.nazwa ?? id;
  const { zawyzenie } = kpi(wycinek);
  const dniZawyzenia = wycinek.wsady.filter((w) => w.status === "kwarantanna" && (w.zawyzenie ?? 0) > 0);

  return (
    <section className="karta" aria-labelledby="wnioski">
      <h2 id="wnioski">Najważniejsze w tym okresie</h2>
      <ul className="wnioski">
        {lista.map((w) =>
          w.zatrzymane.length === 0 ? (
            <li key={w.zrodlo}>
              <strong>{nazwa(w.zrodlo)}:</strong> wszystkie {odmiana(w.wszystkie, ["dostawa", "dostawy", "dostaw"])}{" "}
              trafiły do raportów.
              {w.ostrzegajace > 0 && (
                <>
                  {" "}
                  {odmiana(w.ostrzegajace, ["reguła zgłasza", "reguły zgłaszają", "reguł zgłasza"])} ostrzeżenia: dane
                  idą dalej, a właściciel systemu dostaje listę do poprawy.
                </>
              )}
            </li>
          ) : (
            <li key={w.zrodlo}>
              <strong>{nazwa(w.zrodlo)}:</strong> zatrzymane {w.zatrzymane.length} z{" "}
              {odmiana(w.wszystkie, ["dostawy", "dostaw", "dostaw"])}, w raportach brakuje {zlote(w.wstrzymane)}.
              {w.glowna && (
                <>
                  {" "}
                  Najczęstszy powód ({odmiana(w.glowna.dostawy, ["dostawa", "dostawy", "dostaw"])}): niespełniona
                  reguła <strong>{w.glowna.regula.id}</strong> „{w.glowna.regula.opis}”. Poprawia:{" "}
                  {w.glowna.regula.wlasciciel}.
                </>
              )}
              {w.najwiekszy && w.zatrzymane.length > 1 && (
                <>
                  {" "}
                  Największa zatrzymana dostawa: {dataKrotka(w.najwiekszy.dzien)} ({zlote(w.najwiekszy.przychod_netto ?? 0)}
                  ).
                </>
              )}
            </li>
          ),
        )}
        {zawyzenie > 0 && (
          <li>
            <strong>Zatrzymane duplikaty:</strong> w dostawach z {dniZawyzenia.map((w) => dataKrotka(w.dzien)).join(", ")}{" "}
            były zdublowane dokumenty. Gdyby przeszły, raporty pokazałyby o {zlote(zawyzenie)} za dużo.
          </li>
        )}
      </ul>
    </section>
  );
}
