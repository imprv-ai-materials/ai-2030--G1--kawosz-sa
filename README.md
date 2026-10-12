# ai-2030--G1--kawosz-sa

Dane kursowe Kawosz S.A. w `data/` (opis: [data/README.md](data/README.md)). Na nich działa nocna kontrola danych
przychodu i panel jakości dla finansów.

## Co tu działa

- **Nocne zadanie** (`api/api/inngest_app.py`, Inngest, codziennie o 3:00 czasu polskiego). Wczytuje dostawy z
  poprzedniego dnia z POS, ERP i sklepu i sprawdza reguły jakości. Dostawę z błędem blokującym odkłada do tabeli
  `kwarantanna` z raportem naruszeń, a dobrą publikuje. Na koniec przelicza most przychodu. Każdy krok jest osobnym
  krokiem Inngest: po awarii ponawia się tylko ten, który padł. Drugi przebieg tej samej nocy daje te same liczby.
- **API** (`api/api/main.py`, FastAPI na :8101). Serwuje funkcje Inngest i dane panelu: `GET /api/jakosc`.
- **Panel jakości dla finansów** (`ui/`, Next.js na :3100). Pokazuje status dostaw z 30 dni, trend naruszeń na
  regułę, koszt błędów w złotych i niewyjaśnioną resztę mostu.

Prawdziwe dostawy jeszcze nie przychodzą, więc panel pokazuje **symulację września 2026** (`_symulacja/`). To 30 nocy
przeszłych przez te same kroki na danych z `data/`.

## Uruchomienie w devcontainerze (zalecane)

Wymagania: Docker Desktop, VS Code z rozszerzeniem Dev Containers, pliki z `data/` pobrane z Git LFS (`git lfs pull`).

1. Otwórz repozytorium w VS Code i wybierz **Dev Containers: Reopen in Container**.
   - Pierwsze otwarcie trwa kilka minut: obraz, `poetry install`, `pnpm install`.
   - Razem z kontenerem startuje serwer Inngest (usługa `inngest`), więc nie trzeba go uruchamiać osobno.
   - Jeśli nie ma jeszcze `kawosz.duckdb` albo `_symulacja/`, kontener sam je zbuduje (`pypyr dane`,
     `pypyr symulacja`).
2. Otwórz **dwa terminale** w kontenerze (Terminal → New Terminal) i uruchom w każdym jedno polecenie:

   ```bash
   pypyr start_be     # terminal 1: API + nocne zadanie Inngest na :8101
   pypyr start_ui     # terminal 2: panel jakości na :3100
   ```

3. Otwórz w przeglądarce (porty przekazuje VS Code, zakładka Ports):

   | Co | Adres |
   |---|---|
   | Panel jakości dla finansów | http://localhost:3100 |
   | Inngest: funkcja `kawosz-noc`, cron, przebiegi krok po kroku | http://localhost:8488 |
   | API (dokumentacja) | http://localhost:8101/docs |

4. Jedna noc na żądanie, bez czekania na 3:00 (trzeci terminal):

   ```bash
   pypyr noc dzien=2026-09-30
   ```

   Przebieg pojawi się w Inngest (Runs) z krokami wczytaj → sprawdz → wycen → publikuj / kwarantanna → most →
   sprzatanie. Po odświeżeniu panel pokazuje wynik.

Nie uruchamiaj w kontenerze `pypyr start_tilt` (w repozytorium nie ma Tiltfile) ani `pypyr start_worker` (Inngest
woła funkcje pod :8101). `pypyr start_api` działa tak samo jak `start_be`.

## Uruchomienie bez devcontainera (na hoście)

Wymagania: Python 3.12 z Poetry, Node 20+ z pnpm, Docker (dla serwera Inngest).

1. Jednorazowo zainstaluj zależności i przygotuj dane:

   ```bash
   poetry install
   pnpm --dir ui install
   poetry run pypyr dane          # data/ → kawosz.duckdb (+ mapa kontrahentów, most za VIII i IX 2026)
   poetry run pypyr symulacja     # 30 nocy września → _symulacja/, ok. 1 min
   ```

   Jeśli `kawosz.duckdb` i `_symulacja/` już istnieją, ten krok możesz pominąć.

2. **Trzy terminale**:

   ```bash
   pypyr start_inngest   # terminal 1: serwer Inngest w Dockerze na :8488 (Ctrl+C go zatrzymuje)
   pypyr start_be        # terminal 2: API + nocne zadanie na :8101
   pypyr start_ui        # terminal 3: panel jakości na :3100
   ```

   (Bez aktywnego `.venv` poprzedź polecenia `poetry run`.)

