"""Karten-Detailfenster: Marker bleiben zunächst auf ConflictWatch."""

import unittest
from pathlib import Path

from tests.helpers import ROOT


class MapDetailPanel(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        self.app = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
        self.map = (ROOT / "site" / "map.js").read_text(encoding="utf-8")
        self.css = (ROOT / "site" / "style.css").read_text(encoding="utf-8")

    def test_page_has_local_detail_panel_with_explicit_source_link(self):
        self.assertIn('id="map-detail"', self.html)
        self.assertIn('id="map-detail-close"', self.html)
        self.assertIn('id="map-detail-source-link"', self.html)
        self.assertIn("Originalmeldung öffnen", self.html)

    def test_map_passes_selected_item_to_app_instead_of_external_navigation(self):
        self.assertIn('a.setAttribute("role", "button")', self.map)
        self.assertIn('Details auf ConflictWatch anzeigen.', self.map)
        self.assertIn("state.onSelect(it)", self.map)
        self.assertNotIn('a.setAttribute("href", url)', self.map)

    def test_app_populates_detail_and_only_then_exposes_original_url(self):
        self.assertIn("function showMapDetail(it, src, now)", self.app)
        self.assertIn('a.href = it.url;', self.app)
        self.assertIn('Originalmeldung bei " + src.name + " öffnen', self.app)
        self.assertIn("(it) => showMapDetail(it, srcById[it.source], now)", self.app)

    def test_mobile_panel_reflows_below_map_instead_of_covering_it(self):
        self.assertIn(".map-detail{", self.css)
        self.assertIn("@media(max-width:650px)", self.css)
        self.assertIn("position:static;width:auto;max-height:none", self.css)


if __name__ == "__main__":
    unittest.main()
