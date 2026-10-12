#!/usr/bin/env bash
# Runs once, inside the `app` container, after it's created. The db is already
# healthy at this point (app depends_on db: service_healthy), so migrations here
# are safe. Idempotent — re-running it is fine.
set -euo pipefail

cd "$(dirname "$0")/.."   # → katalog główny repozytorium

# The workspace is a bind mount. If the container user can't write to it, nothing
# below can work (and the editor can't save files either). Normally entrypoint.sh
# has already remapped `vscode` to the host uid; this is the loud fallback.
if [ ! -w . ]; then
  cat >&2 <<MSG
✗ $(pwd) is not writable by $(id -un) (uid $(id -u)); it is owned by uid $(stat -c %u .).
  The container user must match the owner of the bind-mounted source tree.
  • Linux host: the entrypoint should have remapped the user — rebuild the
    container (Dev Containers: Rebuild Container) so the new image is used.
  • Rootless Docker / Podman: set "remoteUser": "root" in devcontainer.json,
    or run podman with --userns=keep-id.
MSG
  exit 1
fi

echo "▸ Taking ownership of the named-volume mount points (.venv, ui/node_modules, ui/.next)…"
# The volumes mount empty + root-owned; hand them to the current (vscode) user so
# poetry / pnpm / next can write into them. ui/.next MUST be here too — it's a
# named volume (see compose.yaml) that shadows the bind mount, so next dev can't
# mkdir .next/dev under it until vscode owns it ("EACCES: mkdir …/ui/.next/dev").
# Not silenced on purpose: if this fails, everything after it fails less clearly.
sudo chown -R "$(id -u):$(id -g)" .venv ui/node_modules ui/.next

# Seed the virtualenv ourselves when it's missing or broken (fresh/stale volume).
# Poetry would otherwise try to rmtree(.venv) to "recreate" it; .venv is a mount
# point, so that only works when the failure is EBUSY — with any other error
# (e.g. EACCES on the parent dir) poetry aborts. `venv --clear` empties the dir
# in place without ever removing the mount point, so poetry just adopts it.
if [ ! -x .venv/bin/python ]; then
  echo "▸ .venv is empty or broken — seeding it with python3 -m venv…"
  python3 -m venv --clear .venv
fi

echo "▸ poetry install (backend deps → .venv)…"
# pyproject.toml ma package-mode = false: instalujemy same zależności; pakiet api jest na ścieżce dzięki
# PYTHONPATH=api (pipeline'y pypyr) i `--app-dir api` (uvicorn).
poetry install

# pypyr i reszta narzędzi z .venv mają działać w każdym terminalu kontenera bez `poetry run` ani aktywacji.
if ! grep -q "narzędzia projektu (pypyr)" ~/.bashrc; then
  echo "export PATH=\"$(pwd)/.venv/bin:\$PATH\"  # narzędzia projektu (pypyr) z .venv" >> ~/.bashrc
fi

echo "▸ pnpm install (frontend deps → ui/node_modules)…"
pnpm --dir ui install

# Baza kawosz.duckdb i symulacja nocnego potoku leżą w repozytorium na hoście (gitignore), więc w kontenerze są
# od razu, jeśli powstały wcześniej. Na świeżym klonie budujemy je tutaj (data/ musi być pobrane z Git LFS).
if [ ! -f kawosz.duckdb ] && [ -f data/erp/erp_faktury.parquet ] && head -c 7 data/erp/erp_faktury.parquet | grep -q PAR1; then
  echo "▸ kawosz.duckdb missing — building it from data/ (pypyr dane)…"
  poetry run pypyr dane
fi
if [ -f kawosz.duckdb ] && [ ! -f _symulacja/kawosz.duckdb ]; then
  echo "▸ _symulacja missing — simulating 30 nights of the nightly job (pypyr symulacja)…"
  poetry run pypyr symulacja
fi

cat <<'DONE'

✅ Devcontainer gotowy. Uruchom w dwóch osobnych terminalach:

    pypyr start_be      # API + nocne zadanie Inngest w JEDNYM procesie na :8101
    pypyr start_ui      # panel jakości danych (Next.js) na :3100

⚠️  W devcontainerze nie uruchamiaj `pypyr start_tilt` (to ścieżka dla hosta: Tilt nie jest
    zainstalowany w kontenerze, a w repozytorium nie ma Tiltfile). Serwer Inngest startuje sam
    razem z kontenerem (usługa `inngest`). `start_api` działa tu tak samo jak `start_be`,
    a `start_worker` nie jest potrzebny: Inngest woła funkcje pod app:8101.

Potem (VS Code → Ports):
    Panel jakości     http://localhost:3100
    API               http://localhost:8101/docs
    Inngest           http://localhost:8488   (pokaże funkcję kawosz-noc z cronem 3:00)

Jedna noc na żądanie (widać ją w Inngest krok po kroku):
    pypyr noc dzien=2026-09-30

DONE
