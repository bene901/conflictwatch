"""GDACS-Kartenlayer: regionale Zentroide, Zusammenfassung, Filter, Sichtung.

Grundregel dieses Layers: ein GDACS-Zentroid ist eine UNGEFAEHRE Lage und darf nie
wie eine punktgenaue USGS-Koordinate auftreten. Warnstufen bleiben Einstufungen der
Quelle; ConflictWatch leitet daraus keine eigene Gefahrenbewertung ab.
"""
import copy
import datetime as dt
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from cw import snapshot
from cw.adapters import gdacs, usgs as usgs_adapter
from cw.merge import blank_source_state, merge_items, succeed_source_state
from tests.helpers import full_registry, raw, real_doc, ROOT
from tests.test_gdacs import ENTRY as GDACS_ENTRY, doc as gdacs_doc
from tests.test_recency_basis import build

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
T0 = "2026-09-20T10:00:00Z"
T1 = "2026-09-20T12:00:00Z"
PROBE = ROOT / "tests" / "js" / "map_probe.js"

# Zwei Waldbraende gut 1 Grad auseinander ueberdecken einander auf der Weltkarte,
# 50 Grad entfernt nicht. Die Flut liegt bewusst zwischen den beiden Waldbraenden.
WILDFIRE_A = (10.0, 0.0)
WILDFIRE_B = (11.0, 0.0)
WILDFIRE_FAR = (60.0, 0.0)
FLOOD_NEAR = (10.4, 0.0)
CYCLONE = (-124.5, 11.4)


def feature(hazard, eventid, lon, lat, level="Green", name=None):
    """Abgeleitet aus dem echten TC-Feature; jede Aenderung steht hier ausdruecklich."""
    f = copy.deepcopy(gdacs_doc()["features"][0])
    p = f["properties"]
    p["eventtype"] = hazard
    p["eventid"] = eventid
    p["alertlevel"] = level
    p["name"] = name or (hazard + " Testereignis " + str(eventid))
    p["url"]["report"] = ("https://www.gdacs.org/report.aspx?eventtype=" + hazard +
                          "&eventid=" + str(eventid))
    f["geometry"]["coordinates"] = [lon, lat]
    return f


def feed(features):
    return {"type": "FeatureCollection", "features": features}


ALL_FEATURES = [
    feature("WF", 9001, *WILDFIRE_A),
    feature("WF", 9002, *WILDFIRE_B),
    feature("WF", 9003, *WILDFIRE_FAR),
    feature("FL", 9004, *FLOOD_NEAR),
    feature("TC", 9005, *CYCLONE, level="Orange"),
]
# Im zweiten Abruf fehlt der entfernte Waldbrand: er bleibt gespeichert, gilt aber
# nicht mehr als frisch gesehen. Das ist keine Entwarnung.
SECOND_FETCH = [f for f in ALL_FEATURES if f["properties"]["eventid"] != 9003]


def parse(features, run_at_now=NOW):
    return gdacs.parse(json.dumps(feed(features)).encode(), run_at_now, GDACS_ENTRY)


def scenario(second=SECOND_FETCH, with_usgs=True):
    """Zwei erfolgreiche GDACS-Abrufe, optional USGS daneben -> echter Snapshot."""
    items = merge_items({}, "gdacs", GDACS_ENTRY, parse(ALL_FEATURES), T0)
    result = parse(second)
    items = merge_items(items, "gdacs", GDACS_ENTRY, result, T1)
    states = [succeed_source_state(blank_source_state("gdacs", "1.0.0"), GDACS_ENTRY,
                                   result, items, T1, "1.0.0")]
    if with_usgs:
        entry = next(s for s in full_registry()["sources"] if s["id"] == "usgs")
        usgs_result = usgs_adapter.parse(raw(real_doc()), NOW, entry)
        items = merge_items(items, "usgs", entry, usgs_result, T1)
        states.append(succeed_source_state(blank_source_state("usgs", "1.0.0"), entry,
                                           usgs_result, items, T1, "1.0.0"))
    reg, items_doc, sources_doc = build(items, states, T1)
    return snapshot.build(items_doc, sources_doc, reg, "abc1234", T1, include_unreleased=True)


FULL_WINDOW = {"id": "map-filter-window", "value": 0}


