import datetime as dt
import io
import unittest
import zipfile

from cw.adapters import ADAPTERS
from cw.adapters import gdelt, ucdp_candidate
from cw.validate import check_registry
from tests.helpers import full_registry

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 22, 16, 0, tzinfo=UTC)


def source(source_id):
    return next(s for s in full_registry()["sources"] if s["id"] == source_id)


UCDP_CSV = """id,type_of_violence,side_a,side_b,date_start,date_end,date_prec,where_prec,where_coordinates,where_description,country,latitude,longitude,low,best,high
1001,1,State A,State B,2026-08-20,2026-08-20,1,1,Test City,Test City,Exampleland,10.5,20.5,5,10,8
1002,3,Group C,Civilians,2026-08-21,2026-08-22,2,6,Exampleland,,Exampleland,12.0,22.0,1,2,3
"""


def gdelt_row(gid="9001", code="195", root="1"):
    row = [""] * 61
    row[0] = gid
    row[1] = "20260922"
    row[6] = "STATE A"
    row[16] = "STATE B"
    row[25] = root
    row[26] = code
    row[31] = "12"
    row[32] = "3"
    row[33] = "4"
    row[51] = "4"
    row[52] = "Test City, Exampleland"
    row[56] = "10.5"
    row[57] = "20.5"
    row[59] = "20260922154500"
    row[60] = "https://example.org/report"
    return "\t".join(row)


class UCDPCandidate(unittest.TestCase):
    def test_preserves_contradictory_fatality_values_and_flags_them(self):
        result = ucdp_candidate.parse(UCDP_CSV.encode(), NOW, source("ucdp-candidate"))
        self.assertEqual(len(result.items), 2)
        self.assertTrue(result.complete)
        item = result.items[0]
        self.assertEqual(item["location"]["precision"], "point")
        self.assertEqual(item["metrics"]["fatalities_low"], 5)
        self.assertEqual(item["metrics"]["fatalities_best"], 10)
        self.assertEqual(item["metrics"]["fatalities_high"], 8)
        self.assertTrue(item["metrics"]["fatalities_inconsistent"])
        self.assertEqual(result.items[1]["location"]["precision"], "country")

    def test_where_prec_7_stays_regional_instead_of_becoming_a_country_point(self):
        raw = UCDP_CSV.replace(",2,6,Exampleland,,Exampleland,12.0,22.0,",
                               ",2,7,International waters,,Exampleland,12.0,22.0,")
        result = ucdp_candidate.parse(raw.encode(), NOW, source("ucdp-candidate"))
        self.assertEqual(result.items[1]["location"]["precision"], "region")

    def test_discovers_newest_monthly_candidate_csv_without_hardcoding_version(self):
        page = b'''<a href="/downloads/candidateged/GEDEvent_v26_0_7.csv">old</a>
<a href="/downloads/candidateged/GEDEvent_v26_0_8.csv">new</a>
<a href="/downloads/ged/GEDEvent_v26_1.csv">full</a>'''
        calls = []
        def fetch(url):
            calls.append(url)
            if url.endswith("/downloads/"):
                return page
            if url.endswith("GEDEvent_v26_0_8.csv"):
                return UCDP_CSV.encode()
            raise AssertionError(url)
        raw = ucdp_candidate.fetch_latest(fetch, source("ucdp-candidate"))
        self.assertEqual(raw, UCDP_CSV.encode())
        self.assertTrue(calls[-1].endswith("GEDEvent_v26_0_8.csv"))


class GDELTEvents(unittest.TestCase):
    def test_keeps_only_selected_root_military_codes_and_marks_claim_unverified(self):
        raw = (gdelt_row("9001", "195") + "\n" +
               gdelt_row("9002", "051") + "\n" +
               gdelt_row("9003", "194", root="0") + "\n").encode()
        result = gdelt.parse(raw, NOW, source("gdelt"))
        self.assertFalse(result.complete)
        self.assertEqual(len(result.items), 1)
        item = result.items[0]
        self.assertEqual(item["id"], "gdelt:9001")
        self.assertEqual(item["provenance"], "claim")
        self.assertTrue(item["metrics"]["automated_unverified"])
        self.assertEqual(item["location"]["precision"], "region")

    def test_recent_fetch_uses_latest_export_plus_overlap_and_returns_tsv(self):
        payload = (gdelt_row() + "\n").encode()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("20260922154500.export.CSV", payload)
        packed = buf.getvalue()
        calls = []
        index = b"123 abc http://data.gdeltproject.org/gdeltv2/20260922154500.export.CSV.zip\n"
        def fetch(url):
            calls.append(url)
            return index if url.endswith("lastupdate.txt") else packed
        raw = gdelt.fetch_recent(fetch, source("gdelt"))
        self.assertIn(b"9001", raw)
        self.assertEqual(len(calls), 1 + gdelt.FETCH_WINDOWS)
        self.assertTrue(all(u.startswith("https://") for u in calls[1:]))

    def test_production_registry_accepts_both_conflict_sources(self):
        reg = full_registry()
        self.assertEqual(check_registry(reg, ADAPTERS), [])
        self.assertTrue({"ucdp-candidate", "gdelt"} <= {s["id"] for s in reg["sources"]})


if __name__ == "__main__":
    unittest.main()
