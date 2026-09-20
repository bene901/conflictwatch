import copy
import json
import unittest

from cw.adapters import usgs
from cw.errors import AdapterError
from cw.merge import (age_source_state, blank_source_state, fail_source_state, merge_items,
                      next_level_change, succeed_source_state)
from cw.timeutil import fmt
from cw.validate import check_items
from tests.helpers import (ROOT, NOW, add_second_event, at, derived, feature, raw, real_doc,
                           registry, usgs_entry)

E = usgs_entry()


def parse(doc, now=NOW):
    return usgs.parse(raw(doc) if not isinstance(doc, bytes) else doc, now, E)


def ingest(doc, items=None, when=NOW):
    res = parse(doc, when)
    return merge_items(items or {}, "usgs", E, res, fmt(when)), res


class T1RealResponse(unittest.TestCase):
    def test_real_response_matches_raw_values(self):
        res = parse(real_doc())
        self.assertTrue(res.complete)
        self.assertEqual(len(res.items), 1)
        it = res.items[0]
        self.assertEqual(it["id"], "usgs:us7000ti1p")
        self.assertEqual(it["occurred_at"], "2026-09-17T14:19:52Z")      # 1789654792210 ms
        self.assertEqual(it["source_updated_at"], "2026-09-18T14:29:54Z")  # 1789741794553 ms
        self.assertEqual(it["level"], {"scheme": "usgs-pager", "value": "green", "label": "PAGER Grün"})
        self.assertEqual(it["data_status"], "reviewed")
        self.assertEqual((it["location"]["lat"], it["location"]["lon"]), (52.8594, -171.3756))
        self.assertEqual(it["metrics"], {"magnitude": 6.5, "magnitude_type": "mww", "depth_km": 98})
        self.assertNotIn("tsunami", json.dumps(it))  # Regions-Flag, keine Warnung
        self.assertEqual(it["location"]["countries"], [])  # kein geratener Ländercode

    def test_golden(self):
        golden = json.loads((ROOT / "tests/fixtures/usgs/golden_real_item.json").read_text())
        self.assertEqual(parse(real_doc()).items[0], golden)

    def test_merged_state_passes_validator(self):
        items, _ = ingest(real_doc())
        self.assertEqual(check_items(list(items.values()), registry(), NOW), [])


class T2toT5BadResponses(unittest.TestCase):
    def assertKind(self, payload, kind):
        with self.assertRaises(AdapterError) as cm:
            parse(payload)
        self.assertEqual(cm.exception.kind, kind)

    def test_t2_empty_complete(self):
        doc = derived(lambda d: (d["features"].clear(), d["metadata"].update(count=0)))
        res = parse(doc)
        self.assertTrue(res.complete)
        self.assertEqual(res.items_in_window, 0)

    def test_t3_malformed_html_truncated(self):
        self.assertKind(b"{not json", "parse")
        self.assertKind(b"<html><body>Service Unavailable</body></html>", "parse")
        self.assertKind(raw(real_doc())[:200], "parse")

    def test_t4_drift(self):
        self.assertKind(derived(lambda d: feature(d)["properties"].pop("time")), "schema")
        self.assertKind(derived(lambda d: feature(d)["properties"].update(time="2026-09-17")), "schema")
        self.assertKind(derived(lambda d: d["metadata"].pop("count")), "schema")
        self.assertKind(derived(lambda d: feature(d)["properties"].update(status="final")), "schema")

    def test_t5_unknown_level_is_error_not_null(self):
        self.assertKind(derived(lambda d: feature(d)["properties"].update(alert="purple")), "schema")

    def test_null_alert_is_valid(self):
        res = parse(derived(lambda d: feature(d)["properties"].update(alert=None)))
        self.assertIsNone(res.items[0]["level"])

    def test_t12_future_time(self):
        fut = int((at(hours=3)).timestamp() * 1000)
        self.assertKind(derived(lambda d: feature(d)["properties"].update(time=fut, updated=fut)), "sanity")

    def test_t13_coordinates(self):
        self.assertKind(derived(lambda d: feature(d)["geometry"].update(coordinates=[200, 52, 10])), "sanity")
        self.assertKind(derived(lambda d: feature(d)["geometry"].update(type="Polygon")), "schema")


