"""GDACS app feed: five non-earthquake natural-hazard alert categories.

The feed does not publish a count or a completeness guarantee. Consequently a
successful parse is always incomplete for the state-merger contract: missing
events cannot be interpreted as withdrawals or evidence of an empty feed.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from urllib.parse import parse_qs, urlparse

from ..errors import AdapterError
from ..registry import level_obj
from ..timeutil import fmt
from .base import FetchResult

SOURCE = "gdacs"
SCHEME = "gdacs-alert"
TYPES = {"TC": "tropical_cyclone", "FL": "flood", "VO": "volcano",
         "DR": "drought", "WF": "wildfire"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})?$")


def _time(value, field: str, event: str, now: dt.datetime, allow_future: bool = False) -> str:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        raise AdapterError("schema", f"{event}: {field} ist kein ISO-Zeitstempel")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise AdapterError("schema", f"{event}: {field} ist ungültig") from None
    # GDACS sends naive timestamps in its feed; its report labels event time UTC.
    parsed = parsed.replace(tzinfo=dt.timezone.utc) if parsed.tzinfo is None else parsed.astimezone(dt.timezone.utc)
    if not allow_future and parsed > now + dt.timedelta(hours=2):
        raise AdapterError("sanity", f"{event}: {field} liegt mehr als 2 h in der Zukunft")
    return fmt(parsed)


def _number(value, field: str, event: str):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise AdapterError("schema", f"{event}: {field} ist keine endliche Zahl")
    return value


def _item(feature: dict, entry: dict, now: dt.datetime) -> dict:
    if not isinstance(feature, dict) or feature.get("type") != "Feature":
        raise AdapterError("schema", "GDACS-Eintrag ist kein GeoJSON-Feature")
    p = feature.get("properties")
    if not isinstance(p, dict):
        raise AdapterError("schema", "GDACS-Eintrag hat keine properties")
    eventtype = p.get("eventtype")
    eventid, episodeid = p.get("eventid"), p.get("episodeid")
    if isinstance(eventid, bool) or not isinstance(eventid, int) or eventid <= 0:
        raise AdapterError("schema", f"{eventtype}: ungültige eventid")
    if isinstance(episodeid, bool) or not isinstance(episodeid, int) or episodeid <= 0:
        raise AdapterError("schema", f"{eventtype}:{eventid}: ungültige episodeid")
    event = f"{eventtype}:{eventid}"
    title = p.get("name")
    if not isinstance(title, str) or not 3 <= len(title) <= 300:
        raise AdapterError("schema", f"{event}: Name fehlt/ist ungültig")
    urls = p.get("url")
    report = urls.get("report") if isinstance(urls, dict) else None
    if not isinstance(report, str) or urlparse(report).hostname not in ("gdacs.org", "www.gdacs.org") or not report.startswith("https://"):
        raise AdapterError("schema", f"{event}: GDACS-Berichtslink fehlt/ist ungültig")
    params = parse_qs(urlparse(report).query)
    if params.get("eventtype") != [eventtype] or params.get("eventid") != [str(eventid)]:
        raise AdapterError("sanity", f"{event}: Bericht zeigt auf eine andere Meldung")

    alert = p.get("alertlevel")
    try:
        level = level_obj(entry, SCHEME, alert)
    except (KeyError, TypeError):
        raise AdapterError("schema", f"{event}: unbekannte GDACS-Stufe {alert!r}") from None
    occurred = _time(p.get("fromdate"), "fromdate", event, now)
    updated = _time(p.get("datemodified"), "datemodified", event, now)
    ended = _time(p.get("todate"), "todate", event, now, allow_future=True)
    if occurred > ended:
        raise AdapterError("sanity", f"{event}: todate liegt vor fromdate")

    geometry = feature.get("geometry")
    coords = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if not isinstance(geometry, dict) or geometry.get("type") != "Point" or not isinstance(coords, list) or len(coords) < 2:
        raise AdapterError("schema", f"{event}: erwarteter GDACS-Zentroid fehlt")
    lon, lat = _number(coords[0], "lon", event), _number(coords[1], "lat", event)
    if not -180 <= lon <= 180 or not -90 <= lat <= 90:
        raise AdapterError("sanity", f"{event}: ungültige Koordinaten")

    countries = p.get("affectedcountries")
    if not isinstance(countries, list):
        raise AdapterError("schema", f"{event}: affectedcountries ist keine Liste")
    iso2 = []
    for c in countries:
        code = c.get("iso2") if isinstance(c, dict) else None
        if not isinstance(code, str) or not re.fullmatch(r"[A-Z]{2}", code):
            raise AdapterError("schema", f"{event}: ungültiges ISO-2-Land")
        if code not in iso2:
            iso2.append(code)

    sev = p.get("severitydata")
    metrics = {"hazard_type": TYPES[eventtype], "episode_id": episodeid}
    if isinstance(sev, dict) and sev.get("severity") is not None:
        metrics["severity"] = _number(sev["severity"], "severity", event)
        if isinstance(sev.get("severityunit"), str):
            metrics["severity_unit"] = sev["severityunit"][:40]
    score = p.get("alertscore")
    if score is not None:
        metrics["alert_score"] = _number(score, "alertscore", event)
    current = p.get("iscurrent")
    if current not in ("true", "false"):
        raise AdapterError("schema", f"{event}: iscurrent unbekannt")

    return {"id": f"{SOURCE}:{eventtype}:{eventid}", "kind": "event",
            "domain": entry["domain"], "source": SOURCE, "provenance": "original",
            "original_publisher": None, "title": title, "lang": "en", "url": report,
            "occurred_at": occurred, "published_at": None, "observed_at": None,
            "source_updated_at": updated, "ongoing": None, "data_status": "unknown",
            "source_status_raw": current, "level": level,
            "location": {"precision": "region", "name": title[:120],
                         "countries": iso2, "lat": round(float(lat), 4), "lon": round(float(lon), 4)},
            "metrics": metrics}


def parse(raw: bytes, now: dt.datetime, entry: dict) -> FetchResult:
    try:
        doc = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AdapterError("parse", "GDACS-Antwort ist kein gültiges JSON") from None
    if not isinstance(doc, dict) or doc.get("type") != "FeatureCollection" or not isinstance(doc.get("features"), list):
        raise AdapterError("schema", "GDACS-Antwort ist keine FeatureCollection")
    items, seen = [], set()
    for feature in doc["features"]:
        if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
            raise AdapterError("schema", "ungültiges GDACS-Feature")
        if feature["properties"].get("eventtype") not in TYPES:
            continue  # EQ/TS werden absichtlich nicht aus GDACS übernommen.
        item = _item(feature, entry, now)
        if item["id"] in seen:
            raise AdapterError("sanity", f"mehrere GDACS-Features für {item['id']}")
        seen.add(item["id"])
        items.append(item)
    # GDACS gibt ausdrücklich keine Vollständigkeitsgarantie. Auch [] bedeutet
    # daher nicht: alle alten Events zurückziehen / verlässlich leere Quelle.
    return FetchResult(items=items, complete=False, items_in_window=len(items))
