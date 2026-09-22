"""GDELT 2.0 Event feed: narrow, explicitly unverified military/conflict signals."""
from __future__ import annotations

import csv
import datetime as dt
import io
import re
import zipfile
from urllib.parse import urlparse

from ..errors import AdapterError
from ..timeutil import fmt
from .base import FetchResult

SOURCE = "gdelt"
FETCH_WINDOWS = 8
MAX_UNPACKED = 12_000_000
WATCH = {
    "138": "Militärische Drohung",
    "139": "Ultimatum",
    "152": "Erhöhte militärische Bereitschaft",
    "154": "Militärische Mobilisierung oder Verstärkung",
    "190": "Einsatz konventioneller militärischer Gewalt",
    "191": "Blockade oder Bewegungsbeschränkung",
    "192": "Besetzung",
    "193": "Kampf mit Hand- oder leichten Waffen",
    "194": "Kampf mit Artillerie oder Panzern",
    "195": "Einsatz von Luftwaffen",
    "196": "Verstoß gegen Waffenruhe",
}
FALLBACK_URL = "https://www.gdeltproject.org/"


def _unpack(raw: bytes, expected_stamp: str) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = [i for i in zf.infolist() if not i.is_dir()]
            if len(names) != 1 or not names[0].filename.endswith(".export.CSV"):
                raise AdapterError("schema", f"GDELT {expected_stamp}: unerwarteter ZIP-Inhalt")
            if names[0].file_size > MAX_UNPACKED:
                raise AdapterError("size", f"GDELT {expected_stamp}: entpackt größer als {MAX_UNPACKED} Bytes")
            return zf.read(names[0])
    except AdapterError:
        raise
    except zipfile.BadZipFile:
        raise AdapterError("parse", f"GDELT {expected_stamp}: ungültiges ZIP") from None


def fetch_recent(fetcher, entry: dict) -> bytes:
    index = fetcher(entry["endpoints"][0])
    try:
        text = index.decode("ascii")
    except UnicodeDecodeError:
        raise AdapterError("parse", "GDELT lastupdate.txt ist nicht ASCII") from None
    latest_url = None
    for line in text.splitlines():
        for token in line.split():
            if token.endswith(".export.CSV.zip"):
                latest_url = token
                break
        if latest_url:
            break
    if not latest_url:
        raise AdapterError("schema", "GDELT lastupdate.txt enthält keinen Export")
    m = re.search(r"/(\d{14})\.export\.CSV\.zip$", latest_url)
    if not m:
        raise AdapterError("schema", "GDELT-Exportname enthält keinen Zeitstempel")
    try:
        latest = dt.datetime.strptime(m.group(1), "%Y%m%d%H%M%S").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        raise AdapterError("schema", "GDELT-Exportzeit ist ungültig") from None

    chunks = []
    for offset in range(FETCH_WINDOWS):
        stamp = (latest - dt.timedelta(minutes=15 * offset)).strftime("%Y%m%d%H%M%S")
        url = f"https://data.gdeltproject.org/gdeltv2/{stamp}.export.CSV.zip"
        try:
            packed = fetcher(url)
        except AdapterError:
            if offset == 0:
                raise
            continue
        chunks.append(_unpack(packed, stamp))
    if not chunks:
        raise AdapterError("network", "kein GDELT-Export abrufbar")
    return b"\n".join(chunks)


def _day(value: str, event_id: str, now: dt.datetime) -> str:
    try:
        day = dt.datetime.strptime(value, "%Y%m%d").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        raise AdapterError("schema", f"{event_id}: SQLDATE ungültig") from None
    if day > now + dt.timedelta(days=2):
        raise AdapterError("sanity", f"{event_id}: Ereignisdatum liegt in der Zukunft")
    return fmt(day)