3. Adresy są takie same jak w devcontainerze. Noc na żądanie: `pypyr noc dzien=2026-09-30`.

## Polecenia

| Polecenie | Co robi |
|---|---|
| `pypyr start_be` | API + funkcje Inngest (nocne zadanie) na :8101 |
| `pypyr start_ui` | panel jakości na :3100 |
| `pypyr start_inngest` | serwer Inngest na :8488 (tylko na hoście, w kontenerze działa sam) |
| `pypyr noc dzien=RRRR-MM-DD` | wysyła do Inngest zdarzenie `kawosz/noc.uruchom`: jedna noc dla wybranego dnia |
| `pypyr dane` | buduje `kawosz.duckdb` od zera z `data/` |
| `pypyr symulacja` | buduje od nowa symulację września w `_symulacja/` (`kawosz.duckdb` się nie zmienia) |
| `pypyr test` | testy (`api/tests`) |

## Na jakich danych to działa

Procesy uruchomione przez pypyr biorą ścieżki ze zmiennych `kawosz_*` w `pyproject.toml` (`[tool.pypyr.vars]`).
Domyślnie jest to symulacja:

| Zmienna | Domyślnie (symulacja) | Produkcja (bez zmiennych `KAWOSZ_*`) |
|---|---|---|
| `kawosz_baza` | `_symulacja/kawosz.duckdb` | `kawosz.duckdb` |
| `kawosz_dostawy` | `_symulacja/dostawy` | `_dostawy/RRRR-MM-DD/{pos,erp,ecom}/` |
| `kawosz_raporty` | `_symulacja/kwarantanna` | `docs/kwarantanna/` |

Bez pypyr te same ścieżki ustawiają zmienne środowiskowe `KAWOSZ_BAZA`, `KAWOSZ_DOSTAWY` i `KAWOSZ_RAPORTY`.
Panel pokazuje u góry, że dane pochodzą z symulacji.

## Gdy coś nie działa

| Objaw | Przyczyna i co zrobić |
|---|---|
| `SigningKeyMissingError` przy `start_be` | Proces nie wie o serwerze Inngest (brak `INNGEST_DEV`), więc SDK startuje w trybie produkcyjnym. Uruchamiaj przez `pypyr start_be`, który ustawia `INNGEST_DEV` sam. Ręcznie: `INNGEST_DEV=http://127.0.0.1:8488`. |
| `Address already in use` (:8101 albo :3100) | Działa już poprzednia kopia, np. w innym terminalu. Zatrzymaj ją (Ctrl+C) albo znajdź proces: `lsof -iTCP:8101 -sTCP:LISTEN`. |
| :8488 zajęty, w Inngest nie ma funkcji `kawosz-noc` | Na tym porcie działa inny serwer Inngest, np. devcontainer innego projektu z tego szablonu albo `kawosz-inngest` z hosta. Zatrzymaj go (`docker stop kawosz-inngest`) i uruchom ponownie. |
| `pypyr: command not found` | Na hoście: `poetry run pypyr …` albo aktywuj `.venv`. W kontenerze otwórz nowy terminal (`.venv/bin` jest na PATH od `postCreate.sh`). |
| Panel: „Panel nie ma jeszcze danych” | Baza nie ma wyników nocy (tabel `wsady`, `naruszenia`). Uruchom `pypyr symulacja` albo `pypyr noc dzien=…`. |
| Panel: „Panel nie może teraz pobrać danych” | API nie działa. Uruchom `pypyr start_be`. Adres API dla panelu: zmienna `KAWOSZ_API`, domyślnie `http://127.0.0.1:8101`. |
| Panel: „Dane są właśnie aktualizowane” | Nocne zadanie trzyma bazę do zapisu. Odśwież stronę za chwilę. |

## Gdzie co jest w kodzie

- `api/api/inngest_app.py`: funkcja Inngest `kawosz-noc` (cron `TZ=Europe/Warsaw 0 3 * * *`) i kolejność kroków.
- `api/api/data_platform/noc.py`: wczytanie wsadu, reguły na „kandydacie”, kwarantanna, publikacja po kluczu.
- `api/api/data_platform/reguly/`, `kontrakty/`: reguły jakości i kontrakty danych (opis w [docs/reguly.md](docs/reguly.md)).
- `api/api/contexts_boundaries/revenue_bc/`: definicja przychodu netto i most przychodu.
- `api/api/data_platform/panel_jakosci.py`: dane panelu (`GET /api/jakosc`). Panel: `ui/app/`.
- `api/api/data_platform/symulacja.py`, `dostawa_z_archiwum.py`: symulacja nocy i dostawy zbudowane z `data/`.
