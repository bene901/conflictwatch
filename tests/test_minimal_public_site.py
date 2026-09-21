"""Public UI stays compact without suppressing source transparency or outage notices."""
import unittest

from tests.helpers import ROOT


class MinimalPublicSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "site/index.html").read_text(encoding="utf-8")
        cls.app = (ROOT / "site/app.js").read_text(encoding="utf-8")
        cls.map = (ROOT / "site/map.js").read_text(encoding="utf-8")

    def test_method_and_map_legend_are_optional(self):
        self.assertIn('<details class="sources-disclosure">', self.html)
        self.assertIn('<details class="map-help">', self.html)
        self.assertIn('id="sources"', self.html)
        self.assertIn('id="map-legend"', self.html)
        self.assertNotIn("Kartenprojektion:", self.html)
        self.assertNotIn("FLÄCHENTREUE DARSTELLUNG", self.html)

    def test_safety_status_and_original_link_remain(self):
        self.assertIn('id="banner"', self.html)
        self.assertIn('id="data-state"', self.html)
        self.assertIn('id="map-detail-source-link"', self.html)
        self.assertIn("Datenstand älter als 3 Stunden", self.app)
        self.assertIn("Abruf ausgefallen", self.app)
        self.assertIn("s.coverage_note", self.app)
        self.assertIn("s.attribution", self.app)
        self.assertIn("setHttpsSourceLink(a, it.url", self.app)

    def test_core_map_and_filters_stay(self):
        self.assertIn("const MAX_ZOOM = 64", self.map)
        self.assertIn('["volcano", "Vulkane"]', self.map)
        self.assertIn('["drought", "Dürren"]', self.map)
        self.assertIn("shownQuakes + \"/\" + allQuakes", self.map)
        self.assertIn("shownRegions + \"/\" + allRegions", self.map)
        self.assertIn("keine Entwarnung", self.map)


if __name__ == "__main__":
    unittest.main()
