"""UCDP Candidate Events: monthly, preliminary georeferenced conflict events."""
from __future__ import annotations

import csv
import datetime as dt
import io
import re
from urllib.parse import urljoin, urlparse

from ..errors import AdapterError
from ..timeutil import fmt
from .base import FetchResult

SOURCE = "ucdp-candidate"
DATASET_URL = "https://ucdp.uu.se/downloads/"
LINK_RE = re.compile(
    r"""href=["']([^"']*candidateged/GEDEvent_v(\d+)_(\d+)_(\d+)\.csv(?:\?[^"']*)?)["']""",
    re.IGNORECASE,
)
VIOLENCE = {
    1: ("state-based", "Staatliche Gewalt"),
    2: ("non-state", "Nichtstaatliche Gewalt"),
    3: ("one-sided", "Einseitige Gewalt"),
}


def fetch_latest(fetcher, entry: dict) -> bytes:
    page_url = entry["endpoints"][0]
    raw = fetcher(page_url)
    try:
        html = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise AdapterError("parse", "UCDP-Downloadseite ist kein UTF-8") from None
    candidates = []
    for match in LINK_RE.finditer(html):
        href = match.group(1)
        version = tuple(int(match.group(i)) for i in (2, 3, 4))
        candidates.append((version, urljoin(page_url, href)))
    if not candidates:
        raise AdapterError("schema", "kein monatlicher UCDP-Candidate-CSV-Link gefunden")
    _, url = max(candidates)
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "ucdp.uu.se":
        raise AdapterError("sanity", "UCDP-Candidate-Link zeigt auf unerwarteten Host")
    return fetcher(url)


def _date(value: str, field: str, event_id: str, now: dt.datetime) -> tuple[str, str]:
    if not isinstance(value, str) or not value.strip():
        raise AdapterError("schema", f"{event_id}: {field} fehlt")
    # Der aktuelle Candidate-CSV exportiert Date-Felder als
    # "YYYY-MM-DD 00:00:00.000", obwohl das Codebook sie als Tagesdatum
    # beschreibt. date-only bleibt ebenfalls zulässig.
    try:
        parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise AdapterError("schema", f"{event_id}: {field} ist kein ISO-Datum") from None
    day = dt.datetime.combine(parsed.date(), dt.time.min, tzinfo=dt.timezone.utc)
    if day > now + dt.timedelta(days=2):
        raise AdapterError("sanity", f"{event_id}: {field} liegt in der Zukunft")
    return fmt(day), day.date().isoformat()


def _integer(value: str, field: str, event_id: str, allow_blank: bool = False):
    if value is None or str(value).strip() == "":
        if allow_blank:
            return None
        raise AdapterError("schema", f"{event_id}: {field} fehlt")
    try:
        number = float(str(value).strip())
    except ValueError:
        raise AdapterError("schema", f"{event_id}: {field} ist keine Zahl") from None
    if not number.is_integer() or number < 0:
        raise AdapterError("schema", f"{event_id}: {field} ist keine nichtnegative Ganzzahl")
    return int(number)


def _coordinate(value: str, field: str, event_id: str):
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        raise AdapterError("schema", f"{event_id}: {field} ist keine Zahl") from None


def _text(row: dict, *names: str, limit: int = 120):
    for name in names:
        value = row.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()[:limit]
    return None


def _fatality(row: dict, event_id: str, primary: str, fallback: str):
    value = row.get(primary)
    if value is None:
        value = row.get(fallback)
    return _integer(value, primary, event_id, allow_blank=True)


def parse(raw: bytes, now: dt.datetime, entry: dict) -> FetchResult:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise AdapterError("parse", "UCDP-Candidate-Datei ist kein UTF-8") from None
    reader = csv.DictReader(io.StringIO(text, newline=""))
    fields = set(reader.fieldnames or [])
    required = {
        "id", "type_of_violence", "side_a", "side_b", "date_start", "date_end",
        "date_prec", "where_prec", "latitude", "longitude",
    }
    missing = sorted(required - fields)
    if missing:
        raise AdapterError("schema", "UCDP-Pflichtfelder fehlen: " + ", ".join(missing))

    items, seen = [], set()
    for row in reader:
        raw_id = (row.get("id") or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", raw_id):
            raise AdapterError("schema", f"ungültige UCDP-ID {raw_id!r}")
        item_id = f"{SOURCE}:{raw_id}"
        if item_id in seen:
            raise AdapterError("sanity", f"doppelte UCDP-ID {item_id}")
        seen.add(item_id)

        violence_no = _integer(row.get("type_of_violence"), "type_of_violence", raw_id)
        if violence_no not in VIOLENCE:
            raise AdapterError("schema", f"{raw_id}: unbekannter type_of_violence {violence_no}")
        violence_key, violence_label = VIOLENCE[violence_no]
        occurred_at, _ = _date(row.get("date_start"), "date_start", raw_id, now)
        _, date_end = _date(row.get("date_end"), "date_end", raw_id, now)
        date_prec = _integer(row.get("date_prec"), "date_prec", raw_id)
        where_prec = _integer(row.get("where_prec"), "where_prec", raw_id)
        if where_prec < 1 or where_prec > 7:
            raise AdapterError("schema", f"{raw_id}: where_prec außerhalb 1..7")

        lat = _coordinate(row.get("latitude"), "latitude", raw_id)
        lon = _coordinate(row.get("longitude"), "longitude", raw_id)
        if (lat is None) != (lon is None):
            raise AdapterError("schema", f"{raw_id}: nur eine Koordinate vorhanden")
        if lat is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise AdapterError("sanity", f"{raw_id}: Koordinaten außerhalb des Wertebereichs")

        side_a = _text(row, "side_a", limit=120) or "Akteur A nicht angegeben"
        side_b = _text(row, "side_b", limit=120) or "Akteur B nicht angegeben"
        location_name = _text(row, "where_description", "where_coordinates", "country", limit=120)
        precision = "point" if where_prec == 1 else ("country" if where_prec == 6 else "region")

        low = _fatality(row, raw_id, "low", "low_est")
        best = _fatality(row, raw_id, "best", "best_est")
        high = _fatality(row, raw_id, "high", "high_est")
        inconsistent = bool(
            (low is not None and best is not None and low > best) or
            (best is not None and high is not None and best > high) or
            (low is not None and high is not None and low > high)
        )
        items.append({
            "id": item_id, "kind": "event", "domain": entry["domain"], "source": SOURCE,
            "provenance": "original", "original_publisher": None,
            "title": f"{violence_label}: {side_a} – {side_b}"[:300], "lang": "de",
            "url": DATASET_URL, "occurred_at": occurred_at, "published_at": None,
            "observed_at": None, "source_updated_at": None, "ongoing": None,
            "data_status": "preliminary", "source_status_raw": "candidate", "level": None,
            "location": {"precision": precision, "name": location_name, "countries": [],
                         "lat": round(lat, 4) if lat is not None else None,
                         "lon": round(lon, 4) if lon is not None else None},
            "metrics": {"violence_type": violence_key, "date_end": date_end,
                        "date_precision": date_prec, "location_precision": where_prec,
                        "fatalities_low": low, "fatalities_best": best, "fatalities_high": high,
                        "fatalities_inconsistent": inconsistent},
        })
    if not items:
        raise AdapterError("sanity", "UCDP-Candidate-Datei enthält keine Ereignisse")
    return FetchResult(items=items, complete=True, items_in_window=len(items))
