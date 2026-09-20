"""Aktualitaet nach Quellentyp.

Kernunterscheidung: "im juengsten erfolgreichen Abruf enthalten" ist NICHT
"Ereignis dauert nachweislich an". Die Regel darf nur das Erste behaupten.
"""
import copy
import datetime as dt
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from cw import snapshot, state
from cw.adapters import gdacs, usgs as usgs_adapter
from cw.merge import merge_items, blank_source_state, succeed_source_state, fail_source_state
from cw.validate import check_snapshot, check_state, schema_errors
from tests.helpers import full_registry, raw, real_doc, ROOT
from tests.test_gdacs import ENTRY as GDACS_ENTRY, doc as gdacs_doc

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
RUN_AT = "2026-09-20T12:00:00Z"
PROBE = ROOT / "tests" / "js" / "recency_probe.js"
WILDFIRE_START = "2026-05-19T01:00:00"  # 124 Tage vor dem Lauf: laengst aus jedem Zeitfenster


def old_wildfire_feed():
    """Echtes TC-Feature, ausdruecklich umetikettiert auf einen lange laufenden Waldbrand."""
    d = gdacs_doc()
    p = d["features"][0]["properties"]
    p["eventtype"] = "WF"
    p["url"]["report"] = p["url"]["report"].replace("eventtype=TC", "eventtype=WF")
    p["fromdate"] = WILDFIRE_START
    return d


def gdacs_state(feed, run_at, items=None):
    result = gdacs.parse(json.dumps(feed).encode(), NOW, GDACS_ENTRY)
    merged = merge_items(items or {}, "gdacs", GDACS_ENTRY, result, run_at)
    st = succeed_source_state(blank_source_state("gdacs", "1.0.0"), GDACS_ENTRY, result,
                              merged, run_at, "1.0.0")
    return merged, st


def build(items, states, generated_at):
    """Registry auf genau die Quellen verengen, deren Zustand geliefert wird."""
    reg = full_registry()
    ids = {st["source"] for st in states}
    reg["sources"] = [s for s in reg["sources"] if s["id"] in ids]
    domains = {s["domain"] for s in reg["sources"]}
    reg["domains"] = [d for d in reg["domains"] if d["id"] in domains]
    items_doc = {"schema_version": "6.0", "generated_at": generated_at,
                 "items": sorted(items.values(), key=lambda i: i["id"])}
    sources_doc = {"schema_version": "6.0", "generated_at": generated_at, "sources": states}
    return reg, items_doc, sources_doc


def run_probe(cases):
    if shutil.which("node") is None:
        raise unittest.SkipTest("node nicht verfuegbar - Aktualitaetsregel nicht ausgefuehrt")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump({"cases": cases}, fh)
        payload = fh.name
    try:
        out = subprocess.run(["node", str(PROBE), payload], capture_output=True, text=True,
                             timeout=60, check=True)
    finally:
        Path(payload).unlink(missing_ok=True)
    return {r["name"]: r["onStart"] for r in json.loads(out.stdout)}


