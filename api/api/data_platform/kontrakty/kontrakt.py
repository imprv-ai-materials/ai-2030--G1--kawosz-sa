"""Kontrakty danych: po jednym pliku YAML na źródło (pos_paragony, ecom_zamowienia, erp_faktury).

Kontrakt to jedyne miejsce, w którym zapisano właściciela, kolumny, typy, słowniki, format i termin
dostawy oraz reguły źródła: opis, poziom, właściciela, progi i to, co zrobić przy naruszeniu.
Kod z data_platform/ czyta te wartości stąd. load_raw.py bierze format pliku i typy, a
reguly/{pos,ecom,erp}.py budują z nich schematy Pandery. W kodzie reguły zostaje tylko SQL i warunki.

Kontrakt jest sprawdzany przy wczytaniu. Literówka w kluczu, nieznany typ, właściciel spoza listy
albo parametr brakujący w opisie reguły kończą się błędem, a nie cichym pominięciem.
"""

import re
from datetime import date, time
from functools import cache
from pathlib import Path
from typing import Any, Literal

import pandera.pandas as pa
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.data_platform.reguly.regula import Poziom, Wlasciciel, meta

KATALOG = Path(__file__).parent

# Typ kolumny w kontrakcie (DuckDB) → typ kolumny w ramce pandas, którą sprawdza Pandera.
TYPY_PANDAS: dict[str, Any] = {
    "INTEGER": "int32",
    "BIGINT": "int64",
    "DOUBLE": "float64",
    "DECIMAL(12,2)": "float64",
    "VARCHAR": str,
    "BOOLEAN": bool,
    "DATE": "datetime64[us]",
    "TIMESTAMP": "datetime64[us]",
    "TIMESTAMP_NS": "datetime64[ns]",
}
# Kolumna opcjonalna (źródło może ją dopiero dodać) dostaje typ z brakami i konwersję, bo nie wiadomo,
# w jakim typie fizycznym przyjdzie pierwszy raz. Tekst bez konwersji: Pandera zamieniłaby brak na „nan”.
TYPY_PANDAS_OPCJONALNE: dict[str, Any] = {
    **TYPY_PANDAS,
    "INTEGER": "Int32",
    "BIGINT": "Int64",
    "DOUBLE": float,
    "DECIMAL(12,2)": float,
    "DATE": pa.DateTime,
    "TIMESTAMP": pa.DateTime,
    "TIMESTAMP_NS": pa.DateTime,
}
WERSJA = re.compile(r"^\d+\.\d+\.\d+$")
PLIK = "plik"  # w `kolumny` reguły: nazwa dostarczonego pliku, a nie kolumna w nim


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Kolumna(_Model):
    nazwa: str
    typ: str
    opis: str
    wymagana: bool = True  # False: kolumna, którą źródło może dopisać na końcu pliku bez nowej wersji
    pusta: bool = False  # czy wolno nie mieć wartości
    unikalna: bool = False
    dozwolone: list[str | int] | None = None
    min: int | float | None = None
    max: int | float | None = None
    wiekszy_niz: int | float | None = None
    wzorzec: str | None = None

    @model_validator(mode="after")
    def _znany_typ(self):
        if self.typ not in TYPY_PANDAS:
            raise ValueError(f"kolumna {self.nazwa}: nieznany typ {self.typ}, dozwolone: {', '.join(TYPY_PANDAS)}")
        return self

    def pandera(self, **nadpisz) -> pa.Column:
        """Kolumna Pandery z typem i ograniczeniami z kontraktu; `nadpisz` zmienia np. `nullable` w jednej regule."""
        checks = []
        if self.dozwolone is not None:
            checks.append(pa.Check.isin(self.dozwolone))
        if self.min is not None and self.max is not None:
            checks.append(pa.Check.in_range(self.min, self.max))
        elif self.min is not None:
            checks.append(pa.Check.ge(self.min))
        elif self.max is not None:
            checks.append(pa.Check.le(self.max))
        if self.wiekszy_niz is not None:
            checks.append(pa.Check.gt(self.wiekszy_niz))
        if self.wzorzec is not None:
            checks.append(pa.Check.str_matches(self.wzorzec))
        opcjonalna = not self.wymagana
        cechy = {
            "dtype": (TYPY_PANDAS_OPCJONALNE if opcjonalna else TYPY_PANDAS)[self.typ],
            "checks": checks,
            "nullable": self.pusta,
            "unique": self.unikalna,
            "required": self.wymagana,
            "coerce": opcjonalna and self.typ != "VARCHAR",
            "description": self.opis,
        }
        return pa.Column(**(cechy | nadpisz))


