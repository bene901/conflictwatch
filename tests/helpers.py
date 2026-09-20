"""Testhilfen. Abgeleitete Fixtures entstehen hier als BEARBEITETE KOPIEN der echten USGS-Antwort
(tests/fixtures/usgs/real_*.json); jede Änderung ist im Funktionsnamen benannt."""
import copy
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "tests" / "fixtures" / "usgs" / "real_2026-09-19_significant_week.json"
# Zeitpunkt kurz nach der Erzeugung der echten Antwort (metadata.generated = 2026-09-19T13:08:51Z)
NOW = dt.datetime(2026, 9, 19, 13, 17, 0, tzinfo=dt.timezone.utc)


def full_registry():
    """Production registry, including internal, non-public integrations."""
    return json.loads((ROOT / "registry.json").read_text(encoding="utf-8"))


def registry():
    """Isolated USGS fixture for the original USGS-only regression suite."""
    r = full_registry()
    r["sources"] = [source for source in r["sources"] if source["id"] == "usgs"]
    r["domains"] = [domain for domain in r["domains"] if domain["id"] == "disaster"]
    return r


def usgs_entry():
    return registry()["sources"][0]


def real_doc():
    return json.loads(REAL.read_text(encoding="utf-8"))


def raw(doc) -> bytes:
    return json.dumps(doc).encode()


def derived(mutator):
    doc = copy.deepcopy(real_doc())
    mutator(doc)
    return doc


def feature(doc):
    return doc["features"][0]


def add_second_event(doc, fid="us7000zz99", hours_later=3, alert=None):
    f = copy.deepcopy(feature(doc))
    f["id"] = fid
    f["properties"]["ids"] = f",{fid},"
    f["properties"]["time"] += hours_later * 3600 * 1000
    f["properties"]["updated"] = f["properties"]["time"] + 600_000
    f["properties"]["alert"] = alert
    f["properties"]["title"] = "M 5.8 - derived test event"
    f["properties"]["url"] = f"https://earthquake.usgs.gov/earthquakes/eventpage/{fid}"
    doc["features"].append(f)
    doc["metadata"]["count"] = len(doc["features"])


def at(minutes=0, hours=0, days=0):
    return NOW + dt.timedelta(minutes=minutes, hours=hours, days=days)
