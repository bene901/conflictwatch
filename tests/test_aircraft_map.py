"""Aircraft observations remain opt-in and separate from conflict events."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT


class AircraftMap(unittest.TestCase):
    def probe(self, status="ok", observed_at="2026-09-22T19:00:00Z", toggles=None):
        if shutil.which("node") is None:
            self.skipTest("node unavailable")
        doc = {
            "sources": [], "items": [],
            "aircraftSnapshot": {
                "schema_version": 1, "status": status, "observed_at": observed_at,
                "aircraft": [{
                    "id": "abc123", "lat": 52.5, "lon": 13.4,
                    "position_time": "2026-09-22T18:59:58Z",
                    "callsign": "TEST", "aircraft_type": "C30J",
                }],
            },
            "toggles": toggles or [],
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(doc, fh)
            name = fh.name
        try:
            run = subprocess.run(
                ["node", str(ROOT / "tests/js/map_probe.js"), name],
                capture_output=True, text=True, timeout=30, check=True,
            )
            return json.loads(run.stdout)
        finally:
            Path(name).unlink(missing_ok=True)

    @staticmethod
    def aircraft_markers(step):
        return [m for m in step["result"]["markers"]
                if any("map-event-aircraft" in str(s["cls"]) for s in m["shapes"])]

    def test_aircraft_snapshot_is_off_by_default_then_opt_in(self):
        steps = self.probe(toggles=[{"id": "map-filter-aircraft", "checked": True}])
        self.assertEqual(self.aircraft_markers(steps[1]), [])
        self.assertEqual(len(self.aircraft_markers(steps[2])), 1)
        self.assertIn("kein Live-Tracking", steps[2]["result"]["legend"]["text"])
        boxes = steps[1]["result"]["filters"]["boxes"]
        self.assertIn("map-filter-aircraft", [b["id"] for b in boxes])

    def test_expired_snapshot_disables_aircraft_overlay(self):
        steps = self.probe(observed_at="2026-09-22T15:00:00Z",
                           toggles=[{"id": "map-filter-aircraft", "checked": True}])
        self.assertEqual(self.aircraft_markers(steps[1]), [])
        self.assertEqual(self.aircraft_markers(steps[-1]), [])
        self.assertTrue(steps[-1].get("missing", False))

    def test_upstream_failure_does_not_show_aircraft(self):
        steps = self.probe(status="unavailable")
        self.assertEqual(self.aircraft_markers(steps[-1]), [])
        self.assertNotIn("map-filter-aircraft",
                         [b["id"] for b in steps[-1]["result"]["filters"]["boxes"]])


if __name__ == "__main__":
    unittest.main()