class Dostawa(_Model):
    termin: str  # po ludzku, np. „D+1 do 6:00”
    dni_po: int = Field(ge=0)  # pliki za dzień D najpóźniej D + dni_po …
    godzina: time  # … o tej godzinie
    strefa: str
    format: Literal["csv", "parquet"]
    plik: str  # nazwa pliku; {lokal} i {dzien} (RRRR-MM-DD) to pola z danych
    kodowanie: str | None = None
    separator: str | None = None
    separator_dziesietny: str | None = None
    naglowek: bool | None = None

    @model_validator(mode="after")
    def _csv_ma_format(self):
        if self.format == "csv" and None in (self.kodowanie, self.separator, self.separator_dziesietny, self.naglowek):
            raise ValueError("dostawa CSV wymaga: kodowanie, separator, separator_dziesietny, naglowek")
        return self


class Wersja(_Model):
    wersja: str
    data: date
    zmiana: str


class RegulaKontraktu(_Model):
    opis: str  # może mieć pola z `parametry`, np. „cena ręczna do {cena_reczna_max} zł”
    poziom: Poziom
    wlasciciel: Wlasciciel
    jednostka: str  # czym jest jeden sprawdzany rekord
    skala: list[int] = []  # numery wierszy z docs/skala_problemu.md
    kolumny: list[str]  # kolumny, których dotyczy reguła; z innej tabeli źródła jako tabela.kolumna
    co_zrobic: str
    parametry: dict[str, Any] = {}
    bez_danych: str | None = None  # co znaczy, że reguła nie ma czego sprawdzić (np. brak czasu dostawy)

    @model_validator(mode="after")
    def _opis_z_parametrami(self):
        try:
            self.opis.format(**self.parametry)
        except KeyError as e:
            raise ValueError(f"opis używa parametru {e}, którego nie ma w `parametry`") from None
        return self


class Kontrakt(_Model):
    kontrakt: str
    nazwa: str
    wersja: str
    wlasciciel: Wlasciciel  # odpowiada za dostawę i zmiany po stronie źródła
    odbiorca: Wlasciciel
    system: str
    opis: str
    dostawa: Dostawa
    zasady_zmian: str
    historia: list[Wersja]
    kolumny: list[Kolumna]
    reguly: dict[str, RegulaKontraktu]

    @model_validator(mode="after")
    def _spojnosc(self):
        if not WERSJA.match(self.wersja):
            raise ValueError(f"wersja {self.wersja}: oczekiwano numeru GŁÓWNA.PODRZĘDNA.POPRAWKA, np. 1.0.0")
        if not self.historia or self.historia[-1].wersja != self.wersja:
            raise ValueError(f"ostatni wpis w historii musi mieć wersję {self.wersja}")
        nazwy = [k.nazwa for k in self.kolumny]
        if len(nazwy) != len(set(nazwy)):
            raise ValueError(f"powtórzona nazwa kolumny: {nazwy}")
        pierwsza_opcjonalna = next((i for i, k in enumerate(self.kolumny) if not k.wymagana), len(nazwy))
        if any(k.wymagana for k in self.kolumny[pierwsza_opcjonalna:]):
            raise ValueError("kolumny opcjonalne muszą być na końcu listy (źródło dopisuje je na końcu pliku)")
        for id_, regula in self.reguly.items():
            nieznane = [k for k in regula.kolumny if "." not in k and k not in [*nazwy, PLIK]]
            if nieznane:
                raise ValueError(f"{id_}: kolumny spoza kontraktu {nieznane} (z innej tabeli pisz tabela.kolumna)")
        return self

    @property
    def plik_yaml(self) -> str:
        return f"{self.kontrakt}.yaml"

    @property
    def wymagane(self) -> list[str]:
        return [k.nazwa for k in self.kolumny if k.wymagana]

    @property
    def opcjonalne(self) -> list[str]:
        return [k.nazwa for k in self.kolumny if not k.wymagana]

    def kolumna(self, nazwa: str) -> Kolumna:
        return next(k for k in self.kolumny if k.nazwa == nazwa)

    def kolumny_pandera(self) -> dict[str, pa.Column]:
        return {k.nazwa: k.pandera() for k in self.kolumny}

    def parametry(self, id_: str) -> dict[str, Any]:
        return self.reguly[id_].parametry

    def opis_reguly(self, id_: str) -> str:
        regula = self.reguly[id_]
        return regula.opis.format(**regula.parametry)

    def schemat(self, id_: str, columns: dict | None = None, checks: list | None = None, **cechy) -> pa.DataFrameSchema:
        """Schemat reguły `id_`: kolumny i warunki z kodu, a opis, poziom, właściciel i skala z kontraktu."""
        regula = self.reguly[id_]
        return pa.DataFrameSchema(
            columns,
            checks=checks,
            name=id_,
            description=self.opis_reguly(id_),
            metadata=meta(regula.poziom, regula.wlasciciel, *regula.skala, jednostka=regula.jednostka),
            **cechy,
        )


@cache
def wczytaj(nazwa: str) -> Kontrakt:
    """Kontrakt z pliku kontrakty/{nazwa}.yaml."""
    with (KATALOG / f"{nazwa}.yaml").open(encoding="utf-8") as plik:
        return Kontrakt.model_validate(yaml.safe_load(plik))
