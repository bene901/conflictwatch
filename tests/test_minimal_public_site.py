"""Public UI stays compact while operational warnings and source links remain."""
import unittest

from tests.helpers import ROOT


class MinimalPublicSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "site/index.html").read_text(encoding="utf-8")
        cls.app = (ROOT / "site/app.js").read_text(encoding="utf-8")
        cls.map = (ROOT / "site/map.js").read_text(encoding="utf-8")

    def test_default_page_has_no_projection_or_method_boilerplate(self):
        self.assertIn('<details class="sources-disclosure">', self.html)
        self.assertIn('<details class="map-help">', self.html)
        self.assertNotIn("Kartenprojektion:", self.html)
        self.assertNotIn("FLÄCHENTREUE DARSTELLUNG", self.html)
        self.assertNotIn("Equal Earth", self.html)
        self.assertNotIn("Quellen &amp; Methode", self.html)
        self.assertNotIn('class="method"', self.html)
        self.assertNotIn("PUBLIC DATA MONITOR", self.html)

    def test_conflict_topic_states_do_not_call_monthly_ucdp_live(self):
        self.assertIn('card.dataset.source === "ucdp-candidate"', self.app)
        self.assertIn('label.textContent = "Monatsbestand"', self.app)
        self.assertIn('card.dataset.source === "gdelt"', self.app)
        self.assertIn('label.textContent = "Aktuell · ungeprüft"', self.app)

    def test_public_dashboard_loads_local_design_layer_and_keeps_core_controls(self):
        self.assertIn('href="public.css?v=1"', self.html)
        self.assertIn('class="hero-eyebrow"', self.html)
        self.assertIn('class="hero-meta"', self.html)
        self.assertIn('class="events-head"', self.html)
        self.assertIn('data-visual="ucdp"', self.html)
        self.assertIn('data-visual="gdelt"', self.html)
        self.assertIn('map-filter-primary', self.map)
        self.assertIn('map-filter-chip', self.map)
        self.assertIn('map-zoom-controls', self.map)
        self.assertIn('li.dataset.source = it.source || "";', self.app)

    def test_sources_and_topic_states_are_compact(self):
        self.assertIn("<summary>Datenquellen</summary>", self.html)
        self.assertIn('id="sources"', self.html)
        self.assertNotIn("Abdeckung & Herkunft", self.app)
        self.assertNotIn("s.coverage_note", self.app)
        self.assertIn('"source-health"', self.app)
        self.assertIn('if (TEST_MODE) label.textContent = "Test";', self.app)
        self.assertIn('else label.textContent = "Live";', self.app)

    def test_operational_warnings_and_original_links_remain(self):
        self.assertIn('id="banner"', self.html)
        self.assertIn('id="data-state"', self.html)
        self.assertIn('id="map-detail-source-link"', self.html)
        self.assertIn("Datenstand älter als 3 Stunden", self.app)
        self.assertIn("Abruf ausgefallen", self.app)
        self.assertIn("Abruf gestört. Zuletzt gespeicherte Meldungen können veraltet sein", self.app)
        self.assertIn("setHttpsSourceLink(a, it.url", self.app)

    def test_core_map_and_filters_stay(self):
        self.assertIn("const MAX_ZOOM = 64", self.map)
        self.assertIn('["volcano", "Vulkane"]', self.map)
        self.assertIn('["drought", "Dürren"]', self.map)
        self.assertIn('shownQuakes + "/" + allQuakes', self.map)
        self.assertIn('shownRegions + "/" + allRegions', self.map)


if __name__ == "__main__":
    unittest.main()
