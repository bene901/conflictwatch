import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT

PROBE = ROOT / "tests" / "js" / "map_probe.js"
T = "2026-09-22T15:45:00Z"


def src(source_id, newest=T):
    return {
        "id": source_id,
        "last_success_at": T,
        "newest_source_time": newest,
        "highlight": {"recency_basis": "display_time",
                      "window_h": 720 if source_id == "ucdp-candidate" else 168},
    }


def item(source_id, iid, title, occurred, lon, lat, precision="region", metrics=None):
    return {
        "id": source_id + ":" + iid, "kind": "event", "domain": "conflict",
        "source": source_id, "title": title, "occurred_at": occurred,
        "published_at": None, "observed_at": None, "last_seen_at": T,
        "location": {"precision": precision, "name": "Testort", "countries": [],
                     "lat": lat, "lon": lon}, "metrics": metrics or {},
    }


def run_map(toggles=None):
    if shutil.which("node") is None:
        raise unittest.SkipTest("node nicht verfügbar")
    snap = {
        "sources": [src("ucdp-candidate", "2026-08-31T00:00:00Z"), src("gdelt")],
        "items": [
            item("ucdp-candidate", "1", "UCDP Ereignis", "2026-08-20T00:00:00Z", 10, 10, "point",
                 {"violence_type": "state-based"}),
            item("gdelt", "2", "GDELT Meldung", "2026-09-22T00:00:00Z", 40, 10, "region",
                 {"cameo_code": "195", "cameo_category": "Einsatz von Luftwaffen"}),
        ],
        "toggles": toggles or [],
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(snap, fh)
        name = fh.name
    try:
        out = subprocess.run(["node", str(PROBE), name], capture_output=True, text=True,
                             timeout=30, check=True)
    finally:
        Path(name).unlink(missing_ok=True)
    return json.loads(out.stdout)


def conflict_markers(step):
    return [m for m in step["result"]["markers"]
            if any("map-event-conflict" in (s["cls"] or "") for s in m["shapes"])]


class ConflictMap(unittest.TestCase):
    def test_conflict_sources_are_separate_from_natural_event_markers(self):
        step = run_map()[0]
        markers = conflict_markers(step)
        self.assertEqual(len(markers), 2)
        text = " ".join(m["ariaLabel"] for m in markers)
        self.assertIn("UCDP", text)
        self.assertIn("automatisch aus Nachrichten erkannt, ungeprüft", text)
        for marker in markers:
            classes = " ".join(s["cls"] or "" for s in marker["shapes"])
            self.assertNotIn("map-event-point", classes)
            self.assertNotIn("map-event-region", classes)

    def test_ucdp_monthly_scope_survives_default_live_24h_filter(self):
        text = " ".join(m["ariaLabel"] for m in conflict_markers(run_map()[0]))
        self.assertIn("UCDP", text)
        self.assertIn("GDELT", text)

    def test_conflict_marker_accepts_realistic_touch_tap(self):
        steps = run_map([{"touchMarkerLabelIncludes": "GDELT Meldung"}])
        self.assertTrue(steps[-1]["result"]["selections"])
        self.assertTrue(steps[-1]["result"]["selections"][-1].endswith(":2"))

    def test_military_action_filter_can_isolate_gdelt_action_type(self):
        steps = run_map([{"id": "map-filter-military-action", "value": "air"}])
        self.assertFalse(steps[-1].get("missing", False))
        text = " ".join(m["ariaLabel"] for m in conflict_markers(steps[-1]))
        self.assertIn("GDELT", text)

        steps = run_map([{"id": "map-filter-military-action", "value": "heavy-arms"}])
        text = " ".join(m["ariaLabel"] for m in conflict_markers(steps[-1]))
        self.assertNotIn("GDELT", text)
        self.assertIn("UCDP", text)

    def test_ucdp_conflict_type_filter_is_independent_from_gdelt(self):
        steps = run_map([{"id": "map-filter-ucdp-type", "value": "one-sided"}])
        text = " ".join(m["ariaLabel"] for m in conflict_markers(steps[-1]))
        self.assertNotIn("UCDP", text)
        self.assertIn("GDELT", text)

    def test_conflict_filter_selects_offer_all_supported_categories(self):
        step = run_map()[0]
        selects = {x["id"]: x for x in step["result"]["filters"]["selects"]}
        self.assertIn("map-filter-military-action", selects)
        self.assertEqual(
            selects["map-filter-military-action"]["options"],
            ["all", "threat", "readiness", "force", "blockade", "occupation",
             "small-arms", "heavy-arms", "air", "ceasefire"],
        )
        self.assertIn("map-filter-ucdp-type", selects)
        self.assertEqual(
            selects["map-filter-ucdp-type"]["options"],
            ["all", "state-based", "non-state", "one-sided"],
        )

    def test_gdelt_filter_hides_only_gdelt(self):
        steps = run_map([{"id": "map-filter-conflict-gdelt", "checked": False}])
        before = " ".join(m["ariaLabel"] for m in conflict_markers(steps[0]))
        after = " ".join(m["ariaLabel"] for m in conflict_markers(steps[1]))
        self.assertIn("GDELT", before)
        self.assertNotIn("GDELT", after)
        self.assertIn("UCDP", after)


if __name__ == "__main__":
    unittest.main()
