"""Grupa kontrolna do pomiaru skuteczności wizyty: które biura w kwartale losowo nie dostają wizyty ani rabatu.

Los biura to skrót z kwartału i id_biura, więc biuro jest w kontroli albo nie przez cały kwartał, niezależnie od
tego, w którym tygodniu i na której liście się pojawi. To ważne, bo poniedziałkowa lista co tydzień pokazuje te same
zagrożone biura, dopóki nie dostaną wizyty: losowanie zależne od składu listy przeniosłoby biuro z kontroli do
wizyt w kolejnym tygodniu. Ten sam los widzi kalkulator wizyt i poniedziałkowa lista opiekunów.

Każde biuro trafia do kontroli z prawdopodobieństwem równym udziałowi, więc przy kilku biurach na liście liczba biur
w kontroli w kwartale się waha (przy 10% i 40 biurach: zwykle 2–7).
"""

import hashlib
from datetime import date


def kwartal(d: date) -> str:
    """2026-10-05 → „2026-Q4”."""
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def los(kwartal_: str, id_biura: int) -> float:
    """Liczba z [0, 1) wyznaczona przez kwartał i biuro: to samo biuro w tym samym kwartale zawsze ma ten sam los."""
    return int.from_bytes(hashlib.sha256(f"{kwartal_}:{id_biura}".encode()).digest()[:8], "big") / 2**64


def w_kontroli(id_biura: int, kwartal_: str, udzial: float) -> bool:
    """Czy biuro jest w tym kwartale w grupie kontrolnej."""
    return los(kwartal_, int(id_biura)) < udzial