def _captured(value: str, event_id: str, now: dt.datetime) -> str:
    try:
        t = dt.datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        raise AdapterError("schema", f"{event_id}: DATEADDED ungültig") from None
    if t > now + dt.timedelta(hours=2):
        raise AdapterError("sanity", f"{event_id}: Erfassungszeit liegt mehr als 2 h in der Zukunft")
    return fmt(t)


def _count(value: str, field: str, event_id: str):
    if value == "":
        return None
    try:
        n = int(value)
    except ValueError:
        raise AdapterError("schema", f"{event_id}: {field} ist keine Ganzzahl") from None
    if n < 0:
        raise AdapterError("schema", f"{event_id}: {field} ist negativ")
    return n


def _category(code: str):
    return next(((prefix, label) for prefix, label in WATCH.items() if code.startswith(prefix)), None)


def parse(raw: bytes, now: dt.datetime, entry: dict) -> FetchResult:
    text = raw.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text), delimiter="\t")
    by_id = {}
    for row in reader:
        if not row:
            continue
        if len(row) < 61:
            raise AdapterError("schema", f"GDELT-Zeile hat nur {len(row)} statt 61 Feldern")
        if row[25] != "1":
            continue
        found = _category(row[26].strip())
        if found is None:
            continue
        _, category = found
        gid = row[0].strip()
        if not re.fullmatch(r"\d{1,30}", gid):
            raise AdapterError("schema", f"ungültige GDELT-ID {gid!r}")
        item_id = f"{SOURCE}:{gid}"
        if item_id in by_id:
            continue

        occurred = _day(row[1].strip(), gid, now)
        captured = _captured(row[59].strip(), gid, now)
        actor1 = row[6].strip()[:120] or "Akteur 1 nicht erkannt"
        actor2 = row[16].strip()[:120] or "Akteur 2 nicht erkannt"
        lat_raw, lon_raw = row[56].strip(), row[57].strip()
        lat = lon = None
        if lat_raw or lon_raw:
            if not lat_raw or not lon_raw:
                raise AdapterError("schema", f"{gid}: unvollständige ActionGeo-Koordinate")
            try:
                lat, lon = float(lat_raw), float(lon_raw)
            except ValueError:
                raise AdapterError("schema", f"{gid}: ActionGeo-Koordinate ist keine Zahl") from None
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise AdapterError("sanity", f"{gid}: ActionGeo-Koordinate außerhalb des Wertebereichs")
        geo_type = row[51].strip()
        if lat is None:
            precision, location_name = "unknown", None
        else:
            precision = "country" if geo_type == "1" else "region"
            location_name = row[52].strip()[:120] or None

        source_url = row[60].strip()
        parsed_url = urlparse(source_url)
        url = source_url if parsed_url.scheme == "https" and parsed_url.hostname else FALLBACK_URL
        publisher = parsed_url.hostname[:120] if parsed_url.hostname else None
        by_id[item_id] = {
            "id": item_id, "kind": "event", "domain": entry["domain"], "source": SOURCE,
            "provenance": "claim", "original_publisher": publisher,
            "title": f"{category}: {actor1} → {actor2}"[:300], "lang": "de", "url": url,
            "occurred_at": occurred, "published_at": None, "observed_at": None,
            "source_updated_at": captured, "ongoing": None, "data_status": "unknown",
            "source_status_raw": row[26].strip()[:40] or None, "level": None,
            "location": {"precision": precision, "name": location_name, "countries": [],
                         "lat": round(lat, 4) if lat is not None else None,
                         "lon": round(lon, 4) if lon is not None else None},
            "metrics": {"cameo_code": row[26].strip(), "cameo_category": category,
                        "actor1": actor1, "actor2": actor2,
                        "mentions": _count(row[31].strip(), "NumMentions", gid),
                        "sources": _count(row[32].strip(), "NumSources", gid),
                        "articles": _count(row[33].strip(), "NumArticles", gid),
                        "automated_unverified": True},
        }
    return FetchResult(items=list(by_id.values()), complete=False, items_in_window=len(by_id))
