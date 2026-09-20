"""USGS-Adapter (Summary-GeoJSON, Feed der signifikanten Beben).

Geprüft an einer echten Antwort vom 19.09.2026 (tests/fixtures/usgs/real_*.json).
Feldbedeutungen laut ComCat-Dokumentation; siehe docs/USGS.md.
"""
from __future__ import annotations
import datetime as dt
import json
import re

from ..errors import AdapterError
from ..registry import level_obj
from ..timeutil import fmt, from_epoch_ms
from .base import FetchResult

SOURCE = "usgs"
SCHEME = "usgs-pager"
STATUS_MAP = {"automatic": "preliminary", "reviewed": "reviewed", "deleted": "withdrawn"}
URL_PREFIX = "https://earthquake.usgs.gov/"
ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
MAX_FUTURE = dt.timedelta(hours=2)


def _num(value, name, feature_id, allow_null=False):
    if value is None and allow_null:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdapterError("schema", f"{feature_id}: {name} ist keine Zahl")
    return value


def _feature(f: dict, entry: dict, now: dt.datetime) -> tuple[dict, list[str]]:
    if not isinstance(f, dict) or f.get("type") != "Feature":
        raise AdapterError("schema", "Eintrag ist kein GeoJSON-Feature")
    fid = f.get("id")
    if not isinstance(fid, str) or not ID_RE.match(fid):
        raise AdapterError("schema", f"ungültige Feature-ID {fid!r}")
    p, g = f.get("properties"), f.get("geometry")
    if not isinstance(p, dict) or not isinstance(g, dict):
        raise AdapterError("schema", f"{fid}: properties/geometry fehlen")

    for key in ("time", "updated", "title", "url", "status"):
        if key not in p:
            raise AdapterError("schema", f"{fid}: Pflichtfeld {key} fehlt")
    try:
        occurred = from_epoch_ms(p["time"])
        updated = from_epoch_ms(p["updated"])
    except (TypeError, ValueError, OverflowError, OSError):
        raise AdapterError("schema", f"{fid}: time/updated keine Epoch-Millisekunden") from None
    if occurred > now + MAX_FUTURE or updated > now + MAX_FUTURE:
        raise AdapterError("sanity", f"{fid}: Zeitpunkt mehr als 2 h in der Zukunft")

    title, url, status = p["title"], p["url"], p["status"]
    if not isinstance(title, str) or not 3 <= len(title) <= 300:
        raise AdapterError("schema", f"{fid}: title ungültig")
    if not isinstance(url, str) or not url.startswith(URL_PREFIX):
        raise AdapterError("schema", f"{fid}: url nicht auf earthquake.usgs.gov")
    if status not in STATUS_MAP:
        raise AdapterError("schema", f"{fid}: unbekannter status {status!r}")

    alert = p.get("alert")
    if alert is None:
        level = None
    else:
        try:
            level = level_obj(entry, SCHEME, alert)
        except KeyError:
            raise AdapterError("schema", f"{fid}: unbekannte PAGER-Stufe {alert!r}") from None

    coords = g.get("coordinates")
    if g.get("type") != "Point" or not isinstance(coords, list) or len(coords) < 2:
        raise AdapterError("schema", f"{fid}: Geometrie ist kein Punkt")
    lon = _num(coords[0], "lon", fid)
    lat = _num(coords[1], "lat", fid)
    depth = _num(coords[2], "depth", fid, allow_null=True) if len(coords) > 2 else None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise AdapterError("sanity", f"{fid}: Koordinaten außerhalb des Wertebereichs")

    place = p.get("place")
    mag = _num(p.get("mag"), "mag", fid, allow_null=True)
    mag_type = p.get("magType") if isinstance(p.get("magType"), str) else None

    item = {
        "id": f"{SOURCE}:{fid}",
        "kind": "event",
        "domain": entry["domain"],
        "source": SOURCE,
        "provenance": "original",
        "original_publisher": None,
        "title": title,
        "lang": "en",
        "url": url,
        "occurred_at": fmt(occurred),
        "published_at": None,
        "observed_at": None,
        "source_updated_at": fmt(updated),
        "ongoing": None,
        "data_status": STATUS_MAP[status],
        "source_status_raw": status,
        "level": level,
        "location": {
            "precision": "point",
            "name": place[:120] if isinstance(place, str) and place else None,
            "countries": [],  # USGS liefert keinen Ländercode; wir raten nicht.
            "lat": round(float(lat), 4),
            "lon": round(float(lon), 4),
        },
        # Bewusst NICHT übernommen: tsunami (Regions-Flag, keine Warnung), sig, mmi, cdi, felt.
        "metrics": {
            "magnitude": mag,
            "magnitude_type": mag_type,
            "depth_km": depth,
        },
    }
    aliases = []
    ids = p.get("ids")
    if isinstance(ids, str):
        aliases = [f"{SOURCE}:{a}" for a in ids.split(",") if a and a != fid and ID_RE.match(a)]
    return item, aliases


def parse(raw: bytes, now: dt.datetime, entry: dict) -> FetchResult:
    try:
        doc = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise AdapterError("parse", "Antwort ist kein gültiges JSON") from None
    if not isinstance(doc, dict) or doc.get("type") != "FeatureCollection":
        raise AdapterError("schema", "keine FeatureCollection")
    meta, features = doc.get("metadata"), doc.get("features")
    if not isinstance(meta, dict) or not isinstance(features, list):
        raise AdapterError("schema", "metadata/features fehlen")
    count = meta.get("count")
    if isinstance(count, bool) or not isinstance(count, int):
        raise AdapterError("schema", "metadata.count fehlt")

    items, aliases, seen = [], {}, set()
    for f in features:
        item, al = _feature(f, entry, now)
        if item["id"] in seen:
            raise AdapterError("sanity", f"doppelte ID {item['id']}")
        seen.add(item["id"])
        items.append(item)
        aliases[item["id"]] = al

    # Summary-Feeds sind nicht paginiert: Abweichung = inkonsistente Antwort, kein Teilabruf.
    if count != len(features):
        raise AdapterError("sanity", f"metadata.count={count}, geliefert {len(features)} Features")
    return FetchResult(items=items, complete=True, aliases=aliases, items_in_window=len(items))
