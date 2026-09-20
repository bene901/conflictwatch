"""GDACS inactive-event expiry: missing != withdrawn, failed/skipped != successful absence."""
import copy
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from cw import pipeline, state
from cw.adapters.base import FetchResult
from cw.errors import AdapterError
from cw.merge import merge_items
from tests.helpers import full_registry, registry as usgs_registry, raw, real_doc
from tests.test_gdacs import ENTRY, NOW, doc, parse

BASE = dt.datetime(2026, 9, 20, 12, 0, tzinfo=dt.timezone.utc)


def stamp(days):
    return (BASE + dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def empty():
    return parse({"type": "FeatureCollection", "features": []})


class GDACSUnseenExpiry(unittest.TestCase):
    def test_survives_day_29_expires_after_day_30_without_withdrawal(self):
        old = merge_items({}, "gdacs", ENTRY, parse(doc()), stamp(0))
        self.assertEqual(old["gdacs:TC:1001324"]["data_status"], "unknown")
        day29 = merge_items(old, "gdacs", ENTRY, empty(), stamp(29))
        self.assertEqual(set(day29), set(old))
        # At exactly the horizon, keep the event; strictly older is removed.
        day30 = merge_items(day29, "gdacs", ENTRY, empty(), stamp(30))
        self.assertEqual(set(day30), set(old))
        day31 = merge_items(day30, "gdacs", ENTRY, empty(), stamp(31))
        self.assertEqual(day31, {})

    def test_counts_from_last_sighting_not_event_or_first_sighting(self):
        first = merge_items({}, "gdacs", ENTRY, parse(doc()), stamp(0))
        again = merge_items(first, "gdacs", ENTRY, parse(doc()), stamp(29))
        self.assertEqual(again["gdacs:TC:1001324"]["ingest"]["first_seen_at"], stamp(0))
        self.assertEqual(again["gdacs:TC:1001324"]["ingest"]["last_seen_at"], stamp(29))
        self.assertIn("gdacs:TC:1001324",
                      merge_items(again, "gdacs", ENTRY, empty(), stamp(59)))
        self.assertEqual(merge_items(again, "gdacs", ENTRY, empty(), stamp(60)), {})

    def test_null_expiry_preserves_legacy_incomplete_and_complete_source_rules(self):
        entry = copy.deepcopy(ENTRY)
        entry["unseen_expiry_days"] = None
        old = merge_items({}, "gdacs", entry, parse(doc()), stamp(0))
        self.assertEqual(set(merge_items(old, "gdacs", entry, empty(), stamp(61))), set(old))
        usgs = usgs_registry()["sources"][0]
        from cw.adapters import usgs as usgs_adapter
        first = usgs_adapter.parse(raw(real_doc()), BASE, usgs)
        usgs_items = merge_items({}, "usgs", usgs, first, stamp(0))
        assert usgs_items
        complete_empty = FetchResult(items=[], complete=True, items_in_window=0)
        self.assertEqual(merge_items(usgs_items, "usgs", usgs, complete_empty, stamp(61)), {})

    def test_pipeline_failed_and_skipped_runs_never_delete_events(self):
        reg = full_registry()
        reg["sources"] = [next(s for s in reg["sources"] if s["id"] == "gdacs")]
        reg["domains"] = [next(d for d in reg["domains"] if d["id"] == "disaster")]
        raw_good = __import__("json").dumps(doc()).encode()
        def ok_fetch(_url):
            return raw_good
        def bad_fetch(_url):
            raise AdapterError("network", "simulated failed response")
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.assertEqual(pipeline.run(reg, folder, now=BASE, fetcher=ok_fetch,
                                          log=lambda *_: None), 0)
            first, _ = state.load(folder)
            self.assertEqual(len(first["items"]), 1)
            self.assertEqual(pipeline.run(reg, folder, now=BASE + dt.timedelta(days=31),
                                          fetcher=bad_fetch, log=lambda *_: None), 0)
            after_error, _ = state.load(folder)
            self.assertEqual(after_error["items"], first["items"])
            self.assertEqual(pipeline.run(reg, folder, fetch=False,
                                          now=BASE + dt.timedelta(days=32),
                                          fetcher=bad_fetch, log=lambda *_: None), 0)
            after_skip, _ = state.load(folder)
            self.assertEqual(after_skip["items"], first["items"])
            def valid_empty(_url):
                return b'{"type":"FeatureCollection","features":[]}'
            self.assertEqual(pipeline.run(reg, folder, now=BASE + dt.timedelta(days=33),
                                          fetcher=valid_empty, log=lambda *_: None), 0)
            after_success, sources = state.load(folder)
            self.assertEqual(after_success["items"], [])
            self.assertEqual(sources["sources"][0]["last_fetch_complete"], False)


if __name__ == "__main__":
    unittest.main()
