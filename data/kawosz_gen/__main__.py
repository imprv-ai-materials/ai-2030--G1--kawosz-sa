"""CLI: generowanie danych Kawosz S.A.

    cd data
    poetry run python -m kawosz_gen               # ziarno 2030, dane do data/, klucz do ../klucz_odpowiedzi
    poetry run python -m kawosz_gen --no-validate
    poetry run python -m kawosz_gen.validate      # same warunki kontrolne
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .generate import generate
from .validate import run

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser(description="Generator danych kursowych Kawosz S.A.")
    ap.add_argument("--seed", type=int, default=2030)
    ap.add_argument("--out", type=Path, default=ROOT, help="katalog danych (domyślnie data/)")
    ap.add_argument("--key", type=Path, default=ROOT.parent / "klucz_odpowiedzi",
                    help="katalog klucza odpowiedzi (poza katalogiem danych)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--no-validate", action="store_true")
    a = ap.parse_args()
    generate(a.seed, a.out, a.key, workers=a.workers)
    if not a.no_validate:
        print()
        sys.exit(0 if run(a.out, a.key) else 1)


if __name__ == "__main__":
    main()
