import { liczba, odmiana, proc, zlote } from "../panel/format";
import type { WynikKalkulatora } from "./typy";

const OKRESY: { klucz: "1" | "4" | "8"; nazwa: string }[] = [
  { klucz: "1", nazwa: "po kwartale" },
  { klucz: "4", nazwa: "po roku" },
  { klucz: "8", nazwa: "po dwóch latach" },
];

/** ±12 pp: połowa przedziału w punktach procentowych. */
function pp(x: number): string {
  return `±${liczba(Math.round(x * 100))} pp`;
}

function srednieP(w: WynikKalkulatora, grupa: "wizyta" | "kontrola"): number {
  const biura = w.lista.filter((b) => b.grupa === grupa);
  return biura.reduce((suma, b) => suma + b.p, 0) / (biura.length || 1);
}

export function Kontrola({ w }: { w: WynikKalkulatora }) {
  const k = w.kontrola;
  const wizyty = w.lista.length - k.biura;
  const s = w.zalozenia.s;
  return (
    <section className="karta" aria-labelledby="kontrola">
      <h2 id="kontrola">Pomiar skuteczności wizyty</h2>
      {k.biura === 0 ? (
        <p className="lead">
          W kwartale {k.kwartal} los nie przydzielił do grupy kontrolnej żadnego biura z tej listy. Każde biuro trafia
          do niej z prawdopodobieństwem {proc(k.udzial)}, więc przy krótkiej liście to się zdarza.
        </p>
      ) : (
        <>
          <p className="lead">
            {odmiana(k.biura, ["biuro", "biura", "biur"])} z listy nie dostaje w tym kwartale wizyty ani rabatu,{" "}
            {odmiana(wizyty, ["biuro dostaje", "biura dostają", "biur dostaje"])} wizytę. Za 90 dni porównujemy
            odejścia: s = 1 − odsetek odejść z wizytą / odsetek odejść bez wizyty.
          </p>
          <div className="kafle kafle-kontroli">
            <div className="kafel">
              <span className="etykieta">Koszt grupy kontrolnej w tym kwartale</span>
              <span className="wartosc">{zlote(k.koszt)}</span>
              <span className="opis">
                Według modelu: tyle dałyby wizyty, których nie robimy (suma p × s × V − C).
              </span>
            </div>
            <div className="kafel">
              <span className="etykieta">Czy grupy są porównywalne</span>
              <span className="wartosc">
                {proc(srednieP(w, "wizyta"))} / {proc(srednieP(w, "kontrola"))}
              </span>
              <span className="opis">
                Średnie ryzyko odejścia: z wizytą / bez wizyty. Przy kilku biurach w kontroli te liczby mogą się
                różnić przez przypadek; wyrównują się z kolejnymi kwartałami.
              </span>
            </div>
            <div className="kafel">
              <span className="etykieta">Dokładność zmierzonego s (90%)</span>
              {k.przedzial_90 ? (
                <>
                  <span className="wartosc">{pp(k.przedzial_90["1"])}</span>
                  <span className="opis">
                    Po jednym kwartale. Dziś zakładamy s = 20–40%, czyli ±10 pp wokół 30%.
                  </span>
                </>
              ) : (
                <span className="opis">
                  Nie da się policzyć przy s = {proc(s)}: rachunek wymaga s między 0 a 100% i odejść na liście
                  w historii.
                </span>
              )}
            </div>
          </div>

          {k.przedzial_90 && (
            <>
              <h3 style={{ marginTop: 20 }}>Ile kwartałów trzeba zbierać</h3>
              <div className="przewijane">
                <table>
                  <thead>
                    <tr>
                      <th>Eksperyment trwa</th>
                      <th className="kwota">Biur bez wizyty łącznie</th>
                      <th className="kwota">90% przedział zmierzonego s</th>
                      <th className="kwota">Koszt kontroli łącznie</th>
                    </tr>
                  </thead>
                  <tbody>
                    {OKRESY.map(({ klucz, nazwa }) => (
                      <tr key={klucz}>
                        <td>{nazwa}</td>
                        <td className="kwota">{liczba(k.biura * Number(klucz))}</td>
                        <td className="kwota">
                          {proc(s)} {pp(k.przedzial_90![klucz])}
                        </td>
                        <td className="kwota">{zlote(k.koszt * Number(klucz))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="drobne" style={{ marginTop: 8 }}>
                Rachunek zakłada co kwartał podobną listę i podobny podział, s = {proc(s)} i odsetek odejść bez wizyty
                taki jak w historii: {k.odejscia_bez_wizyty === null ? "—" : proc(k.odejscia_bez_wizyty)} biur
                z listy odchodziło w 90 dni. W historii były już wizyty retencyjne, więc bez wizyty odchodzi raczej
                więcej. Większy udział kontroli zwęża przedział, ale kosztuje więcej. Najwięcej daje czas: wyniki
                z kolejnych kwartałów sumujemy.
              </p>
            </>
          )}

          <h3 style={{ marginTop: 20 }}>Jak przeprowadzić pomiar</h3>
          <ol className="wnioski">
            <li>
              <strong>Eksperyment prowadzi poniedziałkowa lista opiekunów.</strong> Co tydzień zapisuje w tabeli{" "}
              <code>lista_wizyt</code>, które biura są do odwiedzenia, a które w kontroli. Każde biuro ma w kwartale{" "}
              {k.kwartal} stały los, więc kalkulator pokazuje w kontroli te same biura co lista, a biuro z kontroli
              zostaje w niej do końca kwartału. Kalkulator służy do oceny kosztu i dokładności.
            </li>
            <li>
              <strong>Biura z kontroli zostają bez wizyty i bez rabatu przez cały kwartał.</strong> Nie zastępuj ich
              innymi biurami z budżetu: zepsułoby to porównanie.
            </li>
            <li>
              <strong>Za 90 dni porównaj odejścia w obu grupach</strong> i dopisz wynik do poprzednich kwartałów.
              Wynik z jednego kwartału to za mało, żeby zmieniać s w <code>zalozenia.yaml</code>.
            </li>
          </ol>
        </>
      )}
    </section>
  );
}
