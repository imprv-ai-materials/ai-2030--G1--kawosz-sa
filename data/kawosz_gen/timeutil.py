"""Kalendarz: indeksy dni, święta w Polsce, dni robocze, strefy czasowe."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from .config import START, END, N_DAYS

DAYS = pd.date_range(START, END, freq="D")
DOW = DAYS.dayofweek.to_numpy()  # 0 = poniedziałek
MONTH = DAYS.month.to_numpy()
YEAR = DAYS.year.to_numpy()
DOY = DAYS.dayofyear.to_numpy()


def day_index(d: dt.date) -> int:
    return (d - START).days


def to_date(i: int) -> dt.date:
    return START + dt.timedelta(days=int(i))


def _easter(year: int) -> dt.date:
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(year, month, day)


def polish_holidays(year: int) -> set[dt.date]:
    e = _easter(year)
    hol = {
        dt.date(year, 1, 1), dt.date(year, 1, 6), e, e + dt.timedelta(days=1),
        dt.date(year, 5, 1), dt.date(year, 5, 3), e + dt.timedelta(days=49),
        e + dt.timedelta(days=60), dt.date(year, 8, 15), dt.date(year, 11, 1),
        dt.date(year, 11, 11), dt.date(year, 12, 25), dt.date(year, 12, 26),
    }
    if year >= 2025:
        hol.add(dt.date(year, 12, 24))
    return hol


HOLIDAYS = set().union(*(polish_holidays(y) for y in range(2011, 2028)))
IS_HOLIDAY = np.array([d.date() in HOLIDAYS for d in DAYS])
IS_WORKDAY = (DOW < 5) & ~IS_HOLIDAY


def easter_sundays() -> set[dt.date]:
    return {_easter(y) for y in range(2023, 2028)}


def workdays_between(a: dt.date, b: dt.date) -> list[dt.date]:
    out, d = [], a
    while d <= b:
        if d.weekday() < 5 and d not in HOLIDAYS:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def last_workday_of_month(year: int, month: int) -> dt.date:
    d = (dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1))
    while d.weekday() >= 5 or d in HOLIDAYS:
        d -= dt.timedelta(days=1)
    return d


def months_in_range() -> list[tuple[int, int]]:
    out = []
    y, m = START.year, START.month
    while (y, m) <= (END.year, END.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def add_years(d: dt.date, n: int) -> dt.date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:  # 29 lutego
        return d.replace(year=d.year + n, day=28)


def next_anniversary(start: dt.date, t: dt.date) -> dt.date:
    """Pierwsza rocznica umowy (okresy 12-miesięczne) ściśle po dniu `t`."""
    a = add_years(start, max(1, t.year - start.year))
    if a <= t:
        a = add_years(start, max(1, t.year - start.year + 1))
    return a


def warsaw_to_utc(local_naive: pd.Series | pd.DatetimeIndex) -> pd.Series:
    s = pd.Series(pd.to_datetime(local_naive))
    loc = s.dt.tz_localize("Europe/Warsaw", ambiguous=False, nonexistent="shift_forward")
    return loc.dt.tz_convert("UTC").dt.tz_localize(None)


def utc_to_warsaw(utc_naive: pd.Series) -> pd.Series:
    s = pd.Series(pd.to_datetime(utc_naive))
    return s.dt.tz_localize("UTC").dt.tz_convert("Europe/Warsaw").dt.tz_localize(None)


assert len(DAYS) == N_DAYS
