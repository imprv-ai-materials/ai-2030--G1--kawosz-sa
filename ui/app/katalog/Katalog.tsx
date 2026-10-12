"use client";

import { useMemo, useState } from "react";

import { dataDluga, dataKrotka, odmiana } from "../panel/format";
import type { DaneKatalogu, KartaCechy, PsiCechy } from "./typy";

const WSZYSTKIE = "wszystkie";
const NAZWY_RODZIN: Record<string, string> = {
  umowa: "Umowa",
  uzycie: "Użycie ekspresów",
  zamowienia: "Zamówienia",
  platnosci: "Płatności",
  serwis: "Serwis",
  relacja: "Relacja z opiekunem",
  firmografia: "Firmografia",
};

const dwaMiejsca = new Intl.NumberFormat("pl-PL", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function rodzina(id: string): string {
  return NAZWY_RODZIN[id] ?? id;
}

export default function Katalog({ dane }: { dane: DaneKatalogu }) {
  const [wybranaRodzina, ustawRodzine] = useState(WSZYSTKIE);
  const [tylkoAlerty, ustawTylkoAlerty] = useState(false);

  const karty = useMemo(
    () =>
      dane.karty.filter(
        (k) => (wybranaRodzina === WSZYSTKIE || k.rodzina === wybranaRodzina) && (!tylkoAlerty || k.psi?.alert),
      ),
    [dane.karty, wybranaRodzina, tylkoAlerty],
  );
  const zAlertem = dane.karty.filter((k) => k.psi?.alert).length;
  const modeleKatalogu = dane.wersje.filter((w) => w.z_katalogu);
  const poza = dane.wersje.filter((w) => !w.z_katalogu);

  return (
    <main>
      <header>
        <h1>Katalog cech</h1>
        <p className="lead">
          Cechy, z których model przewiduje, czy biuro odejdzie w ciągu 90 dni. Każda karta mówi, co cecha znaczy, skąd
          bierze dane, z jakiego okresu i z jakim opóźnieniem, kto za nią odpowiada i które modele jej używają. Karty
          leżą w repozytorium obok kodu, który liczy cechy, i zmieniają się razem z nim.
        </p>
        <p className="drobne">
          {dane.psi_t0
            ? `Stabilność (PSI) z tygodnia od ${dataDluga(dane.psi_t0)}: rozkład cechy w tym tygodniu w porównaniu ze zbiorem, na którym uczył się model.`
            : "Stabilności (PSI) jeszcze nie mierzono: cotygodniowe sprawdzanie nie zapisało wyników."}
        </p>
      </header>

      <section className="kafle" aria-label="Najważniejsze liczby">
        <div className="kafel">
          <span className="etykieta">Cechy w katalogu</span>
          <span className="wartosc">{dane.karty.length}</span>
          <span className="opis">{odmiana(dane.rodziny.length, ["rodzina", "rodziny", "rodzin"])}, po jednym pliku SQL.</span>
        </div>
        <div className="kafel">
          <span className="etykieta">Cechy powyżej progu PSI</span>
          <span className="wartosc">{dane.psi_t0 ? zAlertem : "brak"}</span>
          <span className="opis">
            {dane.psi_t0
              ? `PSI powyżej ${dwaMiejsca.format(dane.psi_prog)} w tygodniu od ${dataKrotka(dane.psi_t0)}: rozkład odjechał od treningu.`
              : "Brak pomiaru PSI."}
          </span>
        </div>
        <div className="kafel">
          <span className="etykieta">Modele na cechach z katalogu</span>
          <span className="wartosc">{modeleKatalogu.length}</span>
          <span className="opis">{modeleKatalogu.map((w) => w.wersja).join(", ") || "Żaden model."}</span>
        </div>
        <div className="kafel">
          <span className="etykieta">Wersje z cechami spoza katalogu</span>
          <span className="wartosc">{poza.length}</span>
          <span className="opis">Liczą cechy innym kodem, więc karty ich nie opisują (lista na dole strony).</span>
        </div>
      </section>

      <div className="filtry" role="group" aria-label="Filtry katalogu">
        <div className="filtr-przewijany">
          <span className="etykieta-filtra">Rodzina</span>
          <span className="przelacznik">
            <button aria-pressed={wybranaRodzina === WSZYSTKIE} onClick={() => ustawRodzine(WSZYSTKIE)}>
              wszystkie
            </button>
            {dane.rodziny.map((r) => (
              <button key={r} aria-pressed={wybranaRodzina === r} onClick={() => ustawRodzine(r)}>
                {rodzina(r)}
              </button>
            ))}
          </span>
        </div>
        <div>
          <span className="etykieta-filtra">PSI</span>
          <span className="przelacznik">
            <button aria-pressed={!tylkoAlerty} onClick={() => ustawTylkoAlerty(false)}>
              wszystkie
            </button>
            <button aria-pressed={tylkoAlerty} onClick={() => ustawTylkoAlerty(true)} disabled={!dane.psi_t0}>
              powyżej progu
            </button>
          </span>
        </div>
        <span className="drobne">{odmiana(karty.length, ["cecha", "cechy", "cech"])}</span>
      </div>

      <div className="siatka-kart">
        {karty.map((k) => (
          <Karta key={k.cecha} karta={k} prog={dane.psi_prog} />
        ))}
        {karty.length === 0 && <p className="drobne">Żadna cecha nie pasuje do filtrów.</p>}
      </div>

      <section className="karta" aria-labelledby="modele">
        <h2 id="modele">Wersje modelu</h2>
        <p className="lead" style={{ marginBottom: 14 }}>
          Lista modeli na kartach nie jest wpisywana ręcznie. Wylicza ją kod z wersji w repozytorium: wersja korzysta z
          katalogu, gdy jej model bierze cechy z plików SQL katalogu, a jej cechy to te, na których model został
          nauczony. Starsze wersje mają cechy o tych samych nazwach, ale liczone inaczej (np. bez opóźnień danych).
        </p>
        <div className="przewijane">
          <table>
            <thead>
              <tr>
                <th>Wersja</th>
                <th>Cechy</th>
                <th className="kwota">Liczba cech</th>
              </tr>
            </thead>
            <tbody>
              {dane.wersje.map((w) => (
                <tr key={w.wersja}>
                  <td>
                    <code>{w.wersja}</code>
                  </td>
                  <td>
                    {w.z_katalogu ? (
                      <span className="status ok">
                        <span className="znacznik ok" aria-hidden="true">
                          ✓
                        </span>
                        z katalogu
                      </span>
                    ) : (
                      <span className="drobne">liczone innym kodem, poza katalogiem</span>
                    )}
                  </td>
                  <td className="kwota">{w.cechy}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="karta" aria-labelledby="slowniczek-katalogu">
        <h2 id="slowniczek-katalogu">Słowniczek</h2>
        <dl className="slowniczek">
          <div>
            <dt>t0</dt>
            <dd>
              Dzień, na którego początek liczymy cechę. Model widzi tylko dane, które dotarły do firmy przed t0, tak jak
              w dniu, w którym ocenia biura.
            </dd>
          </div>
          <div>
            <dt>Okno</dt>
            <dd>Z jakiego okresu przed t0 cecha bierze dane, np. „od t0 − 32 do t0 − 3” to 30 dni.</dd>
          </div>
          <div>
            <dt>Opóźnienie</dt>
            <dd>
              Ile czasu dane potrzebują, żeby dotrzeć z systemu źródłowego. Rekordy z ostatnich dni przed t0 jeszcze
              nie dotarły, więc okno kończy się wcześniej niż t0.
            </dd>
          </div>
          <div>
            <dt>PSI</dt>
            <dd>
              Wskaźnik stabilności: jak bardzo rozkład cechy w danym tygodniu różni się od zbioru, na którym uczył się
              model. 0 to brak różnicy, powyżej {dwaMiejsca.format(dane.psi_prog)} rozkład odjechał i warto sprawdzić,
              czy zmieniły się biura, czy dane.
            </dd>
          </div>
          <div>
            <dt>Wersja cechy</dt>
            <dd>
              Rośnie przy każdej zmianie definicji. Zmiana pierwszej liczby (np. 2.0.0) oznacza inne wartości cechy, więc
              modele na niej uczone trzeba przeliczyć.
            </dd>
          </div>
          <div>
            <dt>Właściciel</dt>
            <dd>Rola, która odpowiada za definicję cechy i odpowiada na pytania o nią.</dd>
          </div>
        </dl>
      </section>

      <details className="karta">
        <summary>Cechy, których w katalogu nie ma, i dlaczego ({dane.pominiete.length})</summary>
        <ul className="lista-pominietych">
          {dane.pominiete.map((p) => (
            <li key={p.cecha}>
              <code>{p.cecha}</code>: {p.powod}
            </li>
          ))}
        </ul>
      </details>

      <p className="drobne" style={{ marginTop: 24 }}>
        Źródło: <code>api/api/ai/features/katalog.yaml</code> (karty), wersje w{" "}
        <code>api/api/ai/churn_model/versions/</code> (modele) i tabela <code>psi_cech</code> w bazie{" "}
        <code>{dane.baza}</code> (PSI).
      </p>
    </main>
  );
}

function Karta({ karta, prog }: { karta: KartaCechy; prog: number }) {
  return (
    <article className="karta karta-cechy" aria-labelledby={`cecha-${karta.cecha}`}>
      <div className="naglowek-cechy">
        <h3 id={`cecha-${karta.cecha}`}>
          <code>{karta.cecha}</code>
        </h3>
        <span className="plakietka ostrzega">{rodzina(karta.rodzina)}</span>
      </div>
      <p>{karta.opis}</p>
      <Psi psi={karta.psi} prog={prog} />
      <dl className="pola-karty">
        <dt>Źródło</dt>
        <dd>
          {karta.system}: {karta.tabele.map((t, i) => (
            <span key={t}>
              {i > 0 && ", "}
              <code>{t}</code>
            </span>
          ))}
        </dd>
        <dt>Okno</dt>
        <dd>{karta.okno}</dd>
        <dt>Opóźnienie</dt>
        <dd>{karta.opoznienie}</dd>
        <dt>Plik SQL</dt>
        <dd>
          <code>ai/features/{karta.sql}</code>
        </dd>
        <dt>Właściciel</dt>
        <dd>{karta.wlasciciel}</dd>
        <dt>Wersja</dt>
        <dd>{karta.wersja}</dd>
        <dt>Modele</dt>
        <dd>
          {karta.modele.length ? (
            karta.modele.map((m) => (
              <code key={m} className="model">
                {m}
              </code>
            ))
          ) : (
            <span className="drobne">żaden model jej nie używa</span>
          )}
        </dd>
      </dl>
    </article>
  );
}

function Psi({ psi, prog }: { psi: PsiCechy | null; prog: number }) {
  if (!psi)
    return (
      <p className="psi">
        <span className="status brak">
          <span className="znacznik brak" aria-hidden="true">
            –
          </span>
          PSI: brak pomiaru
        </span>
      </p>
    );
  return (
    <p className="psi">
      <span className={`status ${psi.alert ? "alert" : "ok"}`}>
        <span className={`znacznik ${psi.alert ? "alert" : "ok"}`} aria-hidden="true">
          {psi.alert ? "!" : "✓"}
        </span>
        {psi.alert ? "odjechała od treningu" : "stabilna"}
      </span>{" "}
      <span className="drobne">
        PSI {dwaMiejsca.format(psi.psi)} (próg {dwaMiejsca.format(prog)}) w tygodniu od {dataKrotka(psi.t0)}; powyżej
        progu w {psi.alerty} z {odmiana(psi.tygodnie, ["ostatniego tygodnia", "ostatnich tygodni", "ostatnich tygodni"])}
      </span>
    </p>
  );
}
