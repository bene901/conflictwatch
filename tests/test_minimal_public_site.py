"""Public UI stays compact while operational warnings and source links remain."""
import unittest

from tests.helpers import ROOT


class MinimalPublicSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "site/index.html").read_text(encoding="utf-8")
        cls.app = (ROOT / "site/app.js").read_text(encoding="utf-8")
        cls.map = (ROOT / "site/map.js").read_text(encoding="utf-8")

    def test_default_page_has_no_explanatory_projection_or_method_copy(self):
        self.assertIn('<details class="sources-disclosure">', self.html)
        self.assertIn('<details class="map-help">', self.html)
        self.assertNotIn("Kartenprojektion:", self.html)
        self.assertNotIn("FLÄCHENTREUE DARSTELLUNG", self.html)
        self.assertNotIn("Equal Earth", self.html)
        self.assertNotIn("Quellen &amp; Methode", self.html)
        self.assertNotIn('class="method"', self.html)
        self.assertNotIn("PUBLIC DATA MONITOR", self.html)

    def test_sources_are_collapsed_and_compact(self):
        self.assertIn("<summary>Datenquellen</summary>", self.html)
        self.assertIn('id="sources"', self.html)
        self.assertNotIn("Abdeckung & Herkunft", self.app)
        self.assertNotIn("s.coverage_note", self.app)
        self.assertIn('"source-health"', self.app)
        self.assertIn('label.textContent = TEST_MODE ? "Test" : "Live";', self.app)

    def test_safety_status_and_original_link_remain(self):
        self.assertIn('id="banner"', self.html)
        self.assertIn('id="data-state"', self.html)
        self.assertIn('id="map-detail-source-link"', self.html)
        self.assertIn("Datenstand älter als 3 Stunden", self.app)
        self.assertIn("Abruf ausgefallen", self.app)
        self.assertIn("setHttpsSourceLink(a, it.url", self.app)

    def test_core_map_and_filters_stay(self):
        self.assertIn("const MAX_ZOOM = 64", self.map)
        self.assertIn('["volcano", "Vulkane"]', self.map)
        self.assertIn('["drought", "Dürren"]', self.map)
        self.assertIn("shownQuakes + "/" + allQuakes", self.map)
        self.assertIn("shownRegions + "/" + allRegions", self.map)


if __name__ == "__main__":
    unittest.main()
