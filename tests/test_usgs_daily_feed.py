"""USGS wide daily feed contract: no significant-only filter and no non-quake markers."""
import copy
import datetime as dt
import json
import unittest

from cw.adapters import usgs
from cw.errors import AdapterError
from tests.helpers import full_registry, real_doc

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


class WiderUSGSDailyFeed(unittest.TestCase):
    def setUp(self):
        self.entry = next(s for s in full_registry()["sources"] if s["id"] == "usgs")

    def test_registry_uses_official_all_day_feed_not_significant_only(self):
        self.assertEqual(self.entry["endpoints"], [
            "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
        ])
        self.assertFalse(self.entry["public"])
        self.assertEqual(self.entry["highlight"]["window_h"], 24)

    def test_daily_feed_parses_many_unique_small_and_large_earthquakes(self):
        doc = real_doc()
        base = doc["features"][0]
        generated = []
        for i in range(100):
            f = copy.deepcopy(base)
            ident = f"sample-day-{i}"
            f["id"] = ident
            f["properties"]["ids"] = f",{ident},"
            f["properties"]["url"] = "https://earthquake.usgs.gov/earthquakes/eventpage/" + ident
            f["properties"]["type"] = "earthquake"
            f["properties"]["mag"] = 0.6 + 0.06 * i
            f["properties"]["alert"] = None  # most small quakes have no PAGER alert
            f["geometry"]["coordinates"][0] = -120 + i * 0.2
            generated.append(f)
        doc["features"] = generated
        doc["metadata"]["count"] = len(generated)
        parsed = usgs.parse(json.dumps(doc).encode(), NOW, self.entry)
        self.assertTrue(parsed.complete)
        self.assertEqual(parsed.items_in_window, 100)
        self.assertEqual(len({it["id"] for it in parsed.items}), 100)
        self.assertTrue(any(it["metrics"]["magnitude"] < 2.5 for it in parsed.items))
        self.assertTrue(any(it["metrics"]["magnitude"] >= 4.5 for it in parsed.items))
        self.assertTrue(all(it["location"]["precision"] == "point" for it in parsed.items))

    def test_non_earthquake_feature_is_not_shown_as_an_earthquake(self):
        doc = real_doc()
        quarry = copy.deepcopy(doc["features"][0])
        quarry["id"] = "quarry-test"
        quarry["properties"]["type"] = "quarry blast"
        doc["features"].append(quarry)
        doc["metadata"]["count"] = 2
        parsed = usgs.parse(json.dumps(doc).encode(), NOW, self.entry)
        self.assertEqual(len(parsed.items), 1)
        self.assertEqual(parsed.items[0]["id"], "usgs:" + doc["features"][0]["id"])
        self.assertEqual(parsed.items_in_window, 1)
        doc["metadata"]["count"] = 1
        with self.assertRaises(AdapterError):
            usgs.parse(json.dumps(doc).encode(), NOW, self.entry)


if __name__ == "__main__":
    unittest.main()
