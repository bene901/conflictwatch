"""GDACS: unchanged TC feature from the official feed, plus labeled mutations."""
import copy
import datetime as dt
import json
import unittest

from cw.adapters import gdacs
from cw.errors import AdapterError
from cw.merge import blank_source_state, merge_items, succeed_source_state
from cw.registry import load
from cw.validate import check_items, check_registry
from tests.helpers import ROOT

NOW = dt.datetime(2026, 9, 20, 12, 0, tzinfo=dt.timezone.utc)
REG = load(ROOT / "registry.json")
ENTRY = copy.deepcopy(REG["sources"][0])
ENTRY.update(id="gdacs", name="GDACS", public=False,
             endpoints=["https://www.gdacs.org/contentdata/xml/gdacs_app_feed.json"],
             terms_url="https://www.gdacs.org/About/termofuse.aspx",
             attribution="Daten: Global Disaster Alert and Coordination System (GDACS)",
             id_rule="gdacs:<eventtype>:<eventid>, Episoden sind Updates eines Ereignisses",
             completeness_rule="Immer complete=false, da GDACS keine Vollständigkeit garantiert",
             coverage_note="TC, FL, VO, DR, WF; keine EQ/TS; Zentroid ist keine Schadensfläche",
             level_schemes=[{"id": "gdacs-alert", "ordered_values": ["Green", "Orange", "Red"],
                             "labels": {"Green": "GDACS Grün", "Orange": "GDACS Orange", "Red": "GDACS Rot"},
                             "reference_url": "https://www.gdacs.org/"}])
REG["sources"].append(ENTRY)
FIXTURE = ROOT / "tests/fixtures/gdacs/real_2026-09-20_tc_excerpt.json"


def doc():
    return json.loads(FIXTURE.read_text())


def parse(d):
    return gdacs.parse(json.dumps(d).encode(), NOW, ENTRY)


class GdacsAdapter(unittest.TestCase):
    def test_three_unmodified_live_hazard_features(self):
        expected = {"tc": ("gdacs:TC:1001324", "tropical_cyclone"),
                    "fl": ("gdacs:FL:1104175", "flood"),
                    "wf": ("gdacs:WF:1032256", "wildfire")}
        for code, (ident, hazard) in expected.items():
            with self.subTest(code=code):
                fixture = ROOT / f"tests/fixtures/gdacs/real_2026-09-20_{code}_excerpt.json"
                result = parse(json.loads(fixture.read_text()))
                self.assertEqual(result.items[0]["id"], ident)
                self.assertEqual(result.items[0]["metrics"]["hazard_type"], hazard)
                self.assertEqual(result.items[0]["level"]["value"], "Green")
                self.assertFalse(result.complete)

    def test_real_feature_retains_gdacs_fields_and_validates(self):
        result = parse(doc())
        self.assertFalse(result.complete)  # a curated excerpt is not a complete feed
        self.assertEqual(result.items_in_window, 1)
        item = result.items[0]
        self.assertEqual(item["id"], "gdacs:TC:1001324")
        self.assertEqual(item["title"], "Tropical Cyclone ODALYS-26")
        self.assertEqual(item["occurred_at"], "2026-09-20T09:00:00Z")
        self.assertEqual(item["source_updated_at"], "2026-09-20T10:50:05Z")
        self.assertEqual(item["level"], {"scheme": "gdacs-alert", "value": "Green", "label": "GDACS Grün"})
        self.assertEqual(item["metrics"], {"hazard_type": "tropical_cyclone", "episode_id": 1,
                                           "severity": 129.6288, "severity_unit": "km/h", "alert_score": 1})
        self.assertEqual(item["location"]["precision"], "region")
        self.assertEqual((item["location"]["lat"], item["location"]["lon"]), (11.4, -124.5))
        self.assertIsNone(item["ongoing"])  # iscurrent is not a proven ongoing flag
        self.assertEqual(item["data_status"], "unknown")  # no GDACS review-status inference
        self.assertEqual(check_registry(REG, {"usgs": object(), "gdacs": gdacs.parse}), [])
        merged = merge_items({}, "gdacs", ENTRY, result, "2026-09-20T12:00:00Z")
        self.assertEqual(check_items(list(merged.values()), REG, NOW), [])

    def test_five_hazards_only_and_stable_identity_across_episodes(self):
        for hazard, label in gdacs.TYPES.items():
            with self.subTest(hazard=hazard):
                d = doc()
                p = d["features"][0]["properties"]
                p["eventtype"] = hazard
                p["url"]["report"] = p["url"]["report"].replace("eventtype=TC", f"eventtype={hazard}")
                p["episodeid"] = 5
                it = parse(d).items[0]
                self.assertEqual(it["id"], f"gdacs:{hazard}:1001324")
                self.assertEqual(it["metrics"]["hazard_type"], label)
                self.assertEqual(it["metrics"]["episode_id"], 5)
        d = doc()
        d["features"][0]["properties"]["eventtype"] = "EQ"
        self.assertEqual(parse(d).items, [])

    def test_empty_is_not_complete_and_does_not_withdraw_older_items(self):
        old = merge_items({}, "gdacs", ENTRY, parse(doc()), "2026-09-20T12:00:00Z")
        empty = parse({"type": "FeatureCollection", "features": []})
        self.assertFalse(empty.complete)
        self.assertEqual(empty.items_in_window, 0)
        retained = merge_items(old, "gdacs", ENTRY, empty, "2026-11-20T12:00:00Z")
        self.assertEqual(set(retained), set(old))
        state = succeed_source_state(blank_source_state("gdacs", "1.0.0"), ENTRY, empty, retained,
                                     "2026-09-20T12:00:00Z", "1.0.0")
        self.assertNotEqual(state["data_state"], "empty")

    def test_invalid_input_fails_as_a_whole_without_partial_success(self):
        for raw in (b"<html>error</html>", b'{"type":"FeatureCollection","features":[', b"null"):
            with self.subTest(raw=raw[:20]), self.assertRaises(AdapterError):
                gdacs.parse(raw, NOW, ENTRY)
        with self.assertRaises(AdapterError) as cm:
            parse({"type": "FeatureCollection", "features": [doc()["features"][0], doc()["features"][0]]})
        self.assertEqual(cm.exception.kind, "sanity")
        with self.assertRaises(AdapterError):
            parse({"type": "FeatureCollection", "features": [doc()["features"][0], None]})

    def test_unknown_level_time_country_and_report_target_fail(self):
        cases = (
            (lambda p: p.update(alertlevel="Yellow"), "schema"),
            (lambda p: p.update(fromdate="tomorrow"), "schema"),
            (lambda p: p.update(datemodified="2026-09-21T15:00:00"), "sanity"),
            (lambda p: p.update(affectedcountries=[{"iso2": "USA"}]), "schema"),
            (lambda p: p["url"].update(report="https://www.gdacs.org/report.aspx?eventid=99&eventtype=TC"), "sanity"),
        )
        for mutate, kind in cases:
            d = doc()
            mutate(d["features"][0]["properties"])
            with self.subTest(kind=kind), self.assertRaises(AdapterError) as cm:
                parse(d)
            self.assertEqual(cm.exception.kind, kind)

    def test_future_todate_is_forecast_not_future_event(self):
        d = doc()
        d["features"][0]["properties"]["todate"] = "2026-09-25T09:00:00"
        self.assertEqual(len(parse(d).items), 1)


if __name__ == "__main__":
    unittest.main()
