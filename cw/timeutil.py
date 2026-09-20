"""Zeitfunktionen. Alle gespeicherten Zeiten: UTC, Sekunden, Format YYYY-MM-DDTHH:MM:SSZ."""
from __future__ import annotations
import datetime as dt

FMT = "%Y-%m-%dT%H:%M:%SZ"
UTC = dt.timezone.utc


def now_utc() -> dt.datetime:
    return dt.datetime.now(UTC).replace(microsecond=0)


def fmt(t: dt.datetime) -> str:
    if t.tzinfo is None:
        raise ValueError("naive datetime")
    return t.astimezone(UTC).strftime(FMT)


def parse_utc(value: str) -> dt.datetime:
    """Strikter Parser. Lehnt unmögliche Daten (2026-02-30, 25:00) und andere Schreibweisen ab."""
    if not isinstance(value, str) or len(value) != 20:
        raise ValueError(f"kein UTC-Zeitstempel: {value!r}")
    return dt.datetime.strptime(value, FMT).replace(tzinfo=UTC)


def from_epoch_ms(ms) -> dt.datetime:
    if isinstance(ms, bool) or not isinstance(ms, int):
        raise TypeError("Epoch-Millisekunden müssen eine Ganzzahl sein")
    return dt.datetime.fromtimestamp(ms / 1000, UTC).replace(microsecond=0)
