"""Collect one authentic NOAA scales response for an isolated schema probe.

The response is saved only as a short-lived GitHub Actions artifact. This script
does not change registry.json, data-state, or the public website.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

from cw.adapters import noaa_swpc
from cw.errors import AdapterError
from cw.http import fetch
from tests.test_noaa_draft import entry

URL = "https://services.swpc.noaa.gov/products/noaa-scales.json"


def main() -> int:
    output = Path("raw-noaa")
    output.mkdir(exist_ok=True)
    raw = fetch(URL, timeout=20, max_bytes=5_000_000)
    (output / "noaa-scales-original.json").write_bytes(raw)
    print(f"Source: {URL}")
    print(f"Raw bytes: {len(raw)}")
    print(f"Raw SHA-256: {hashlib.sha256(raw).hexdigest()}")
    doc = json.loads(raw)
    if not isinstance(doc, dict):
        print("Unexpected root type", type(doc).__name__)
        return 2
    print("Top-level block keys:", sorted(doc.keys()))
    current = doc.get("0")
    if isinstance(current, dict):
        print("Latest-observed keys:", sorted(current.keys()))
        print("Observation date/time:", current.get("DateStamp"), current.get("TimeStamp"))
        for k in "GSR":
            scale = current.get(k)
            print(f"Latest {k}:", scale.get("Scale") if isinstance(scale, dict) else "(missing)")
    try:
        parsed = noaa_swpc.parse(raw, dt.datetime.now(dt.timezone.utc), entry())
    except AdapterError as exc:
        print(f"Adapter rejected authentic NOAA feed: {exc.kind}: {exc.detail}")
        return 2
    print("Adapter accepted: count", len(parsed.items), "complete", parsed.complete)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
