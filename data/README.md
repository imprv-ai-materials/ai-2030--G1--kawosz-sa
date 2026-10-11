# Kawosz S.A. — dane kursowe

Syntetyczne dane palarni kawy Kawosz S.A. (Poznań) za okres **2024-01-01 – 2026-09-30**
(dzień eksportu: 2026-09-30). Dane są powtarzalne: to samo ziarno losowania daje bajt w bajt
te same pliki.

## Generowanie

```bash
git lfs pull                         # pliki .parquet i .zip są w Git LFS
poetry install                       # numpy, pandas, scikit-learn, pyarrow (grupa dev)
cd data
poetry run python -m kawosz_gen      # ziarno 2030 → pliki w data/
poetry run python -m kawosz_gen.validate   # same warunki kontrolne (liczone z plików)
```

Opcje: `--seed`, `--out`, `--key`, `--workers`, `--no-validate`. Pełny przebieg trwa ok. 1,5 minuty.

Katalog `kawosz_gen/` zdradza mechanizmy danych — uczestnikom należy przekazywać tylko pliki
z danymi.

## Pliki

| Katalog | Plik | 1 wiersz = |
|---|---|---|
| `crm/` | `crm_biura.parquet` | biuro (stan na dzień eksportu) |
| | `crm_umowy_historia.parquet` | zdarzenie umowy |
| | `crm_kontakty_am.parquet` | kontakt opiekuna klienta |
| | `ankiety_nps.parquet` | wysyłka ankiety NPS |
| | `crm_opiekunowie.parquet` | opiekun klienta (AM) |
| `erp/` | `erp_kontrahenci.parquet` | kontrahent z aktywną umową |
| | `erp_kontrahenci_archiwum.parquet` | kontrahent z zakończoną umową |
| | `erp_faktury.parquet`, `erp_pozycje.parquet` | faktura / korekta, pozycja dokumentu |
| | `erp_platnosci.parquet` | płatność |
| | `erp_kartoteka.parquet` | indeks towarowy |
| `pos/` | `pos_paragony.zip` → `paragony/pos_paragony_{lokal}_{data}.csv` | paragon (plik dzienny z kasy) |
| | `pos_pozycje.parquet` | pozycja paragonu |
| | `pos_produkty.parquet`, `lokale.parquet` | produkt POS, lokal |
| `ecom/` | `ecom_zamowienia.parquet`, `ecom_pozycje.parquet` | zamówienie, pozycja |
| | `ecom_subskrypcje.parquet` | płatność subskrypcji „Kawosz co miesiąc” |
| | `karty_podarunkowe.parquet` | karta podarunkowa |
| | `ecom_produkty.parquet` | produkt sklepu |
| `iot/` | `iot_ekspresy.parquet`, `iot_telemetria.parquet` | ekspres, ekspres × dzień |
| `helpdesk/` | `helpdesk_zgloszenia.parquet` | zgłoszenie |
| `nbp/` | `kursy_nbp.parquet` | kurs EUR/PLN z dnia roboczego |
| `agencja/` | `agencja_features.parquet` | biuro × migawka (tabela przygotowana przez agencję) |

## Konwencje systemów

- Tabele w formacie **Parquet** (kompresja zstd, typy kolumn zapisane w pliku; braki jako null).
- Wyjątek: dzienne pliki paragonów z kas (`pos/pos_paragony.zip`) zostają w oryginalnym formacie
  dostawcy POS — **CSV w cp1250**, separator `;`, **przecinek dziesiętny**, kwoty brutto.
  Kolumna `vat` w `pos_pozycje` to stawka w procentach.
- E-commerce zapisuje czas w **UTC** (`data_utc`, `data_platnosci`); kwoty brutto (VAT 23%) w walucie
  zamówienia (`waluta`: PLN lub EUR).
- ERP: kwoty netto w PLN, `vat` jako kwota podatku; daty dokumentów w czasie lokalnym.
- Czas biznesowy firmy: Europe/Warsaw.
