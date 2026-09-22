"""Bedienbarkeit der Erdbebenkarte: Zoom, Verschieben, Magnitude, Zeitraum.

Am 20.09.2026 lagen 213 Erdbeben im Bestand, Median-Magnitude 1,5 - 163 davon unter
M2.5. Ohne Zusammenfassung und Filter ist die Karte ein Punktenebel. Diese Tests
pruefen die Bedienung gegen site/map.js in node, nicht gegen Textstellen.
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
from tests.helpers import full_registry, raw, real_doc, ROOT, feature
from tests.test_gdacs_map_layer import ALL_FEATURES, feed
from tests.test_gdacs import ENTRY as GDACS_ENTRY
from tests.test_recency_basis import build

PROBE = ROOT / "tests" / "js" / "map_probe.js"
# Gemeinsame Bezugszeit fuer beide Quellen: die GDACS-Fixture stammt vom 20.09.2026,
# die abgeleiteten Beben werden darauf gesetzt.
NOW = dt.datetime(2026, 9, 20, 12, 0, tzinfo=dt.timezone.utc)
RUN_AT = "2026-09-20T12:00:00Z"
FULL = {"id": "map-filter-window", "value": 0}
ALL_MAGS = {"id": "map-filter-magnitude", "value": 0}
STRONG = {"id": "map-filter-magnitude", "value": 6}


def quake(doc, template, fid, mag, lon, lat, minutes_ago=30):
    """Abgeleitete Kopie des echten USGS-Features; jede Aenderung steht hier."""
    f = copy.deepcopy(template)
    p = f["properties"]
    f["id"] = fid
    p["ids"] = f",{fid},"
    p["mag"] = mag
    p["alert"] = None
    p["time"] = int(NOW.timestamp() * 1000) - minutes_ago * 60_000
    p["updated"] = p["time"] + 60_000
    p["title"] = f"M {mag} - abgeleitetes Testbeben {fid}"
    p["url"] = f"https://earthquake.usgs.gov/earthquakes/eventpage/{fid}"
    f["geometry"]["coordinates"] = [lon, lat, 10.0]
    doc["features"].append(f)
    doc["metadata"]["count"] = len(doc["features"])
    return doc


def quake_doc():
    """Vier Beben, wie der 4.5_day-Feed sie liefern kann - drei dicht beieinander.

    Alle liegen ab M4.5: schwaechere Beben stehen gar nicht erst im Feed, also
    duerfen sie auch in den Testdaten nicht vorkommen.
    """
    doc = copy.deepcopy(real_doc())
    template = copy.deepcopy(feature(doc))
    doc["features"] = []
    doc["metadata"]["count"] = 0
    doc["metadata"]["generated"] = int(NOW.timestamp() * 1000)
    quake(doc, template, "tq1000", 6.4, 10.0, 0.0)
    quake(doc, template, "tq1001", 4.6, 10.4, 0.0)     # ueberdeckt tq1000 in der Weltansicht
    quake(doc, template, "tq1002", 4.9, 10.8, 0.0)     # ebenso
    quake(doc, template, "tq1003", 5.1, -70.0, -20.0)  # weit entfernt
    return doc


def scenario(with_gdacs=True):
    reg = full_registry()
    for src in reg["sources"]:
        src["public"] = True
    usgs_entry = next(s for s in reg["sources"] if s["id"] == "usgs")
    result = usgs_adapter.parse(raw(quake_doc()), NOW, usgs_entry)
    items = merge_items({}, "usgs", usgs_entry, result, RUN_AT)
    states = [succeed_source_state(blank_source_state("usgs", "1.0.0"), usgs_entry,
                                   result, items, RUN_AT, "1.0.0")]
    if with_gdacs:
        gres = gdacs.parse(json.dumps(feed(ALL_FEATURES)).encode(), NOW, GDACS_ENTRY)
        items = merge_items(items, "gdacs", GDACS_ENTRY, gres, RUN_AT)
        states.append(succeed_source_state(blank_source_state("gdacs", "1.0.0"),
                                           GDACS_ENTRY, gres, items, RUN_AT, "1.0.0"))
    _, items_doc, sources_doc = build(items, states, RUN_AT)
    reg_scoped = full_registry()
    reg_scoped["sources"] = [s for s in reg_scoped["sources"]
                             if s["id"] in {st["source"] for st in states}]
    for src in reg_scoped["sources"]:
        src["public"] = True
    return snapshot.build(items_doc, sources_doc, reg_scoped, "abc1234", RUN_AT,
                          include_unreleased=True)


def run(snap, toggles):
    if shutil.which("node") is None:
        raise unittest.SkipTest("node nicht verfuegbar - Karte nicht ausgefuehrt")
    payload = {"items": snap["items"], "sources": snap["sources"], "toggles": toggles}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(payload, fh)
        name = fh.name
    try:
        out = subprocess.run(["node", str(PROBE), name], capture_output=True, text=True,
                             timeout=60, check=True)
    finally:
        Path(name).unlink(missing_ok=True)
    return json.loads(out.stdout)


def quake_markers(step):
    return [s for m in step["result"]["markers"] for s in m["shapes"]
            if s["cls"] and "map-event-point" in s["cls"].split()]


def region_markers(step):
    return [s for m in step["result"]["markers"] for s in m["shapes"]
            if s["cls"] and "map-event-region" in s["cls"].split()]


def box(step):
    return [float(n) for n in step["result"]["viewBox"].split()]


class Navigation(unittest.TestCase):
    def test_zoom_narrows_the_view_and_reset_restores_the_whole_world(self):
        steps = run(scenario(), [{"id": "map-zoom-in"}, {"id": "map-zoom-in"},
                                 {"id": "map-zoom-reset"}])
        self.assertEqual(box(steps[0]), [0, 0, 1000, 510])
        self.assertLess(box(steps[1])[2], 1000)
        self.assertLess(box(steps[2])[2], box(steps[1])[2])
        self.assertEqual(box(steps[3]), [0, 0, 1000, 510])

    def test_zoom_out_never_goes_past_the_whole_world(self):
        steps = run(scenario(), [{"id": "map-zoom-out"}, {"id": "map-zoom-out"}])
        for step in steps:
            x, y, w, h = box(step)
            self.assertLessEqual(w, 1000)
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x + w, 1000.01)
            self.assertLessEqual(y + h, 510.01)

    def test_wheel_zoom_uses_pointer_as_focus_not_map_center(self):
        steps = run(scenario(with_gdacs=False), [
            {"event": "wheel", "payload": {"clientX": 800, "clientY": 255, "deltaY": -200}}
        ])
        x, y, w, h = box(steps[-1])
        self.assertLess(w, 1000)
        # Bei Mittelpunkt-Zoom waere x deutlich kleiner; der Punkt unter x=800
        # bleibt hier als Fokus erhalten.
        self.assertGreater(x, 180)

    def test_two_finger_pinch_actually_zooms_the_map(self):
        steps = run(scenario(with_gdacs=False), [
            {"event": "pointerdown", "payload": {
                "pointerId": 1, "pointerType": "touch", "clientX": 400, "clientY": 255,
                "timeStamp": 100}},
            {"event": "pointerdown", "payload": {
                "pointerId": 2, "pointerType": "touch", "clientX": 600, "clientY": 255,
                "timeStamp": 110}},
            {"event": "pointermove", "payload": {
                "pointerId": 2, "pointerType": "touch", "clientX": 750, "clientY": 255,
                "timeStamp": 140}},
        ])
        self.assertLess(box(steps[-1])[2], 700)
        self.assertGreater(box(steps[-1])[0], 0)

    def test_one_finger_drag_pans_after_zooming(self):
        steps = run(scenario(with_gdacs=False), [
            {"id": "map-zoom-in"},
            {"event": "pointerdown", "payload": {
                "pointerId": 7, "pointerType": "touch", "clientX": 500, "clientY": 255,
                "timeStamp": 100}},
            {"event": "pointermove", "payload": {
                "pointerId": 7, "pointerType": "touch", "clientX": 620, "clientY": 255,
                "timeStamp": 160}},
        ])
        self.assertLess(box(steps[-1])[0], box(steps[1])[0])

    def test_zoom_limit_allows_deep_inspection_but_stays_bounded(self):
        steps = run(scenario(with_gdacs=False), [{"id": "map-zoom-in"}] * 14)
        w = box(steps[-1])[2]
        self.assertLessEqual(w, 16)
        self.assertGreaterEqual(w, 1000 / 64 - 0.02)

    def test_zooming_in_pulls_overlapping_quakes_apart(self):
        """Der eigentliche Zweck: drei Beben an fast derselben Stelle sind in der
        Weltansicht ein Marker und werden beim Hineinzoomen einzeln sichtbar."""
        toggles = [FULL, ALL_MAGS] + [{"id": "map-zoom-in"}] * 5
        steps = run(scenario(with_gdacs=False), toggles)
        start = len(quake_markers(steps[2]))
        end = len(quake_markers(steps[-1]))
        self.assertLess(start, 4)      # zusammengefasst
        self.assertGreater(end, start)  # aufgetrennt
        self.assertLessEqual(end, 4)    # nie mehr Marker als Ereignisse

    def test_cluster_marker_names_the_strongest_magnitude_of_the_group(self):
        steps = run(scenario(with_gdacs=False), [FULL, ALL_MAGS])
        clusters = [s for s in quake_markers(steps[2]) if "is-cluster" in s["cls"]]
        self.assertTrue(clusters)
        label = next(m["ariaLabel"] for m in steps[2]["result"]["markers"]
                     for s in m["shapes"] if s is clusters[0])
        self.assertIn("Erdbeben laut USGS", label)
        self.assertIn("stärkstes laut Quelle Magnitude 6.4", label)
        self.assertIn("hineinzoomen", label)


    def test_single_marker_stays_on_conflictwatch_and_selects_event(self):
        toggles = [FULL, ALL_MAGS] + [{"id": "map-zoom-in"}] * 5
        before = run(scenario(with_gdacs=False), toggles)[-1]
        marker = next(m for m in before["result"]["markers"]
                      if "tq1003" in (m["ariaLabel"] or ""))
        self.assertIsNone(marker["href"])
        self.assertEqual(marker["role"], "button")
        self.assertEqual(marker["tabIndex"], "0")
        self.assertIn("Details auf ConflictWatch anzeigen", marker["ariaLabel"])

        clicked = run(scenario(with_gdacs=False),
                      toggles + [{"markerLabelIncludes": "tq1003"}])[-1]
        self.assertFalse(clicked.get("missing", False))
        self.assertTrue(clicked["result"]["selections"])
        self.assertTrue(clicked["result"]["selections"][-1].endswith("tq1003"))
        self.assertTrue(any(m["pressed"] == "true" for m in clicked["result"]["markers"]
                            if "tq1003" in (m["ariaLabel"] or "")))

    def test_cluster_click_zooms_in_instead_of_selecting_or_leaving_site(self):
        steps = run(scenario(with_gdacs=False),
                    [FULL, ALL_MAGS, {"markerLabelIncludes": "hier zusammengefasst"}])
        self.assertFalse(steps[-1].get("missing", False))
        self.assertLess(box(steps[-1])[2], box(steps[-2])[2])
        self.assertEqual(steps[-1]["result"]["selections"], [])
        self.assertTrue(all(m["href"] is None for m in steps[-1]["result"]["markers"]))


class MagnitudeFilter(unittest.TestCase):
    def test_default_hides_nothing_but_names_the_limit_of_the_source(self):
        """Der Bestand ist bereits die Auswahl des USGS-Feeds (ab M4.5). Die Karte
        blendet voreingestellt nichts zusaetzlich aus, nennt aber die Grenze."""
        step = run(scenario(with_gdacs=False), [FULL])[1]
        note = step["result"]["note"]
        self.assertIn("4/4 Erdbeben (USGS)", note)
        self.assertIn('ab Magnitude 4,5', (ROOT / "site/map.js").read_text())
        self.assertNotIn("Kartenprojektion:", (ROOT / "site/index.html").read_text())
        self.assertNotIn("Zusätzlich ausgeblendet", note)

    def test_stricter_filter_is_named_and_marked_as_stored_not_gone(self):
        step = run(scenario(with_gdacs=False), [FULL, STRONG])[2]
        note = step["result"]["note"]
        self.assertIn("1/4 Erdbeben (USGS)", note)
        self.assertIn("1/4", note)

    def test_magnitude_filter_never_touches_sources_without_magnitudes(self):
        """Kontrollfall: ein Magnitudenfilter darf keine Flut verschwinden lassen."""
        strict = run(scenario(), [FULL, STRONG])
        self.assertEqual(len(quake_markers(strict[2])), 1)
        self.assertTrue(region_markers(strict[2]))
        loose = run(scenario(), [FULL, ALL_MAGS])
        self.assertEqual(len(region_markers(strict[2])), len(region_markers(loose[2])))


class TimeWindow(unittest.TestCase):
    def test_window_uses_event_time_for_usgs_and_last_sighting_for_gdacs(self):
        """GDACS-Ereignisse beginnen Monate vor dem Abruf. Zaehlte hier die Anzeigezeit,
        fiele ein heute noch gemeldeter Waldbrand aus 'letzte 24 Stunden' heraus."""
        snap = scenario()
        gdacs_items = [i for i in snap["items"] if i["source"] == "gdacs"]
        self.assertTrue(gdacs_items)
        for it in gdacs_items:
            self.assertEqual(it["last_seen_at"], RUN_AT)
        day = run(snap, [{"id": "map-filter-window", "value": 24}])
        note = day[1]["result"]["note"]
        # Alle GDACS-Meldungen bleiben im 24-Stunden-Fenster, obwohl ihr Beginn
        # Monate zurueckliegt - massgeblich ist die letzte Sichtung.
        self.assertIn("%d/%d Meldungen (GDACS)" % (len(gdacs_items), len(gdacs_items)), note)
        self.assertLess(len(region_markers(day[1])), len(gdacs_items))  # zusammengefasst

    def test_window_selector_offers_the_documented_ranges(self):
        step = run(scenario(), [])[0]
        selects = {s["id"]: s for s in step["result"]["filters"]["selects"]}
        self.assertEqual(selects["map-filter-window"]["options"], ["24", "168", "0"])
        self.assertEqual(selects["map-filter-window"]["value"], "24")
        self.assertEqual(selects["map-filter-magnitude"]["value"], "0")
        self.assertEqual(selects["map-filter-magnitude"]["options"], ["0", "5", "6", "7"])

    def test_quake_clusters_never_merge_with_gdacs_regions(self):
        """Ein punktgenauer Ort und eine ungefaehre Lage duerfen nie ein Marker werden."""
        step = run(scenario(), [FULL, ALL_MAGS])[2]
        for marker in step["result"]["markers"]:
            classes = {c for s in marker["shapes"] if s["cls"] for c in s["cls"].split()}
            self.assertFalse({"map-event-point", "map-event-region"} <= classes)


if __name__ == "__main__":
    unittest.main()