class MergeRules(unittest.TestCase):
    def test_t6_idempotent(self):
        a, _ = ingest(real_doc(), when=at())
        b, _ = ingest(real_doc(), a, when=at(hours=1))
        ia, ib = a["usgs:us7000ti1p"], b["usgs:us7000ti1p"]
        self.assertEqual(ib["ingest"]["last_changed_at"], ia["ingest"]["last_changed_at"])
        self.assertNotEqual(ib["ingest"]["last_seen_at"], ia["ingest"]["last_seen_at"])
        strip = lambda x: {k: v for k, v in x.items() if k != "ingest"}
        self.assertEqual(strip(ia), strip(ib))

    def test_t7_correction_same_id(self):
        a, _ = ingest(real_doc(), when=at())
        doc = derived(lambda d: feature(d)["properties"].update(mag=6.6, title="M 6.6 - 169 km W of Nikolski, Alaska"))
        b, _ = ingest(doc, a, when=at(hours=1))
        self.assertEqual(list(b), ["usgs:us7000ti1p"])
        self.assertEqual(b["usgs:us7000ti1p"]["ingest"]["last_changed_at"], fmt(at(hours=1)))
        self.assertEqual(b["usgs:us7000ti1p"]["ingest"]["first_seen_at"], fmt(at()))

    def test_t8_level_change_table(self):
        g = {"scheme": "usgs-pager", "value": "green", "label": "g"}
        y = {"scheme": "usgs-pager", "value": "yellow", "label": "y"}
        old = lambda lvl, lc=None: {"level": lvl, "level_change": lc, "ingest": {"last_seen_at": "2026-09-19T12:17:00Z"}}
        run = "2026-09-19T13:17:00Z"
        self.assertIsNone(next_level_change(old(None), y, run))            # null -> X
        self.assertIsNone(next_level_change(old(g), None, run))            # X -> null
        lc = next_level_change(old(g), y, run)                             # X -> Y
        self.assertEqual(lc["from"], g)
        self.assertEqual(lc["detected_between"], ["2026-09-19T12:17:00Z", run])
        self.assertIsNone(lc["source_changed_at"])
        self.assertEqual(next_level_change(old(y, lc), y, "2026-09-19T14:17:00Z"), lc)  # X -> X unverändert
        # Erstaufnahme mit Stufe: kein Wechsel
        items, _ = ingest(derived(lambda d: feature(d)["properties"].update(alert="red")))
        self.assertIsNone(items["usgs:us7000ti1p"]["level_change"])

    def test_level_change_through_pipeline_is_within_observations(self):
        a, _ = ingest(real_doc(), when=at())
        b, _ = ingest(derived(lambda d: feature(d)["properties"].update(alert="yellow")), a, when=at(hours=2))
        it = b["usgs:us7000ti1p"]
        self.assertEqual(it["level_change"]["detected_between"], [fmt(at()), fmt(at(hours=2))])
        self.assertEqual(check_items([it], registry(), at(hours=2)), [])

    def test_t9_incomplete_fetch_updates_but_never_deletes(self):
        """Adaptervertrag (paginierte Quellen): complete=False aktualisiert, löscht nie, setzt nie empty."""
        from cw.adapters.base import FetchResult
        a, _ = ingest(derived(lambda d: add_second_event(d)), when=at())
        first = parse(real_doc()).items
        res = FetchResult(items=first, complete=False, items_in_window=len(first))
        b = merge_items(a, "usgs", E, res, fmt(at(days=40)))
        self.assertIn("usgs:us7000zz99", b)  # trotz Alter: unvollständiger Abruf löscht nichts
        empty = FetchResult(items=[], complete=False, items_in_window=0)
        st = succeed_source_state(blank_source_state("usgs", "1.0.0"), E, empty, b, fmt(at()), "1.0.0")
        self.assertNotEqual(st["data_state"], "empty")

    def test_usgs_count_mismatch_is_sanity_error(self):
        for count in (2, 0):
            with self.assertRaises(AdapterError) as cm:
                parse(derived(lambda d, c=count: d["metadata"].update(count=c)))
            self.assertEqual(cm.exception.kind, "sanity")

    def test_t10_missing_in_complete_fetch_is_left_alone(self):
        a, _ = ingest(derived(lambda d: add_second_event(d)), when=at())
        b, _ = ingest(real_doc(), a, when=at(hours=1))
        self.assertEqual(b["usgs:us7000zz99"], a["usgs:us7000zz99"])

    def test_t11_explicit_withdrawal(self):
        items, _ = ingest(derived(lambda d: feature(d)["properties"].update(status="deleted")))
        self.assertEqual(items["usgs:us7000ti1p"]["data_status"], "withdrawn")

    def test_t16_retention(self):
        a, _ = ingest(derived(lambda d: add_second_event(d)), when=at())
        b, _ = ingest(real_doc(), a, when=at(days=31))  # zz99 fehlt im vollständigen Abruf und ist > 30 Tage alt
        self.assertNotIn("usgs:us7000zz99", b)
        self.assertIn("usgs:us7000ti1p", b)  # im Abruf enthalten -> bleibt

    def test_alias_keeps_first_identity(self):
        a, _ = ingest(real_doc(), when=at())

        def switch(d):
            f = feature(d)
            f["id"] = "ak2026slmipb"
            f["properties"]["url"] = "https://earthquake.usgs.gov/earthquakes/eventpage/ak2026slmipb"
            f["properties"]["ids"] = ",ak2026slmipb,us7000ti1p,"
        b, _ = ingest(derived(switch), a, when=at(hours=1))
        self.assertEqual(list(b), ["usgs:us7000ti1p"])
        self.assertTrue(b["usgs:us7000ti1p"]["url"].endswith("ak2026slmipb"))


