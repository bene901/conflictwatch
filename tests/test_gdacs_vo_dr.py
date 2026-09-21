"""GDACS volcano/drought feeds: authentic 2026 examples and normalization rules."""
import copy
import datetime as dt
import json
import unittest

from cw.adapters import gdacs_vo_dr
from cw.adapters import ADAPTERS
from cw.errors import AdapterError
from cw.registry import load
from cw.validate import check_items, check_registry
from tests.helpers import ROOT

NOW = dt.datetime(2026, 9, 21, 10, 45, tzinfo=dt.timezone.utc)
REG = load(ROOT / "registry.json")
VO_ENTRY = copy.deepcopy(next(s for s in REG["sources"] if s["id"] == "gdacs-volcano"))
DR_ENTRY = copy.deepcopy(next(s for s in REG["sources"] if s["id"] == "gdacs-drought"))
VO_FEATURE = json.loads((ROOT / "tests/fixtures/gdacs/real_2026-09-21_vo_event.json").read_text())
DR_FEATURE = json.loads((ROOT / "tests/fixtures/gdacs/real_2026-09-21_dr_centroid.json").read_text())


def collection(*features):
    return json.dumps({"type": "FeatureCollection", "features": list(features)}).encode()


class VolcanoFeed(unittest.TestCase):
    def test_authentic_fuego_event_normalizes(self):
        result = gdacs_vo_dr.parse_volcano(collection(VO_FEATURE), NOW, VO_ENTRY)
        self.assertFalse(result.complete)
        self.assertEqual(result.items_in_window, 1)
        item = result.items[0]
        self.assertEqual(item["id"], "gdacs-volcano:1000145")
        self.assertEqual(item["source"], "gdacs-volcano")
        self.assertEqual(item["title"], "Eruption  Fuego")
        self.assertEqual(item["occurred_at"], "2026-08-05T08:09:00Z")
        self.assertEqual(item["source_updated_at"], "2026-09-21T10:40:56Z")
        self.assertEqual(item["level"]["value"], "Green")
        self.assertEqual(item["location"]["countries"], ["GT"])
        self.assertEqual((item["location"]["lat"], item["location"]["lon"]), (14.473, -90.88))
        self.assertEqual(item["metrics"]["hazard_type"], "volcano")
        self.assertEqual(item["metrics"]["event_name"], "Fuego")
        self.assertEqual(item["source_status_raw"], "false")
        self.assertEqual(check_items([item], REG, NOW), [])

    def test_empty_current_volcano_feed_is_valid_not_an_all_clear(self):
        result = gdacs_vo_dr.parse_volcano(collection(), NOW, VO_ENTRY)
        self.assertFalse(result.complete)
        self.assertEqual(result.items_in_window, 0)
        self.assertEqual(result.items, [])


class DroughtFeed(unittest.TestCase):
    def test_authentic_central_sahel_centroid_normalizes_string_fields(self):
        result = gdacs_vo_dr.parse_drought(collection(DR_FEATURE), NOW, DR_ENTRY)
        self.assertFalse(result.complete)
        item = result.items[0]
        self.assertEqual(item["id"], "gdacs-drought:1027567")
        self.assertEqual(item["source"], "gdacs-drought")
        self.assertEqual(item["occurred_at"], "2026-06-21T00:00:00Z")
        self.assertIsNone(item["source_updated_at"])
        self.assertEqual(item["level"]["value"], "Green")
        self.assertEqual(item["metrics"]["episode_id"], 1)
        self.assertEqual(item["metrics"]["alert_score"], 0.25)
        self.assertEqual(item["metrics"]["severity"], 168576)
        self.assertEqual(item["metrics"]["hazard_type"], "drought")
        self.assertEqual(item["location"]["countries"], [])
        self.assertEqual((item["location"]["lat"], item["location"]["lon"]), (9.924, 15.933))
        self.assertEqual(check_items([item], REG, NOW), [])

    def test_polygon_copy_is_ignored_not_published_as_second_event(self):
        polygon = copy.deepcopy(DR_FEATURE)
        polygon["id"] = "DR10275671Area"
        polygon["geometry"] = {"type": "MultiPolygon", "coordinates": []}
        polygon["properties"]["Class"] = "Poly_area"
        polygon["properties"]["polygonlabel"] = "Affected Area"
        result = gdacs_vo_dr.parse_drought(collection(DR_FEATURE, polygon), NOW, DR_ENTRY)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0]["id"], "gdacs-drought:1027567")


class Contract(unittest.TestCase):
    def test_registry_releases_both_sources_with_adapters(self):
        self.assertEqual(check_registry(REG, ADAPTERS), [])
        self.assertTrue(VO_ENTRY["public"])
        self.assertTrue(DR_ENTRY["public"])
        self.assertIsNone(VO_ENTRY["max_empty_h"])
        self.assertEqual(DR_ENTRY["max_empty_h"], 72)
        self.assertTrue(VO_ENTRY["endpoints"][0].endswith("gdacsVO.geojson"))
        self.assertTrue(DR_ENTRY["endpoints"][0].endswith("gdacsDR.geojson"))

    def test_wrong_type_and_wrong_report_target_fail_closed(self):
        wrong = copy.deepcopy(VO_FEATURE)
        wrong["properties"]["eventtype"] = "DR"
        self.assertEqual(gdacs_vo_dr.parse_volcano(collection(wrong), NOW, VO_ENTRY).items, [])

        bad = copy.deepcopy(VO_FEATURE)
        bad["properties"]["url"]["report"] = (
            "https://www.gdacs.org/report.aspx?eventid=99&episodeid=1&eventtype=VO"
        )
        with self.assertRaises(AdapterError) as cm:
            gdacs_vo_dr.parse_volcano(collection(bad), NOW, VO_ENTRY)
        self.assertEqual(cm.exception.kind, "sanity")


if __name__ == "__main__":
    unittest.main()
