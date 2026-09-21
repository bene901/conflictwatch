"""Wirkungsfelder: was ein Beben fuer Menschen bedeutet, nicht nur wie stark es war.

Magnitude allein beantwortet das nicht - das M6.5 vom 19.09.2026 lag in 98 km Tiefe
und erreichte vor Ort Mercalli V. USGS liefert dafuer eigene Felder; sie werden
unveraendert uebernommen und in der Oberflaeche eingeordnet, nicht bewertet.
"""
import copy
import datetime as dt
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from cw.adapters import usgs
from cw.errors import AdapterError
from cw.registry import load
from tests.helpers import NOW, derived, feature, full_registry, raw, real_doc, ROOT

PROBE = ROOT / "tests" / "js" / "recency_probe.js"
ENTRY = next(s for s in full_registry()["sources"] if s["id"] == "usgs")


def parse(doc):
    return usgs.parse(raw(doc), NOW, ENTRY)


def metrics_texts(metrics):
    if shutil.which("node") is None:
        raise unittest.SkipTest("node nicht verfuegbar - Messwerttexte nicht ausgefuehrt")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump({"metrics": metrics}, fh)
        name = fh.name
    try:
        out = subprocess.run(["node", str(PROBE), name], capture_output=True, text=True,
                             timeout=60, check=True)
    finally:
        Path(name).unlink(missing_ok=True)
    return json.loads(out.stdout)


class AdapterKeepsImpactFields(unittest.TestCase):
    def test_real_response_carries_shaking_reports_and_felt_count(self):
        m = parse(real_doc()).items[0]["metrics"]
        self.assertEqual(m["shaking_mmi"], 4.983)   # instrumentell geschaetzt
        self.assertEqual(m["reported_cdi"], 3.4)    # von Menschen gemeldet
        self.assertEqual(m["felt_reports"], 8)

    def test_missing_impact_fields_become_null_not_zero(self):
        """Kontrollfall: 0 hiesse 'nicht gespuert', null heisst 'nicht angegeben'."""
        doc = derived(lambda d: [feature(d)["properties"].pop(k, None)
                                 for k in ("mmi", "cdi", "felt")])
        m = parse(doc).items[0]["metrics"]
        self.assertIsNone(m["shaking_mmi"])
        self.assertIsNone(m["reported_cdi"])
        self.assertIsNone(m["felt_reports"])

    def test_tsunami_region_flag_and_internal_rank_stay_out(self):
        """tsunami:1 heisst laut USGS nur 'grosses Beben in ozeanischer Region'.
        Als Gefahrenangabe waere es falsch - die echte Antwort hat das Flag gesetzt."""
        self.assertEqual(feature(real_doc())["properties"]["tsunami"], 1)
        item = parse(real_doc()).items[0]
        self.assertNotIn("tsunami", json.dumps(item))
        self.assertNotIn("sig", item["metrics"])

    def test_values_outside_the_mercalli_scale_are_refused(self):
        for field, value in (("mmi", 13.0), ("cdi", -1.0)):
            doc = derived(lambda d, f=field, v=value: feature(d)["properties"].update({f: v}))
            with self.subTest(field=field), self.assertRaises(AdapterError) as cm:
                parse(doc)
            self.assertEqual(cm.exception.kind, "sanity")

    def test_felt_count_must_be_a_whole_non_negative_number(self):
        for value in (-3, "viele", 2.5):
            doc = derived(lambda d, v=value: feature(d)["properties"].update({"felt": v}))
            with self.subTest(value=value), self.assertRaises(AdapterError):
                parse(doc)


class DisplayExplainsTheScale(unittest.TestCase):
    def test_measured_value_and_rounded_step_stay_distinguishable(self):
        text = metrics_texts([{"magnitude": 6.5, "magnitude_type": "mww", "depth_km": 98,
                               "shaking_mmi": 4.983, "reported_cdi": 3.4, "felt_reports": 8}])[0]
        self.assertIn("Mercalli V – von fast allen gespürt (Messwert 4,98)", text)
        self.assertIn("Mercalli III – schwach gespürt (Messwert 3,4)", text)
        self.assertIn("8 Rückmeldungen von Menschen", text)
        self.assertNotIn("shaking_mmi", text)  # keine Rohfeldnamen in der Anzeige

    def test_scale_steps_follow_the_rounding_of_the_scale(self):
        cases = [(1.0, "I"), (2.4, "II"), (3.2, "III"), (4.49, "IV"), (4.5, "V"),
                 (6.4, "VI"), (7.8, "VIII"), (12.0, "XII")]
        texts = metrics_texts([{"shaking_mmi": v} for v, _ in cases])
        for (value, roman), text in zip(cases, texts):
            with self.subTest(value=value):
                self.assertIn("Mercalli " + roman + " –", text)

    def test_single_report_is_not_called_reports(self):
        self.assertIn("1 Rückmeldung von Menschen", metrics_texts([{"felt_reports": 1}])[0])

    def test_page_says_that_a_missing_effect_is_not_an_all_clear(self):
        js = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Das heißt nicht, dass das Beben nicht gespürt wurde.", js)


if __name__ == "__main__":
    unittest.main()
