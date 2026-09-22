"""Fetch a separate, short-lived ADS-B aircraft context snapshot for the public page.

Not a conflict event feed, not a historical flight tracker. Fail closed: a
failed upstream response never republishes an earlier aircraft position.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
from pathlib import Path

from cw import http
from cw.errors import AdapterError

ENDPOINT = "https://api.adsb.lol/v2/mil"
LICENSE = "https://opendatacommons.org/licenses/odbl/1-0/"
MAX_POSITION_AGE_SECONDS = 120
MAX_RESPONSE_AGE_SECONDS = 300
MAX_AIRCRAFT = 2000
UTC = dt.timezone.utc


def iso(when: dt.datetime) -> str:
    return when.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def numeric(value, minimum: float, maximum: float):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value) if minimum <= value <= maximum else None


def normalize(raw: bytes, fetched_at: dt.datetime) -> dict:
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("invalid_json") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("ac"), list):
        raise ValueError("invalid_schema")
    epoch = numeric(payload.get("now"), 0, 4102444800000)
    if epoch is None:
        raise ValueError("missing_source_time")
    observed_at = dt.datetime.fromtimestamp(epoch / 1000, tz=UTC)
    if abs((fetched_at - observed_at).total_seconds()) > MAX_RESPONSE_AGE_SECONDS:
        raise ValueError("outdated_source_response")

    aircraft = []
    seen = set()
    for row in payload["ac"]:
        if not isinstance(row, dict):
            continue
        ident = row.get("hex")
        if not isinstance(ident, str) or not re.fullmatch(r"[a-fA-F0-9]{6}", ident):
            continue
        ident = ident.lower()
        if ident in seen:
            continue
        seen.add(ident)
        # /mil is source classification, not evidence of affiliation or mission.
        if not isinstance(row.get("dbFlags"), int) or not (row["dbFlags"] & 1):
            continue
        lat = numeric(row.get("lat"), -90, 90)
        lon = numeric(row.get("lon"), -180, 180)
        seen_pos = numeric(row.get("seen_pos"), 0, MAX_POSITION_AGE_SECONDS)
        if lat is None or lon is None or seen_pos is None:
            continue
        record = {
            "id": ident,
            "lat": round(lat, 3),
            "lon": round(lon, 3),
            "position_time": iso(observed_at - dt.timedelta(seconds=seen_pos)),
            "callsign": str(row.get("flight") or "").strip()[:16],
            "aircraft_type": str(row.get("t") or "").strip()[:12],
        }
        altitude = numeric(row.get("alt_baro"), -2000, 100000)
        speed = numeric(row.get("gs"), 0, 2000)
        if altitude is not None:
            record["altitude_ft"] = round(altitude)
        if speed is not None:
            record["speed_kt"] = round(speed)
        aircraft.append(record)
        if len(aircraft) >= MAX_AIRCRAFT:
            raise ValueError("aircraft_limit_exceeded")

    return {
        "schema_version": 1,
        "status": "ok" if aircraft else "empty",
        "fetched_at": iso(fetched_at),
        "observed_at": iso(observed_at),
        "source": "adsb.lol /v2/mil",
        "license": LICENSE,
        "attribution": "© adsb.lol contributors · ODbL 1.0",
        "coverage_note": "Nur von adsb.lol als militärisch markierte und empfangene ADS-B/MLAT-Signale. Keine vollständige Militärflugliste; kein Nachweis eines Einsatzes.",
        "aircraft": aircraft,
    }


def build(fetcher=http.fetch, now=None) -> dict:
    fetched_at = now or dt.datetime.now(UTC)
    try:
        return normalize(fetcher(ENDPOINT), fetched_at)
    except (AdapterError, ValueError, OverflowError, OSError) as exc:
        # Do not reuse prior coordinates on outage: never show a stale position.
        return {
            "schema_version": 1,
            "status": "unavailable",
            "fetched_at": iso(fetched_at),
            "source": "adsb.lol /v2/mil",
            "license": LICENSE,
            "attribution": "© adsb.lol contributors · ODbL 1.0",
            "error_code": (exc.kind if isinstance(exc, AdapterError) else str(exc))[:80],
            "aircraft": [],
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    doc = build()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"ADS-B snapshot: {doc['status']} ({len(doc['aircraft'])} observations)")


if __name__ == "__main__":
    main()
