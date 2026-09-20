"""NOAA/SWPC scales adapter: latest observed block ``0`` only.

This adapter parses only observed (not predicted) scales. Historical test
samples are never published as live data. Registry publication is separately gated.
"""
from __future__ import annotations

import datetime as dt
import json

from ..errors import AdapterError
from ..registry import level_obj
from ..timeutil import fmt
from .base import FetchResult

SOURCE = "noaa-swpc"
SCALES = {"G": "noaa-g", "S": "noaa-s", "R": "noaa-r"}
TITLES = {"G": "Geomagnetische Stürme (NOAA)",
          "S": "Solare Strahlungsstürme (NOAA)",
          "R": "Radiostörungen (NOAA)"}
SOURCE_URL = "https://www.swpc.noaa.gov/node/1085"


def _observation_time(block: dict, now: dt.datetime) -> str:
    date, clock = block.get("DateStamp"), block.get("TimeStamp")
    if not isinstance(date, str) or not isinstance(clock, str):
        raise AdapterError("schema", "NOAA Beobachtung hat kein gültiges DateStamp/TimeStamp")
    try:
        observed = dt.datetime.strptime(date + "T" + clock, "%Y-%m-%dT%H:%M:%S")
        if observed.strftime("%Y-%m-%dT%H:%M:%S") != date + "T" + clock:
            raise ValueError("non-canonical timestamp")
        observed = observed.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        raise AdapterError("schema", "NOAA Beobachtungszeit ist ungültig") from None
    if observed > now + dt.timedelta(hours=2):
        raise AdapterError("sanity", "NOAA Beobachtung mehr als 2 h in der Zukunft")
    return fmt(observed)


def parse(raw: bytes, now: dt.datetime, entry: dict) -> FetchResult:
    try:
        doc = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AdapterError("parse", "NOAA-Antwort ist kein gültiges JSON") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("0"), dict):
        raise AdapterError("schema", "NOAA latest-observed Block '0' fehlt")
    current = doc["0"]  # '-1' = 24-h maximum; '1'..'3' = forecasts; deliberately ignored.
    observed_at = _observation_time(current, now)
    items = []
    for letter, scheme_id in SCALES.items():
        cell = current.get(letter)
        if not isinstance(cell, dict) or "Scale" not in cell:
            raise AdapterError("schema", f"NOAA '{letter}' latest-observed Scale fehlt")
        value = cell["Scale"]
        # Missing data is NOT NOAA level 0 and never converted to an all-clear.
        if not isinstance(value, str) or value not in {"0", "1", "2", "3", "4", "5"}:
            raise AdapterError("schema", f"NOAA '{letter}' Scale fehlt oder unbekannt: {value!r}")
        try:
            level = level_obj(entry, scheme_id, value)
        except KeyError:
            raise AdapterError("schema", f"NOAA Skala nicht in Registry: {scheme_id}:{value}") from None
        items.append({
            "id": f"{SOURCE}:scale:{letter}",
            "kind": "status", "domain": entry["domain"], "source": SOURCE,
            "provenance": "original", "original_publisher": None,
            "title": TITLES[letter], "lang": "de", "url": SOURCE_URL,
            "occurred_at": None, "published_at": None,
            "observed_at": observed_at, "source_updated_at": None,
            "ongoing": None, "data_status": "unknown", "source_status_raw": None,
            "level": level,
            "location": {"precision": "global", "name": "Global", "countries": [], "lat": None, "lon": None},
            "metrics": {},
        })
    return FetchResult(items=items, complete=True, items_in_window=3)