class T17SourceStates(unittest.TestCase):
    def setUp(self):
        self.items, self.res = ingest(real_doc(), when=at())
        self.ok = succeed_source_state(blank_source_state("usgs", "1.0.0"), E, self.res, self.items, fmt(at()), "1.0.0")

    def test_success(self):
        self.assertEqual((self.ok["fetch_health"], self.ok["data_state"]), ("ok", "fresh"))
        self.assertEqual(self.ok["newest_source_time"], "2026-09-18T14:29:54Z")

    def test_failure_within_and_beyond_gap(self):
        s1 = fail_source_state(self.ok, E, self.items, fmt(at(hours=1)), "http", "HTTP 503")
        self.assertEqual(s1["fetch_health"], "degraded")
        s2 = fail_source_state(s1, E, self.items, fmt(at(hours=7)), "timeout", "x")
        self.assertEqual(s2["fetch_health"], "down")
        self.assertEqual(s2["consecutive_failures"], 2)

    def test_integrity_failed_fetch_never_looks_healthy(self):
        before = copy.deepcopy(self.items)
        s = fail_source_state(self.ok, E, self.items, fmt(at(hours=1)), "parse", "kaputt")
        self.assertEqual(self.items, before)                      # Bestand unberührt
        self.assertNotEqual(s["fetch_health"], "ok")              # kein störungsfreier Zustand
        self.assertEqual(s["last_success_at"], self.ok["last_success_at"])
        self.assertEqual(s["newest_source_time"], self.ok["newest_source_time"])
        self.assertEqual(s["data_state"], self.ok["data_state"])  # nicht auf fresh/empty gesetzt

    def test_empty_then_suspicious(self):
        entry = dict(E, max_empty_h=24)
        empty = type(self.res)(items=[], complete=True, items_in_window=0)
        s1 = succeed_source_state(self.ok, entry, empty, self.items, fmt(at(hours=1)), "1.0.0")
        self.assertEqual((s1["fetch_health"], s1["data_state"]), ("ok", "empty"))
        s2 = succeed_source_state(s1, entry, empty, self.items, fmt(at(hours=30)), "1.0.0")
        self.assertEqual(s2["fetch_health"], "degraded")

    def test_no_fetch_ages_to_down(self):
        s = age_source_state(self.ok, E, self.items, fmt(at(hours=7)))
        self.assertEqual(s["fetch_health"], "down")


if __name__ == "__main__":
    unittest.main()