def run_map(snap, toggles=None, full_window=True):
    """full_window=True stellt den Zeitfilter auf den gesamten Datenstand.

    Diese Tests pruefen Marker, Zusammenfassung und Gefahrenfilter, nicht den
    Zeitfilter; der hat eigene Tests. Ohne diese Vorgabe haengt das Ergebnis am
    Abstand zwischen Fixture-Zeitpunkt und Abrufzeit.
    """
    if shutil.which("node") is None:
        raise unittest.SkipTest("node nicht verfuegbar - Kartenlayer nicht ausgefuehrt")
    steps = list(toggles or [])
    if full_window:
        steps.insert(0, FULL_WINDOW)
    payload = {"items": snap["items"], "sources": snap["sources"], "toggles": steps}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(payload, fh)
        name = fh.name
    try:
        out = subprocess.run(["node", str(PROBE), name], capture_output=True, text=True,
                             timeout=60, check=True)
    finally:
        Path(name).unlink(missing_ok=True)
    result = json.loads(out.stdout)
    return result[1:] if full_window else result


def shapes(step, cls):
    found = []
    for marker in step["result"]["markers"]:
        for s in marker["shapes"]:
            if s["cls"] and cls in s["cls"].split():
                found.append({**s, "ariaLabel": marker["ariaLabel"], "href": marker["href"]})
    return found


class PointPrecisionUnchanged(unittest.TestCase):
    def test_usgs_points_keep_their_marker_and_are_never_region_marked(self):
        step = run_map(scenario())[0]
        points = shapes(step, "map-event-point")
        self.assertTrue(points)
        for p in points:
            self.assertAlmostEqual(float(p["r"]), 8)
            self.assertIsNone(p["level"])  # USGS bekommt keine GDACS-Stufenfarbe
            self.assertNotIn("ungefähre Lage", p["ariaLabel"])
        self.assertIn("Erdbeben (USGS)", step["result"]["note"])

    def test_region_events_never_render_as_point_markers(self):
        """Kontrollfall: ohne die Trennung waeren 87 Zentroide punktgenaue Gefahrenorte."""
        step = run_map(scenario(with_usgs=False))[0]
        self.assertEqual(shapes(step, "map-event-point"), [])
        self.assertTrue(shapes(step, "map-event-region"))


class RegionPresentation(unittest.TestCase):
    def test_every_region_marker_says_it_is_approximate_and_no_damage_area(self):
        step = run_map(scenario())[0]
        regions = shapes(step, "map-event-region")
        self.assertTrue(regions)
        for r in regions:
            self.assertIn("ungefähre Lage laut GDACS – keine Schadensfläche", r["ariaLabel"])

    def test_level_colour_is_the_sources_own_grade_and_nothing_else(self):
        step = run_map(scenario())[0]
        regions = shapes(step, "map-event-region")
        levels = {r["level"] for r in regions}
        self.assertTrue(levels <= {"green", "orange"}, levels)
        cyclone = next(r for r in regions if "TC" in r["ariaLabel"] or "Wirbelsturm" in r["ariaLabel"]
                       or "Orange" in r["ariaLabel"])
        self.assertEqual(cyclone["level"], "orange")
        self.assertIn("Warnstufe laut GDACS", cyclone["ariaLabel"])
        legend = step["result"]["legend"]
        self.assertFalse(legend["hidden"])
        self.assertIn("weitere Ereignisse", legend["text"])

    def test_single_region_marker_opens_conflictwatch_detail_before_original_report(self):
        step = run_map(scenario())[0]
        cyclone = next(r for r in shapes(step, "map-event-region") if "Orange" in r["ariaLabel"])
        self.assertIsNone(cyclone["href"])
        self.assertIn("Details auf ConflictWatch anzeigen", cyclone["ariaLabel"])


