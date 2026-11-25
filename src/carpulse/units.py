"""Metric formatting helpers (km, °C, L/100 km, dd.mm.yyyy)."""

from __future__ import annotations

from datetime import date, datetime


def km(value: float) -> str:
    return f"{round(value):,} km".replace(",", " ")


def num(value: float) -> str:
    return f"{round(value):,}".replace(",", " ")


def kmh(value: float) -> str:
    return f"{round(value)} km/h"


def celsius(value: float) -> str:
    return f"{value:.0f} °C"


def volts(value: float) -> str:
    return f"{value:.1f} V"


def l100(value: float) -> str:
    return f"{value:.1f} L/100 km"


def dmy(value: str | date | datetime) -> str:
    if isinstance(value, str):
        value = date.fromisoformat(value[:10])
    return value.strftime("%d.%m.%Y")


def when(days: int) -> str:
    """Human 'in 3 weeks' style text for a number of days from today."""
    if days <= 0:
        return "now"
    if days == 1:
        return "tomorrow"
    if days < 14:
        return f"in {days} days"
    if days < 60:
        return f"in {round(days / 7)} weeks"
    if days < 730:
        return f"in {round(days / 30.4)} months"
    return f"in {days / 365:.1f} years"


def duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60}:{seconds % 60:02d}"
