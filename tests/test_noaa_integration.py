"""Private NOAA integration: authentic source response enters state, never public snapshot."""
import copy
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
GDACS_RAW = (ROOT / "tests" / "fixtures" / "gdacs" / "real_2026-09-20_tc_excerpt.json").read_bytes()
DR_FEATURE = json.loads((ROOT / "tests" / "fixtures" / "gdacs" / "real_2026-09-21_dr_centroid.json").read_text())
VO_RAW = b'{"type":"FeatureCollection","features":[]}'
DR_RAW = json.dumps({"type": "FeatureCollection", "features": [DR_FEATURE]}).encode()


def fixture_fetcher(url: str) -> bytes:
    if url.endswith("noaa-scales.json"):
        return NOAA_RAW
    if url.endswith("4.5_day.geojson"):
        return USGS_RAW
    if url.endswith("gdacs_app_feed.json"):
        return GDACS_RAW
    if url.endswith("gdacsVO.geojson"):
        return VO_RAW
    if url.endswith("gdacsDR.geojson"):
        return DR_RAW
    raise AssertionError(f"Unexpected source URL: {url}")


class NOAAIntegration(unittest.TestCase):
    def test_registry_has_five_released_sources_and_real_endpoints(self):
        reg = full_registry()
        self.assertEqual(check_registry(reg, ADAPTERS), [])
        self.assertEqual({s["id"] for s in reg["sources"]},
                         {"usgs", "noaa-swpc", "gdacs", "gdacs-volcano", "gdacs-drought"})
        self.assertTrue(all(s["public"] is True for s in reg["sources"]))
        for src in reg["sources"]:
            self.assertTrue(src["endpoints"][0].startswith("https://"))
        gdacs = next(s for s in reg["sources"] if s["id"] == "gdacs")
        self.assertEqual(gdacs["max_empty_h"], 72)

    def test_authentic_noaa_statuses_reach_the_public_snapshot(self):
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

            # Alle drei Quellen sind freigegeben: der regulaere Snapshot zeigt sie.
            prod = snapshot.build(items, sources, reg, "abc1234", "2026-09-20T13:30:00Z")
            self.assertEqual(len(prod["sources"]), 5)
            self.assertEqual(len(prod["items"]), 6)  # 1 USGS + 3 NOAA + 1 base GDACS + 1 DR; VO feed is currently empty
            self.assertEqual({i["source"] for i in prod["items"]},
                             {"usgs", "noaa-swpc", "gdacs", "gdacs-drought"})
            self.assertEqual(check_snapshot(prod, reg, CAPTURED_AT), [])

            # Kontrollfall: eine ausdruecklich gesperrte Quelle bleibt auch jetzt draussen.
            blocked = copy.deepcopy(reg)
            next(s for s in blocked["sources"] if s["id"] == "gdacs")["public"] = False
            limited = snapshot.build(items, sources, blocked, "abc1234", "2026-09-20T13:30:00Z")
            self.assertEqual({s["id"] for s in limited["sources"]},
                             {"usgs", "noaa-swpc", "gdacs-volcano", "gdacs-drought"})
            self.assertNotIn("gdacs", {i["source"] for i in limited["items"]})
            self.assertEqual(check_snapshot(limited, blocked, CAPTURED_AT), [])

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
