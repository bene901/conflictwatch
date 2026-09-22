"""Die frueher separate oeffentliche Testansicht ist stillgelegt.

Sie existierte ausschliesslich, um NICHT freigegebene Quellen zu zeigen. Seit alle
Quellen in registry.json auf public:true stehen, gibt es nichts mehr gesondert
vorzuschauen: die Seite wird nicht mehr gebaut und der regulaere Feed zeigt alles.

Die Schutzregeln der Testansicht bleiben geprueft, weil sie wieder gebraucht werden,
sobald eine kuenftige Quelle erneut gesperrt startet.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from cw import pipeline, snapshot, state
from cw.test_preview import TEST_SOURCE_IDS, build_test_snapshot, main as preview_main
from tests.helpers import ROOT, full_registry
from tests.test_noaa_integration import CAPTURED_AT, fixture_fetcher


def blocked_registry():
    """Alle Quellen ausdruecklich gesperrt - der Zustand, fuer den die Testansicht gebaut war."""
    reg = full_registry()
    for src in reg["sources"]:
        src["public"] = False
    return reg


class RetiredTestPreview(unittest.TestCase):
    def setUp(self):
        self.reg = full_registry()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_dir = Path(self.tmp.name) / "state"
        self.assertEqual(pipeline.run(self.reg, self.state_dir, now=CAPTURED_AT,
                                      fetcher=fixture_fetcher, log=lambda *_: None), 0)
        self.items, self.sources = state.load(self.state_dir)

    def test_all_sources_are_released_and_visible_in_the_regular_feed(self):
        self.assertTrue(all(src["public"] is True for src in self.reg["sources"]))
        public = snapshot.build(self.items, self.sources, self.reg, "abc1234",
                                "2026-09-20T13:30:00Z")
        self.assertEqual({s["id"] for s in public["sources"]},
                         {"usgs", "noaa-swpc", "gdacs", "gdacs-volcano", "gdacs-drought",
                          "ucdp-candidate", "gdelt"})
        self.assertEqual(len(public["items"]), 6)

    def test_cli_skips_cleanly_instead_of_breaking_the_pipeline(self):
        """Frueher ein harter Fehler (Code 2). Ein stillgelegter Schritt darf den
        Lauf nicht abbrechen - sonst deployt nichts mehr."""
        out = Path(self.tmp.name) / "test" / "data" / "snapshot.json"
        code = preview_main(["--state", str(self.state_dir), "--revision", "abc1234",
                             "--out", str(out)])
        self.assertEqual(code, 0)
        self.assertFalse(out.exists())  # es wird nichts Gesondertes veroeffentlicht

    def test_released_source_still_disables_the_separate_preview(self):
        """Kernschutz: eine regulaer freigegebene Quelle darf nicht zusaetzlich in
        einer als 'nicht freigegeben' beschrifteten Ansicht auftauchen."""
        reg = blocked_registry()
        next(s for s in reg["sources"] if s["id"] == "usgs")["public"] = True
        with self.assertRaisesRegex(ValueError, "Testansicht deaktivieren"):
            build_test_snapshot(self.items, self.sources, reg, "abc1234", CAPTURED_AT)

    def test_unapproved_source_would_still_never_enter_the_preview(self):
        """Gilt weiterhin fuer den Fall, dass eine kuenftige Quelle gesperrt startet."""
        reg = blocked_registry()
        extra = copy.deepcopy(reg["sources"][0])
        extra["id"] = "future-private-provider"
        extra["public"] = False
        reg["sources"].append(extra)
        trial = build_test_snapshot(self.items, self.sources, reg, "abc1234", CAPTURED_AT)
        self.assertEqual({s["id"] for s in trial["sources"]}, TEST_SOURCE_IDS)
        self.assertNotIn("future-private-provider", str(trial))
        self.assertNotIn("gdacs", {it["source"] for it in trial["items"]})

    def test_site_and_pipeline_no_longer_offer_the_separate_view(self):
        prod = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        wf = (ROOT / ".github" / "workflows" / "pipeline.yml").read_text(encoding="utf-8")
        self.assertNotIn('href="test/"', prod)
        self.assertNotIn("python -m cw.test_preview", wf)
        self.assertNotIn("_site/test/", wf)
        self.assertIn("--out _site/data/snapshot.json", wf)
        # Der interne Vorschau-Snapshot bleibt ein Artefakt und wird nie veroeffentlicht.
        self.assertNotIn("_site/data/snapshot.json --include-unreleased", wf)

    def test_the_retired_page_keeps_its_disclosure_while_it_exists(self):
        """Die Datei liegt noch im Repo. Solange sie das tut, muss ihre Kennzeichnung
        stehen - sonst waere sie beim Wiedereinschalten stillschweigend falsch."""
        html = (ROOT / "site" / "test.html").read_text(encoding="utf-8")
        self.assertIn('data-mode="test"', html)
        self.assertIn("NICHT FREIGEGEBENE DATENQUELLEN", html)
        self.assertIn("keine vollständige Gefahrenübersicht", html)
        js = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
        self.assertIn("ungültiger Test-Datensatz oder unbekannte Quelle", js)


if __name__ == "__main__":
    unittest.main()