class RecencyContract(unittest.TestCase):
    """Datenvertrag: Registry, interner Bestand, oeffentliche Projektion."""

    def test_every_source_declares_its_recency_basis(self):
        declared = {s["id"]: s["highlight"]["recency_basis"] for s in full_registry()["sources"]}
        self.assertEqual(declared, {"usgs": "display_time", "noaa-swpc": "display_time",
                                    "gdacs": "last_seen"})

    def test_internal_state_keeps_ingest_and_public_snapshot_exposes_only_last_seen(self):
        items, st = gdacs_state(old_wildfire_feed(), RUN_AT)
        reg, items_doc, sources_doc = build(items, [st], RUN_AT)
        self.assertEqual(check_state(items_doc, sources_doc, reg, NOW), [])

        internal = items_doc["items"][0]
        self.assertIn("ingest", internal)
        self.assertNotIn("last_seen_at", internal)  # intern bleibt intern

        snap = snapshot.build(items_doc, sources_doc, reg, "abc1234", RUN_AT,
                              include_unreleased=True)
        public = snap["items"][0]
        self.assertNotIn("ingest", public)  # kein Durchreichen des ganzen Objekts
        self.assertEqual(public["last_seen_at"], internal["ingest"]["last_seen_at"])
        self.assertEqual(public["occurred_at"], "2026-05-19T01:00:00Z")  # Beginn bleibt unberuehrt
        self.assertEqual(check_snapshot(snap, reg, NOW, preview=True), [])

    def test_schema_forbids_swapping_the_two_sighting_fields(self):
        """Kontrollfall: ohne diese Zusicherung waere die Trennung nur eine Konvention."""
        items, st = gdacs_state(old_wildfire_feed(), RUN_AT)
        reg, items_doc, sources_doc = build(items, [st], RUN_AT)
        snap = snapshot.build(items_doc, sources_doc, reg, "abc1234", RUN_AT,
                              include_unreleased=True)

        leaked = copy.deepcopy(snap)
        leaked["items"][0]["ingest"] = {"first_seen_at": RUN_AT, "last_seen_at": RUN_AT,
                                        "last_changed_at": RUN_AT}
        self.assertTrue(schema_errors(leaked))

        stripped = copy.deepcopy(snap)
        del stripped["items"][0]["last_seen_at"]
        self.assertTrue(schema_errors(stripped))

        internal_leak = copy.deepcopy(items_doc)
        internal_leak["items"][0]["last_seen_at"] = RUN_AT
        self.assertTrue(schema_errors(internal_leak))

    def test_sighting_may_not_be_newer_than_the_last_successful_fetch(self):
        items, st = gdacs_state(old_wildfire_feed(), RUN_AT)
        reg, items_doc, sources_doc = build(items, [st], RUN_AT)
        snap = snapshot.build(items_doc, sources_doc, reg, "abc1234", RUN_AT,
                              include_unreleased=True)
        self.assertEqual(check_snapshot(snap, reg, NOW, preview=True), [])

        forged = copy.deepcopy(snap)
        forged["items"][0]["last_seen_at"] = "2026-09-20T11:59:00Z"
        for source in forged["sources"]:
            if source["id"] == "gdacs":
                source["last_success_at"] = "2026-09-20T11:00:00Z"
        problems = check_snapshot(forged, reg, NOW, preview=True)
        self.assertTrue(any("nach dem letzten Abruferfolg" in x for x in problems), problems)


