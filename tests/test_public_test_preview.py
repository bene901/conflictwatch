"""Public test view must never change the regular release gate."""
import copy
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from cw import pipeline, snapshot, state
from cw.test_preview import TEST_SOURCE_IDS, build_test_snapshot, main as preview_main
from tests.helpers import ROOT, full_registry, raw, real_doc
from tests.test_noaa_integration import CAPTURED_AT, fixture_fetcher

class PublicTestPreview(unittest.TestCase):
    def setUp(self):
        self.reg = full_registry()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state_dir = Path(self.tmp.name) / "state"
        result = pipeline.run(self.reg, self.state_dir, now=CAPTURED_AT,
                              fetcher=fixture_fetcher, log=lambda *_: None)
        self.assertEqual(result, 0)
        self.items, self.sources = state.load(self.state_dir)

    def test_real_source_data_visible_in_test_only(self):
        public = snapshot.build(self.items, self.sources, self.reg, "abc1234",
                                "2026-09-20T13:30:00Z")
        trial = build_test_snapshot(self.items, self.sources, self.reg, "abc1234", CAPTURED_AT)
        self.assertEqual(public["sources"], [])
        self.assertEqual(public["items"], [])
        self.assertEqual({s["id"] for s in trial["sources"]}, TEST_SOURCE_IDS)
        self.assertEqual({it["source"] for it in trial["items"]}, TEST_SOURCE_IDS)
        self.assertEqual(len(trial["items"]), 4)
        self.assertEqual(len([it for it in trial["items"] if it["kind"] == "event"]), 1)
        self.assertEqual(len([it for it in trial["items"] if it["kind"] == "status"]), 3)
        self.assertTrue(all(not s["public"] for s in self.reg["sources"]))

    def test_unknown_future_source_not_published_by_test_snapshot(self):
        reg = copy.deepcopy(self.reg)
        extra = copy.deepcopy(reg["sources"][0])
        extra["id"] = "future-private-provider"
        extra["public"] = False
        reg["sources"].append(extra)
        # This extra source is registered but not part of the explicitly approved preview.
        trial = build_test_snapshot(self.items, self.sources, reg, "abc1234", CAPTURED_AT)
        self.assertEqual({s["id"] for s in trial["sources"]}, TEST_SOURCE_IDS)
        self.assertNotIn("future-private-provider", str(trial))

    def test_released_source_disables_test_mode_until_separately_reviewed(self):
        reg = copy.deepcopy(self.reg)
        next(s for s in reg["sources"] if s["id"] == "usgs")["public"] = True
        with self.assertRaisesRegex(ValueError, "Testansicht deaktivieren"):
            build_test_snapshot(self.items, self.sources, reg, "abc1234", CAPTURED_AT)

    def test_test_html_disclosure_and_disjoint_page_data(self):
        html = (ROOT / "site" / "test.html").read_text(encoding="utf-8")
        js = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
        prod = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        wf = (ROOT / ".github" / "workflows" / "pipeline.yml").read_text(encoding="utf-8")
        self.assertIn('data-mode="test"', html)
        self.assertIn("NICHT FREIGEGEBENE DATENQUELLEN", html)
        self.assertIn("keine vollständige Gefahrenübersicht", html)
        self.assertIn('href="test/"', prod)
        self.assertIn("ungültiger Test-Datensatz oder unbekannte Quelle", js)
        self.assertIn("--out _site/data/snapshot.json", wf)
        self.assertIn("--out _site/test/data/snapshot.json", wf)
        self.assertIn("python -m cw.test_preview", wf)
        self.assertNotIn("cp site/* _site/", wf)
        self.assertNotIn("_site/data/snapshot.json --include-unreleased", wf)

    def test_test_preview_cli_writes_valid_data_without_changing_public_flag(self):
        from unittest import mock
        out = Path(self.tmp.name) / "test" / "data" / "snapshot.json"
        with mock.patch("cw.test_preview.now_utc", return_value=CAPTURED_AT):
            code = preview_main(["--state", str(self.state_dir), "--revision", "abc1234",
                                 "--out", str(out)])
        self.assertEqual(code, 0)
        self.assertTrue(out.is_file())
        self.assertEqual({s["id"] for s in __import__("json").loads(out.read_text())["sources"]},
                         TEST_SOURCE_IDS)
        self.assertTrue(all(not s["public"] for s in self.reg["sources"]))

if __name__ == "__main__":
    unittest.main()
