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

    def test_registry_uses_the_official_magnitude_45_feed(self):
        self.assertEqual(self.entry["endpoints"], [
            "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson"
        ])
        # Die Schwelle stammt von USGS, nicht von ConflictWatch. Unterhalb M4.5 ist die
        # weltweite Erfassung ungleichmaessig; eine Karte ohne Schwelle zeigt vor allem
        # die Dichte des US-Messnetzes. Am 20.09.2026: 152 von 161 Beben unter M2.5 in
        # den USA, aber nur 2 von 15 Beben ab M4.5.
        self.assertIn("ab Magnitude 4,5", self.entry["coverage_note"])
        self.assertIn("keine Entwarnung", self.entry["coverage_note"])
        self.assertEqual(self.entry["retention_days"], 7)
        self.assertTrue(self.entry["public"])  # seit 20.09.2026 regulaer freigegeben
        self.assertEqual(self.entry["highlight"]["window_h"], 24)
        # Zeitpunkt-Quelle: die Aktualitaet zaehlt ab dem Bebenzeitpunkt, nicht ab der
        # letzten Sichtung - anders als bei GDACS-Ereignissen mit Dauer.
        self.assertEqual(self.entry["highlight"]["recency_basis"], "display_time")

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

    def test_explicit_publish_refresh_fetches_even_if_interval_not_due(self):
        from pathlib import Path
        import tempfile
        from cw import pipeline
        from tests.helpers import registry as isolated_registry, raw

        requests = []
        def fake_fetch(url):
            requests.append(url)
            return raw(real_doc())

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            reg = isolated_registry()
            self.assertEqual(pipeline.run(reg, folder, now=NOW,
                                          fetcher=fake_fetch, log=lambda *_: None), 0)
            self.assertEqual(pipeline.run(reg, folder, now=NOW + dt.timedelta(minutes=5),
                                          fetcher=fake_fetch, log=lambda *_: None), 0)
            self.assertEqual(len(requests), 1)  # Stündlicher Normallauf bleibt gedrosselt.
            self.assertEqual(pipeline.run(reg, folder, now=NOW + dt.timedelta(minutes=10),
                                          force_fetch=True, fetcher=fake_fetch,
                                          log=lambda *_: None), 0)
            self.assertEqual(len(requests), 2)
            self.assertTrue(all(url.endswith("/4.5_day.geojson") for url in requests))


if __name__ == "__main__":
    unittest.main()