class RecencyRule(unittest.TestCase):
    """Die Regel selbst, in node gegen site/app.js ausgefuehrt."""

    @classmethod
    def snap_for(cls, items, states, generated_at):
        reg, items_doc, sources_doc = build(items, states, generated_at)
        return snapshot.build(items_doc, sources_doc, reg, "abc1234", generated_at,
                              include_unreleased=True)

    @staticmethod
    def pick(snap, source_id):
        item = next(i for i in snap["items"] if i["source"] == source_id)
        src = next(s for s in snap["sources"] if s["id"] == source_id)
        return item, src

    def test_old_wildfire_reported_again_today_counts_as_current(self):
        items, st = gdacs_state(old_wildfire_feed(), RUN_AT)
        snap = self.snap_for(items, [st], RUN_AT)
        item, src = self.pick(snap, "gdacs")
        self.assertEqual(item["occurred_at"], "2026-05-19T01:00:00Z")
        self.assertEqual(item["last_seen_at"], src["last_success_at"])
        result = run_probe([{"name": "wf", "item": item, "source": src, "now": RUN_AT}])
        self.assertTrue(result["wf"])

    def test_window_h_does_not_decide_for_last_seen_sources(self):
        """Punkt 4: die alte Sieben-Tage-Grenze darf nicht zusaetzlich mitentscheiden."""
        items, st = gdacs_state(old_wildfire_feed(), RUN_AT)
        snap = self.snap_for(items, [st], RUN_AT)
        item, src = self.pick(snap, "gdacs")
        cases = []
        for hours in (1, 72, 168, 720):
            variant = copy.deepcopy(src)
            variant["highlight"]["window_h"] = hours
            cases.append({"name": f"w{hours}", "item": item, "source": variant, "now": RUN_AT})
        result = run_probe(cases)
        self.assertEqual(set(result.values()), {True}, result)

    def test_event_absent_from_the_latest_successful_fetch_is_not_current(self):
        items, _ = gdacs_state(old_wildfire_feed(), RUN_AT)
        # Zwei weitere erfolgreiche Abrufe ohne dieses Ereignis.
        empty = gdacs.parse(b'{"type":"FeatureCollection","features":[]}', NOW, GDACS_ENTRY)
        later = "2026-09-22T12:00:00Z"
        items = merge_items(items, "gdacs", GDACS_ENTRY, empty, "2026-09-21T12:00:00Z")
        items = merge_items(items, "gdacs", GDACS_ENTRY, empty, later)
        st = succeed_source_state(blank_source_state("gdacs", "1.0.0"), GDACS_ENTRY, empty,
                                  items, later, "1.0.0")
        snap = self.snap_for(items, [st], later)
        item, src = self.pick(snap, "gdacs")
        self.assertEqual(item["last_seen_at"], RUN_AT)      # bleibt im Bestand,
        self.assertNotEqual(item["last_seen_at"], src["last_success_at"])  # gilt aber nicht als frisch
        result = run_probe([{"name": "gone", "item": item, "source": src, "now": later}])
        self.assertFalse(result["gone"])

    def test_failed_fetch_changes_neither_the_sighting_nor_the_verdict(self):
        items, ok_state = gdacs_state(old_wildfire_feed(), RUN_AT)
        before = self.snap_for(items, [ok_state], RUN_AT)
        item_before, src_before = self.pick(before, "gdacs")

        broken = fail_source_state(ok_state, GDACS_ENTRY, items, "2026-09-21T12:00:00Z",
                                   "network", "simulierter Ausfall")
        after = self.snap_for(items, [broken], "2026-09-21T12:00:00Z")
        item_after, src_after = self.pick(after, "gdacs")

        self.assertEqual(item_after["last_seen_at"], item_before["last_seen_at"])
        self.assertEqual(src_after["last_success_at"], src_before["last_success_at"])
        self.assertNotEqual(src_after["fetch_health"], "ok")
        result = run_probe([
            {"name": "before", "item": item_before, "source": src_before, "now": RUN_AT},
            {"name": "after", "item": item_after, "source": src_after,
             "now": "2026-09-21T12:00:00Z"},
        ])
        # Ein Ausfall ist keine Entwarnung: das Urteil bleibt unveraendert.
        self.assertEqual(result["before"], result["after"])
        self.assertTrue(result["after"])

    def test_usgs_keeps_point_in_time_logic_and_ignores_the_sighting(self):
        reg = full_registry()
        entry = next(s for s in reg["sources"] if s["id"] == "usgs")
        # Die Original-Fixture hat ein Beben vom 17.09.; für die 24-h-Regel
        # die unveränderte reale Erdbebenstruktur ausdrücklich zeitlich ableiten.
        recent = real_doc()
        recent["features"][0]["properties"]["time"] = int((NOW - dt.timedelta(hours=1)).timestamp() * 1000)
        recent["features"][0]["properties"]["updated"] = int((NOW - dt.timedelta(minutes=5)).timestamp() * 1000)
        result = usgs_adapter.parse(raw(recent), NOW, entry)
        fresh_run = "2026-09-20T12:00:00Z"
        items = merge_items({}, "usgs", entry, result, fresh_run)
        st = succeed_source_state(blank_source_state("usgs", "1.0.0"), entry, result, items,
                                  fresh_run, "1.0.0")
        snap = self.snap_for(items, [st], fresh_run)
        item, src = self.pick(snap, "usgs")
        self.assertEqual(src["highlight"]["recency_basis"], "display_time")
        self.assertEqual(item["last_seen_at"], src["last_success_at"])

        # Dasselbe Beben, 30 Tage spaeter erneut geliefert: die Sichtung ist frisch,
        # das Ereignis nicht. Fuer USGS zaehlt weiterhin ausschliesslich die Anzeigezeit.
        late = "2026-10-20T12:00:00Z"
        late_items = merge_items(items, "usgs", entry, result, late)
        late_state = succeed_source_state(st, entry, result, late_items, late, "1.0.0")
        late_snap = self.snap_for(late_items, [late_state], late)
        late_item, late_src = self.pick(late_snap, "usgs")
        self.assertEqual(late_item["last_seen_at"], late_src["last_success_at"])

        verdict = run_probe([
            {"name": "fresh", "item": item, "source": src, "now": fresh_run},
            {"name": "stale", "item": late_item, "source": late_src, "now": late},
        ])
        self.assertTrue(verdict["fresh"])
        self.assertFalse(verdict["stale"])  # frische Sichtung macht ein altes Beben nicht aktuell


if __name__ == "__main__":
    unittest.main()
