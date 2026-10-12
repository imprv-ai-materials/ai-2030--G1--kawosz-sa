export function Slowniczek() {
  return (
    <section className="karta" aria-labelledby="slowniczek">
      <h2 id="slowniczek">Słowniczek</h2>
      <p className="lead" style={{ marginBottom: 14 }}>
        Pojęcia z tego panelu. Panel nie wymaga wiedzy technicznej: każda liczba wynika z kontroli opisanych niżej.
      </p>
      <dl className="slowniczek">
        <div>
          <dt>Dostawa</dt>
          <dd>
            Dane z jednego systemu za jeden dzień, które przychodzą w nocy: paragony ze wszystkich kas, faktury z ERP
            albo zamówienia ze sklepu. Kontrola dotyczy całej dostawy naraz.
          </dd>
        </div>
        <div>
          <dt>Kwarantanna</dt>
          <dd>
            Poczekalnia dla dostawy z poważnym błędem. Dane są zachowane, ale nie trafiają do raportów. Raporty
            pokazują ostatni poprawny stan. Po poprawce u źródła dostawa przechodzi kontrolę jeszcze raz.
          </dd>
        </div>
        <div>
          <dt>Reguła blokująca</dt>
          <dd>
            Błąd, przez który raport pokazałby złą kwotę: zdublowany plik, brak danych, suma paragonu niezgodna z
            pozycjami, sprzedaż bez kategorii, faktura na zdublowanego klienta. Jedno naruszenie zatrzymuje dostawę.
          </dd>
        </div>
        <div>
          <dt>Reguła ostrzegająca</dt>
          <dd>
            Błąd, który nie zmienia kwot w raporcie (np. brak metody płatności, zły e-mail). Dane idą dalej, a
            właściciel systemu dostaje listę rekordów do poprawy.
          </dd>
        </div>
        <div>
          <dt>Przychód netto według definicji</dt>
          <dd>
            Przychód bez VAT, w złotych (euro po kursie NBP), bez zamówień testowych i zwrotów, z kartami podarunkowymi
            w dniu realizacji i subskrypcjami rocznymi rozłożonymi na 12 miesięcy. Każdy dokument liczy się raz.
          </dd>
        </div>
        <div>
          <dt>Przychód zatrzymany</dt>
          <dd>
            Przychód netto z dostaw w kwarantannie. Sprzedaż się odbyła, ale raport jej jeszcze nie pokazuje, więc
            przychód w raportach jest zaniżony o tę kwotę.
          </dd>
        </div>
        <div>
          <dt>Zawyżenie zatrzymane</dt>
          <dd>
            O ile raport pokazałby za dużo, gdyby zła dostawa przeszła: zdublowane dokumenty (np. ten sam plik z kasy
            przysłany drugi raz) policzyłyby się dwa razy.
          </dd>
        </div>
        <div>
          <dt>Surowa suma BI i most</dt>
          <dd>
            Dashboard BI sumuje kwoty tak, jak leżą w systemach. Most rozkłada różnicę między tą sumą a przychodem
            netto na kroki: VAT, zwroty, plan roczny, karty, kurs euro, zamówienia testowe, strefa czasowa.
          </dd>
        </div>
        <div>
          <dt>Niewyjaśniona reszta</dt>
          <dd>
            Część różnicy między BI a przychodem netto, której nie tłumaczy żaden krok mostu. Powinna wynosić 0,00 zł.
            Inna wartość to sygnał błędu w danych.
          </dd>
        </div>
        <div>
          <dt>Właściciel (kto poprawia)</dt>
          <dd>
            Zespół odpowiedzialny za system, z którego pochodzi błąd. Poprawka zawsze odbywa się u źródła, a nie w
            raporcie. Pytania o konkretną dostawę kieruj do właściciela z jej opisu.
          </dd>
        </div>
      </dl>
    </section>
  );
}
