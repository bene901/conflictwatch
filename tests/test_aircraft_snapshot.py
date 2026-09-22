"""ADS-B aircraft context: source semantics, expiry and fail-closed behavior."""
import datetime as dt
import json
import unittest

from cw.errors import AdapterError
from scripts.build_aircraft_snapshot import build, normalize

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 22, 19, 0, tzinfo=UTC)
NOW_MS = int(NOW.timestamp() * 1000)


def aircraft(ident="abc123", lat=52.5, lon=13.4, seen_pos=2, flags=1):
    return {"hex": ident, "lat": lat, "lon": lon, "seen_pos": seen_pos,
            "dbFlags": flags, "flight": "TEST  ", "t": "C30J",
            "alt_baro": 12000, "gs": 240}


def payload(rows, now=NOW_MS):
    return json.dumps({"now": now, "ac": rows}).encode()


class ADSBSnapshot(unittest.TestCase):
    def test_keeps_only_recent_sourced_military_positions(self):
        rows = [aircraft(), aircraft("abc123", 30, 20),
                aircraft("abc124", seen_pos=240),
                aircraft("abc125", flags=0),
                aircraft("abc126", lat=99),
                aircraft("abc127", lon=None),
                aircraft("abc128", seen_pos=20)]
        doc = normalize(payload(rows), NOW)
        self.assertEqual(doc["status"], "ok")
        self.assertEqual([a["id"] for a in doc["aircraft"]], ["abc123", "abc128"])
        self.assertEqual(doc["aircraft"][0]["callsign"], "TEST")
        self.assertEqual(doc["aircraft"][0]["position_time"], "2026-09-22T18:59:58Z")
        self.assertEqual(doc["aircraft"][0]["lat"], 52.5)
        self.assertIn("ODbL", doc["attribution"])
        self.assertNotIn("track_history", doc)

    def test_outdated_source_response_rejected(self):
        stale = payload([aircraft()], NOW_MS - 20 * 60 * 1000)
        with self.assertRaisesRegex(ValueError, "outdated_source_response"):
            normalize(stale, NOW)

    def test_failure_never_republishes_previous_flight_positions(self):
        def unavailable(_):
            raise AdapterError("http", "HTTP 429")
        doc = build(fetcher=unavailable, now=NOW)
        self.assertEqual(doc["status"], "unavailable")
        self.assertEqual(doc["aircraft"], [])
        self.assertEqual(doc["error_code"], "http")

    def test_empty_means_no_observed_positions_not_no_military_activity(self):
        doc = normalize(payload([aircraft(seen_pos=180)]), NOW)
        self.assertEqual(doc["status"], "empty")
        self.assertEqual(doc["aircraft"], [])
        self.assertIn("Keine vollständige Militärflugliste", doc["coverage_note"])


if __name__ == "__main__":
    unittest.main()
