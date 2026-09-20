"""One-off, read-only live check of the official GDACS feed in a GitHub runner."""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json

from cw.adapters import gdacs
from cw.http import fetch
from tests.test_gdacs import ENTRY


def main():
    url = ENTRY["endpoints"][0]
    raw = fetch(url)
    path = Path("raw/gdacs_live.json")
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(raw)  # preserve bytes even if parsing fails
    doc = json.loads(raw)
    kinds = Counter(f.get("properties", {}).get("eventtype", "missing")
                    for f in doc.get("features", []) if isinstance(f, dict))
    print(f"GDACS raw: {len(raw)} bytes, SHA256 {sha256(raw).hexdigest()}")
    print(f"Feature types in full feed: {dict(sorted(kinds.items()))}")
    result = gdacs.parse(raw, datetime.now(timezone.utc), ENTRY)
    print(f"Parsed: {len(result.items)} relevant events; complete={result.complete}")
    print("Sample IDs:", [item["id"] for item in result.items[:10]])
    archive_url = "https://www.gdacs.org/contentdata/xml/gdacs_archive.geojson"
    try:
        archived = fetch(archive_url)
        archive_doc = json.loads(archived)
        archive_kinds = Counter(f.get("properties", {}).get("eventtype", "missing")
                                for f in archive_doc.get("features", []) if isinstance(f, dict))
        Path("raw/gdacs_archive.geojson").write_bytes(archived)
        print(f"GDACS archive: {len(archived)} bytes, SHA256 {sha256(archived).hexdigest()}")
        print(f"Archived feature types: {dict(sorted(archive_kinds.items()))}")
    except Exception as exc:
        print(f"Optional archive unavailable: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
