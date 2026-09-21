"""Map UI regression: sourced Equal-Earth land geometry, source coordinates only."""
import re
import unittest
from pathlib import Path
from tests.helpers import ROOT

SITE = ROOT / "site"

class EqualEarthDisplay(unittest.TestCase):
    def test_both_modes_have_real_equal_earth_asset_and_dynamic_markers(self):
        for name in ("index.html", "test.html"):
            page = (SITE / name).read_text(encoding="utf-8")
            with self.subTest(page=name):
                self.assertIn('id="map-view"', page)
                self.assertIn('id="map-points"', page)
                self.assertIn('href="world-equal-earth.svg"', page)
                self.assertIn('src="map.js?v=8"', page)
                self.assertNotIn('src="world.svg"', page)
                self.assertEqual(page.count('id="map-view"'), 1)
        svg = (SITE / "world-equal-earth.svg").read_text(encoding="utf-8")
        self.assertIn("Natural Earth", svg)
        self.assertIn("Equal Earth", svg)
        self.assertGreaterEqual(svg.count("<path "), 170)
        self.assertNotIn("Erdbebenpositionen", svg)  # basemap never contains fabricated events

    def test_no_visitor_geolocation_or_personal_distance(self):
        js = (SITE / "map.js").read_text(encoding="utf-8")
        self.assertIn("location.precision === \"point\"", js)
        # Regionale Zentroide bekommen eine eigene Abfrage und eine eigene Darstellung.
        # Beide Genauigkeiten stehen ausdruecklich im Quelltext, damit hier pruefbar
        # bleibt, dass eine ungefaehre Lage nie wie ein punktgenauer Ort gezeichnet wird.
        self.assertIn("location.precision === \"region\"", js)
        self.assertIn("map-event-region", js)
        self.assertIn("ungefähre Lage laut GDACS – keine Schadensfläche", js)
        self.assertIn("it.location.lon, it.location.lat", js)
        self.assertIn("window.ConflictWatchMap", js)
        self.assertNotIn("navigator.geolocation.", js)
        self.assertNotIn("getCurrentPosition(", js)
        self.assertNotIn("watchPosition(", js)
        self.assertNotIn("navigator.permissions", js)
        app = (SITE / "app.js").read_text(encoding="utf-8")
        self.assertIn("window.ConflictWatchMap.render(items, snap.sources,", app)
        self.assertIn("(it) => showMapDetail(it, srcById[it.source], now)", app)

    def test_both_page_builds_copy_mapping_assets(self):
        yml = (ROOT / ".github" / "workflows" / "pipeline.yml").read_text(encoding="utf-8")
        # Seit der Freigabe aller Quellen gibt es nur noch die regulaere Seite.
        self.assertEqual(yml.count("site/world-equal-earth.svg"), 1)
        self.assertEqual(yml.count("site/map.js"), 1)
        self.assertNotIn("_site/test/", yml)
        reg = (ROOT / "registry.json").read_text(encoding="utf-8")
        self.assertIn('"public": true', reg)
        self.assertNotIn('"public": false', reg)

if __name__ == "__main__":
    unittest.main()
