"""Offline tests for the isolated NOAA draft adapter.

Fixtures below are intentionally SYNTHETIC examples based on publicly described
noaa-scales.json structure. They do not substitute for a live NOAA response.
"""
import copy
import datetime as dt
import json
import unittest

from cw.adapters import noaa_swpc
from cw.errors import AdapterError
from cw.validate import check_items

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


def entry():
    return {
        "id": "noaa-swpc", "domain": "spaceweather", "kinds": ["status"],
        "level_schemes": [
            {"id": "noaa-" + code.lower(), "ordered_values": [str(i) for i in range(6)],
             "labels": {str(i): code + str(i) for i in range(6)},
             "reference_url": "https://www.swpc.noaa.gov/noaa-scales-explanation"}
            for code in "GSR"
        ],
    }


def payload():
    return {"0": {"DateStamp": "2026-09-20", "TimeStamp": "11:30:00",
                  "G": {"Scale": "3"}, "S": {"Scale": "0"}, "R": {"Scale": "1"}},
            "-1": {"G": {"Scale": "5"}, "S": {"Scale": "5"}, "R": {"Scale": "5"}},
            "1": {"G": {"Scale": "5"}, "S": {"Scale": None}, "R": {"Scale": "5"}}}


def parse(doc):
    return noaa_swpc.parse(json.dumps(doc).encode(), NOW, entry())


class NoaaDraft(unittest.TestCase):
    def test_three_observed_statuses_ignore_forecast_and_maximum(self):
        r = parse(payload())
        self.assertTrue(r.complete)
        self.assertEqual((r.items_in_window, len(r.items)), (3, 3))
        self.assertEqual([i["id"] for i in r.items],
                         ["noaa-swpc:scale:G", "noaa-swpc:scale:S", "noaa-swpc:scale:R"])
        self.assertEqual([i["level"]["value"] for i in r.items], ["3", "0", "1"])
        self.assertEqual([i["observed_at"] for i in r.items], ["2026-09-20T11:30:00Z"] * 3)

    def test_normalized_items_pass_common_validator(self):
        r = parse(payload())
        reg = {"domains": [{"id": "spaceweather", "label": "Weltraumwetter"}],
               "sources": [entry()]}
        # The adapter returns ItemDrafts; the shared validator checks merged Items.
        from cw.merge import merge_items
        from cw.timeutil import fmt
        merged = merge_items({}, "noaa-swpc", entry(), r, fmt(NOW))
        self.assertEqual(check_items(list(merged.values()), reg, NOW), [])

    def test_missing_current_block_is_not_success(self):
        d = payload()
        del d["0"]
        with self.assertRaises(AdapterError) as err:
            parse(d)
        self.assertEqual(err.exception.kind, "schema")

    def test_no_data_is_not_level_zero(self):
        for invalid in (None, "", "no data", 0, "6"):
            d = payload()
            d["0"]["G"]["Scale"] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(AdapterError) as err:
                parse(d)
            self.assertEqual(err.exception.kind, "schema")

    def test_missing_individual_status_is_error_not_partial_all_clear(self):
        d = payload()
        del d["0"]["S"]
        with self.assertRaises(AdapterError) as err:
            parse(d)
        self.assertEqual(err.exception.kind, "schema")

    def test_invalid_or_future_observation_time(self):
        for date, clock, kind in [
            ("2026-02-30", "11:30:00", "schema"),
            ("2026-09-20", "25:00:00", "schema"),
            ("2026-09-20", "15:00:00", "sanity"),
        ]:
            d = payload()
            d["0"]["DateStamp"], d["0"]["TimeStamp"] = date, clock
            with self.subTest(date=date, clock=clock), self.assertRaises(AdapterError) as err:
                parse(d)
            self.assertEqual(err.exception.kind, kind)

    def test_bad_json_and_unknown_registry_scale(self):
        with self.assertRaises(AdapterError) as err:
            noaa_swpc.parse(b"<html>not json</html>", NOW, entry())
        self.assertEqual(err.exception.kind, "parse")
        e = entry()
        e["level_schemes"] = e["level_schemes"][1:]
        with self.assertRaises(AdapterError) as err:
            noaa_swpc.parse(json.dumps(payload()).encode(), NOW, e)
        self.assertEqual(err.exception.kind, "schema")


if __name__ == "__main__":
    unittest.main()