class Clustering(unittest.TestCase):
    def test_overlapping_wildfires_collapse_into_one_counted_marker(self):
        step = run_map(scenario())[0]
        clusters = shapes(step, "is-cluster")
        self.assertEqual(len(clusters), 1)
        self.assertIn("2 Waldbrände laut GDACS", clusters[0]["ariaLabel"])
        self.assertIn("weil sich die Marker überdecken", clusters[0]["ariaLabel"])
        counts = [s for m in step["result"]["markers"] for s in m["shapes"]
                  if s["cls"] == "map-cluster-count"]
        self.assertEqual([c["text"] for c in counts], ["2"])

    def test_different_hazards_at_the_same_spot_are_never_merged(self):
        """Die Flut liegt zwischen den beiden Waldbraenden und bleibt ein eigener Marker."""
        step = run_map(scenario())[0]
        regions = shapes(step, "map-event-region")
        flood = [r for r in regions if "Überschwemmung" in r["ariaLabel"] or "FL" in r["ariaLabel"]]
        self.assertEqual(len(flood), 1)
        self.assertNotIn("is-cluster", (flood[0]["cls"] or ""))

    def test_distant_wildfire_stays_its_own_marker(self):
        step = run_map(scenario(second=ALL_FEATURES))[0]
        wildfires = [r for r in shapes(step, "map-event-region")
                     if "Waldbrand" in r["ariaLabel"] or "Waldbrände" in r["ariaLabel"]]
        self.assertEqual(len(wildfires), 2)  # ein Cluster aus zweien + der entfernte
        self.assertEqual(sum(1 for w in wildfires if "is-cluster" in (w["cls"] or "")), 1)


class RecencyAndFilters(unittest.TestCase):
    def test_default_shows_only_events_from_the_latest_successful_fetch(self):
        step = run_map(scenario(), full_window=False)[0]
        labels = " ".join(r["ariaLabel"] for r in shapes(step, "map-event-region"))
        self.assertNotIn("9003", labels)
        self.assertIn("1 ältere Meldung ausgeblendet", step["result"]["note"])
        self.assertIn("keine Entwarnung", step["result"]["note"])

    def test_older_events_appear_only_through_their_own_filter_and_stay_marked(self):
        steps = run_map(scenario(), toggles=[{"id": "map-filter-older", "checked": True}])
        before, after = steps[0], steps[1]
        self.assertLess(len(shapes(before, "map-event-region")),
                        len(shapes(after, "map-event-region")))
        older = shapes(after, "is-older")
        self.assertEqual(len(older), 1)
        self.assertIn("nicht aus dem jüngsten Abruf", older[0]["ariaLabel"])
        self.assertIn("keine Entwarnung", older[0]["ariaLabel"])

    def test_filters_exist_per_hazard_and_hide_only_that_hazard(self):
        steps = run_map(scenario(), toggles=[{"id": "map-filter-wildfire", "checked": False}])
        boxes = {b["id"] for b in steps[0]["result"]["filters"]["boxes"]}
        self.assertEqual(boxes, {"map-filter-wildfire", "map-filter-flood",
                                 "map-filter-tropical-cyclone", "map-filter-older"})
        self.assertFalse(steps[0]["result"]["filters"]["hidden"])

        after = steps[1]
        labels = [r["ariaLabel"] for r in shapes(after, "map-event-region")]
        self.assertFalse([l for l in labels if "Waldbrand" in l or "Waldbrände" in l])
        self.assertTrue([l for l in labels if "Überschwemmung" in l or "FL" in l])
        self.assertTrue(shapes(after, "map-event-point"))  # USGS bleibt unberuehrt

    def test_without_region_events_no_hazard_filters_and_no_gdacs_legend(self):
        entry = next(s for s in full_registry()["sources"] if s["id"] == "usgs")
        result = usgs_adapter.parse(raw(real_doc()), NOW, entry)
        items = merge_items({}, "usgs", entry, result, T1)
        st = succeed_source_state(blank_source_state("usgs", "1.0.0"), entry, result,
                                  items, T1, "1.0.0")
        reg, items_doc, sources_doc = build(items, [st], T1)
        snap = snapshot.build(items_doc, sources_doc, reg, "abc1234", T1, include_unreleased=True)
        step = run_map(snap)[0]
        boxes = {b["id"] for b in step["result"]["filters"]["boxes"]}
        self.assertEqual(boxes, set())  # keine Gefahrenart-Filter ohne GDACS-Daten
        self.assertNotIn("GDACS", step["result"]["legend"]["text"])
        self.assertIn("Erdbeben", step["result"]["legend"]["text"])
        self.assertTrue(shapes(step, "map-event-point"))


if __name__ == "__main__":
    unittest.main()
