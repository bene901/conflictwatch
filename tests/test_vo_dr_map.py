"""Volcano/drought map integration: real normalized items reach distinct map controls."""
import datetime as dt
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from cw import snapshot
from cw.adapters import gdacs_vo_dr
from cw.merge import blank_source_state, merge_items, succeed_source_state
from cw.registry import load
from tests.helpers import ROOT
from tests.test_recency_basis import build

NOW = dt.datetime(2026, 9, 21, 10, 45, tzinfo=dt.timezone.utc)
RUN_AT = "2026-09-21T10:45:00Z"
REG = load(ROOT / "registry.json")
VO = next(s for s in REG["sources"] if s["id"] == "gdacs-volcano")
DR = next(s for s in REG["sources"] if s["id"] == "gdacs-drought")
VO_FEATURE = json.loads((ROOT / "tests/fixtures/gdacs/real_2026-09-21_vo_event.json").read_text())
DR_FEATURE = json.loads((ROOT / "tests/fixtures/gdacs/real_2026-09-21_dr_centroid.json").read_text())
PROBE = ROOT / "tests/js/map_probe.js"


def raw(feature):
    return json.dumps({"type": "FeatureCollection", "features": [feature]}).encode()


def scenario():
    vo_result = gdacs_vo_dr.parse_volcano(raw(VO_FEATURE), NOW, VO)
    dr_result = gdacs_vo_dr.parse_drought(raw(DR_FEATURE), NOW, DR)
    items = merge_items({}, VO["id"], VO, vo_result, RUN_AT)
    items = merge_items(items, DR["id"], DR, dr_result, RUN_AT)
    states = [
        succeed_source_state(blank_source_state(VO["id"], "1.0.0"), VO, vo_result,
                             items, RUN_AT, "1.0.0"),
        succeed_source_state(blank_source_state(DR["id"], "1.0.0"), DR, dr_result,
                             items, RUN_AT, "1.0.0"),
    ]
    reg, items_doc, sources_doc = build(items, states, RUN_AT)
    return snapshot.build(items_doc, sources_doc, reg, "abc1234", RUN_AT,
                          include_unreleased=True)


def run_map(toggles=None):
    if shutil.which("node") is None:
        raise unittest.SkipTest("node nicht verfuegbar - Karte nicht ausgefuehrt")
    snap = scenario()
    payload = {"items": snap["items"], "sources": snap["sources"],
               "toggles": list(toggles or [])}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(payload, fh)
        name = fh.name
    try:
        out = subprocess.run([str(shutil.which("node")), str(PROBE), name],
                             capture_output=True, text=True, timeout=60, check=True)
    finally:
        Path(name).unlink(missing_ok=True)
    return json.loads(out.stdout)


def region_labels(step):
    return [m["ariaLabel"] for m in step["result"]["markers"]
            if any(s["cls"] and "map-event-region" in s["cls"].split()
                   for s in m["shapes"])]


class VolcanoDroughtMap(unittest.TestCase):
    def test_both_hazards_get_separate_filters_and_region_markers(self):
        initial = run_map()[0]["result"]
        boxes = {b["id"]: b for b in initial["filters"]["boxes"]}
        self.assertIn("map-filter-volcano", boxes)
        self.assertIn("map-filter-drought", boxes)
        self.assertIn("Vulkane", boxes["map-filter-volcano"]["label"])
        self.assertIn("Dürren", boxes["map-filter-drought"]["label"])
        labels = " ".join(region_labels({"result": initial}))
        self.assertIn("Vulkan:", labels)
        self.assertIn("Dürre:", labels)
        self.assertIn("ungefähre Lage laut GDACS", labels)

    def test_hiding_drought_does_not_hide_volcano(self):
        steps = run_map([{"id": "map-filter-drought", "checked": False}])
        labels = " ".join(region_labels(steps[-1]))
        self.assertIn("Vulkan:", labels)
        self.assertNotIn("Dürre:", labels)


if __name__ == "__main__":
    unittest.main()
