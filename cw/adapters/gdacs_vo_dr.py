"""GDACS type-specific GeoJSON feeds for volcanoes and droughts.

These feeds do not use the same field representation as gdacs_app_feed.json:
DR commonly uses digit strings and human-readable dates, while VO event data
uses numeric ids and ISO timestamps. Both are normalized here without inferring
status, area, or completeness from fields GDACS does not guarantee.
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

SCHEME = "gdacs-alert"
HUMAN_DATES = ("%d %b %Y %H:%M:%S", "%d %b %Y %H:%M")


def _int_id(value, field: str, event: str) -> int:
    if isinstance(value, bool):
        raise AdapterError("schema", f"{event}: {field} ungültig")
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value):
        return int(value)
    raise AdapterError("schema", f"{event}: {field} ungültig")


def _number(value, field: str, event: str):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise AdapterError("schema", f"{event}: {field} ist keine Zahl")
    if isinstance(value, (int, float)):
        out = float(value)
    elif isinstance(value, str):
        try:
            out = float(value)
        except ValueError:
            raise AdapterError("schema", f"{event}: {field} ist keine Zahl") from None
    else:
        raise AdapterError("schema", f"{event}: {field} ist keine Zahl")
    if not math.isfinite(out):
        raise AdapterError("schema", f"{event}: {field} ist keine endliche Zahl")
    return int(out) if out.is_integer() else out


def _time(value, field: str, event: str, now: dt.datetime, allow_future=False):
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AdapterError("schema", f"{event}: {field} ist kein Zeitstempel")
    raw = value.strip()
    parsed = None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        for pattern in HUMAN_DATES:
            try:
                parsed = dt.datetime.strptime(raw, pattern)
                break
            except ValueError:
                pass
    if parsed is None:
        raise AdapterError("schema", f"{event}: {field} ist kein unterstützter GDACS-Zeitstempel")
    parsed = parsed.replace(tzinfo=dt.timezone.utc) if parsed.tzinfo is None else parsed.astimezone(dt.timezone.utc)
    if not allow_future and parsed > now + dt.timedelta(hours=2):
        raise AdapterError("sanity", f"{event}: {field} liegt mehr als 2 h in der Zukunft")
    return fmt(parsed)


def _report(properties: dict, eventtype: str, eventid: int, episodeid: int, event: str) -> str:
    direct = properties.get("link")
    urls = properties.get("url")
    report = direct if isinstance(direct, str) else urls.get("report") if isinstance(urls, dict) else None
    if not isinstance(report, str) or not report.startswith("https://"):
        raise AdapterError("schema", f"{event}: GDACS-Berichtslink fehlt/ist ungültig")
    parsed = urlparse(report)
    if parsed.hostname not in ("gdacs.org", "www.gdacs.org"):
        raise AdapterError("schema", f"{event}: GDACS-Berichtslink hat falschen Host")
    params = parse_qs(parsed.query)
    if params.get("eventtype") != [eventtype] or params.get("eventid") != [str(eventid)]:
        raise AdapterError("sanity", f"{event}: Bericht zeigt auf eine andere Meldung")
    if "episodeid" in params and params["episodeid"] != [str(episodeid)]:
        raise AdapterError("sanity", f"{event}: Bericht zeigt auf eine andere Episode")
    return report


def _countries(properties: dict, event: str) -> list[str]:
    raw = properties.get("affectedcountries")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise AdapterError("schema", f"{event}: affectedcountries ist keine Liste")
    out = []
    for row in raw:
        code = row.get("iso2") if isinstance(row, dict) else None
        if not isinstance(code, str) or not re.fullmatch(r"[A-Z]{2}", code):
            raise AdapterError("schema", f"{event}: ungültiges ISO-2-Land")
        if code not in out:
            out.append(code)
    return out


def _item(feature: dict, entry: dict, now: dt.datetime, expected_type: str, hazard_type: str) -> dict:
    if not isinstance(feature, dict) or feature.get("type") != "Feature":
        raise AdapterError("schema", "GDACS-Eintrag ist kein GeoJSON-Feature")
    p = feature.get("properties")
    if not isinstance(p, dict):
        raise AdapterError("schema", "GDACS-Eintrag hat keine properties")
    if p.get("eventtype") != expected_type:
        raise AdapterError("schema", f"unerwarteter GDACS-Typ {p.get('eventtype')!r}")

    eventid = _int_id(p.get("eventid"), "eventid", expected_type)
    event = f"{expected_type}:{eventid}"
    episodeid = _int_id(p.get("episodeid"), "episodeid", event)
    title = p.get("name")
    if not isinstance(title, str) or not 3 <= len(title) <= 300:
        raise AdapterError("schema", f"{event}: Name fehlt/ist ungültig")

    geometry = feature.get("geometry")
    coords = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if not isinstance(geometry, dict) or geometry.get("type") != "Point" or not isinstance(coords, list) or len(coords) < 2:
        raise AdapterError("schema", f"{event}: erwarteter GDACS-Zentroid fehlt")
    lon = _number(coords[0], "lon", event)
    lat = _number(coords[1], "lat", event)
    if lon is None or lat is None or not -180 <= lon <= 180 or not -90 <= lat <= 90:
        raise AdapterError("sanity", f"{event}: ungültige Koordinaten")

    report = _report(p, expected_type, eventid, episodeid, event)
    alert = p.get("alertlevel")
    try:
        level = level_obj(entry, SCHEME, alert)
    except (KeyError, TypeError):
        raise AdapterError("schema", f"{event}: unbekannte GDACS-Stufe {alert!r}") from None

    occurred = _time(p.get("fromdate"), "fromdate", event, now)
    if occurred is None:
        raise AdapterError("schema", f"{event}: fromdate fehlt")
    ended = _time(p.get("todate"), "todate", event, now, allow_future=True)
    updated = _time(p.get("datemodified"), "datemodified", event, now) if p.get("datemodified") is not None else None
    if occurred and ended and occurred > ended:
        raise AdapterError("sanity", f"{event}: todate liegt vor fromdate")

    metrics = {"hazard_type": hazard_type, "episode_id": episodeid}
    score = _number(p.get("alertscore"), "alertscore", event)
    if score is not None:
        metrics["alert_score"] = score
    severity_raw = p.get("severitydata")
    severity = severity_raw.get("severity") if isinstance(severity_raw, dict) else p.get("severity")
    severity = _number(severity, "severity", event)
    if severity is not None:
        metrics["severity"] = severity
    unit = severity_raw.get("severityunit") if isinstance(severity_raw, dict) else None
    if isinstance(unit, str) and unit:
        metrics["severity_unit"] = unit[:40]
    eventname = p.get("eventname")
    if isinstance(eventname, str) and eventname.strip():
        metrics["event_name"] = eventname.strip()[:120]

    current = p.get("iscurrent")
    if current is not None and current not in ("true", "false"):
        raise AdapterError("schema", f"{event}: iscurrent unbekannt")

    return {
        "id": f"{entry['id']}:{eventid}",
        "kind": "event",
        "domain": entry["domain"],
        "source": entry["id"],
        "provenance": "original",
        "original_publisher": None,
        "title": title,
        "lang": "en",
        "url": report,
        "occurred_at": occurred,
        "published_at": None,
        "observed_at": None,
        "source_updated_at": updated,
        "ongoing": None,
        "data_status": "unknown",
        "source_status_raw": current,
        "level": level,
        "location": {
            "precision": "region",
            "name": title[:120],
            "countries": _countries(p, event),
            "lat": round(float(lat), 4),
            "lon": round(float(lon), 4),
        },
        "metrics": metrics,
    }


def _parse(raw: bytes, now: dt.datetime, entry: dict, expected_type: str, hazard_type: str) -> FetchResult:
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
        p = feature["properties"]
        if p.get("eventtype") != expected_type:
            continue
        geometry = feature.get("geometry")
        # The drought bulk file contains both one centroid and one polygon per event.
        # ConflictWatch V1 publishes only source-supplied centroids; polygons are not
        # silently converted into points and do not become duplicate events.
        if not isinstance(geometry, dict) or geometry.get("type") != "Point":
            continue
        if p.get("Class") not in (None, "Point_Centroid"):
            continue
        item = _item(feature, entry, now, expected_type, hazard_type)
        if item["id"] in seen:
            raise AdapterError("sanity", f"mehrere GDACS-Zentroide für {item['id']}")
        seen.add(item["id"])
        items.append(item)

    return FetchResult(items=items, complete=False, items_in_window=len(items))


def parse_volcano(raw: bytes, now: dt.datetime, entry: dict) -> FetchResult:
    return _parse(raw, now, entry, "VO", "volcano")


def parse_drought(raw: bytes, now: dt.datetime, entry: dict) -> FetchResult:
    return _parse(raw, now, entry, "DR", "drought")
