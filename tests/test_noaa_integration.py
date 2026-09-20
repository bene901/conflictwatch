"""Private NOAA integration: authentic source response enters state, never public snapshot."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from cw import pipeline, snapshot, state
from cw.validate import check_registry, check_snapshot, check_state
from cw.adapters import ADAPTERS
from tests.helpers import full_registry, raw, real_doc, ROOT

UTC = dt.timezone.utc
CAPTURED_AT = dt.datetime(2026, 9, 20, 13, 30, tzinfo=UTC)
NOAA_RAW = (ROOT / "tests" / "fixtures" / "noaa" / "real_2026-09-20_noaa_scales.json").read_bytes()
USGS_RAW = raw(real_doc())


def fixture_fetcher(url: str) -> bytes:
    if url.endswith("noaa-scales.json"):
        return NOAA_RAW
    if url.endswith("significant_week.geojson"):
        return USGS_RAW
    raise AssertionError(f"Unexpected source URL: {url}")


class NOAAIntegration(unittest.TestCase):
    def test_registry_has_two_private_sources_and_real_endpoints(self):
        reg = full_registry()
        self.assertEqual(check_registry(reg, ADAPTERS), [])
        self.assertEqual({s["id"] for s in reg["sources"]}, {"usgs", "noaa-swpc"})
        self.assertTrue(all(s["public"] is False for s in reg["sources"]))

    def test_authentic_noaa_statuses_ingested_but_not_published(self):
        reg = full_registry()
        with tempfile.TemporaryDirectory() as temp:
            state_dir = Path(temp)
            code = pipeline.run(reg, state_dir, now=CAPTURED_AT, fetcher=fixture_fetcher,
                                log=lambda *_: None)
            self.assertEqual(code, 0)
            items, sources = state.load(state_dir)
            self.assertEqual(check_state(items, sources, reg, CAPTURED_AT), [])
            states = {s["source"]: s for s in sources["sources"]}
            noaa = states["noaa-swpc"]
            self.assertEqual((noaa["fetch_health"], noaa["data_state"]), ("ok", "fresh"))
            self.assertEqual(noaa["items_in_window"], 3)
            self.assertEqual(noaa["last_success_at"], "2026-09-20T13:30:00Z")
            self.assertEqual(noaa["newest_source_time"], "2026-09-20T13:26:00Z")

            rows = [i for i in items["items"] if i["source"] == "noaa-swpc"]
            self.assertEqual(len(rows), 3)
            self.assertEqual([i["level"]["value"] for i in rows], ["0", "0", "0"])
            self.assertEqual({i["observed_at"] for i in rows}, {"2026-09-20T13:26:00Z"})

            prod = snapshot.build(items, sources, reg, "testrev", "2026-09-20T13:30:00Z")
            self.assertEqual(prod["sources"], [])
            self.assertEqual(prod["items"], [])
            self.assertEqual(check_snapshot(prod, reg, CAPTURED_AT), [])

            preview = snapshot.build(items, sources, reg, "testrev", "2026-09-20T13:30:00Z",
                                     include_unreleased=True)
            self.assertEqual(len(preview["sources"]), 2)
            self.assertEqual(len(preview["items"]), 4)
            self.assertEqual(check_snapshot(preview, reg, CAPTURED_AT, preview=True), [])

    def test_old_noaa_observation_is_not_marked_fresh_after_repeated_fetch(self):
        reg = full_registry()
        with tempfile.TemporaryDirectory() as temp:
            state_dir = Path(temp)
            self.assertEqual(pipeline.run(reg, state_dir, now=CAPTURED_AT,
                                          fetcher=fixture_fetcher, log=lambda *_: None), 0)
            later = CAPTURED_AT + dt.timedelta(hours=3)
            self.assertEqual(pipeline.run(reg, state_dir, now=later,
                                          fetcher=fixture_fetcher, log=lambda *_: None), 0)
            items, sources = state.load(state_dir)
            st = next(s for s in sources["sources"] if s["source"] == "noaa-swpc")
            self.assertEqual(st["data_state"], "old")
            self.assertEqual(st["fetch_health"], "ok")
            self.assertEqual(check_state(items, sources, reg, later), [])


if __name__ == "__main__":
    unittest.main()
