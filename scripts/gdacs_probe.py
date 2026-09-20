"""One-off, read-only live check of the official GDACS feed in a GitHub runner."""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
from urllib.request import Request, urlopen

from cw.adapters import gdacs
from cw.http import MAX_BYTES, USER_AGENT, fetch
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
    archive_url = "https://www.gdacs.org/contentdata/xml/archive.geojson"
    try:
        request = Request(archive_url, headers={"User-Agent": USER_AGENT,
                                                "Accept": "application/geo+json,application/json"})
        with urlopen(request, timeout=20) as response:
            archived = response.read(MAX_BYTES + 1)
        if len(archived) > MAX_BYTES:
            raise ValueError("GDACS archive exceeds size cap")
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
