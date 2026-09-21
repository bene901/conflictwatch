import copy
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cw import pipeline, snapshot, state
from cw.errors import AdapterError
from cw.validate import check_items, check_snapshot, check_state
from tests.helpers import ROOT, at, raw, real_doc, registry, full_registry


def run_once(state_dir, fetcher, when, alarm=None, reg=None):
    logs = []
    code = pipeline.run(reg or registry(), state_dir, fetch=True, now=when, fetcher=fetcher,
                        alarm_path=alarm, log=logs.append)
    return code, logs


def ok_fetcher(doc=None):
    data = raw(doc or real_doc())
    return lambda url: data


def failing(kind="http"):
    def f(url):
        raise AdapterError(kind, "simuliert")
    return f


class Validator(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        run_once(self.d, ok_fetcher(), at())
        self.items, self.sources = state.load(self.d)

    def test_valid_state(self):
        self.assertEqual(check_state(self.items, self.sources, registry(), at()), [])

    def test_t12_impossible_dates_rejected(self):
        for bad in ("2026-02-30T10:00:00Z", "2026-09-19T25:00:00Z", "2026-19-45T99:99:99Z"):
            items = copy.deepcopy(self.items)
            items["items"][0]["occurred_at"] = bad
            self.assertTrue(check_state(items, self.sources, registry(), at()), bad)

    def test_detected_between_outside_observations_rejected(self):
        items = copy.deepcopy(self.items)
        it = items["items"][0]
        it["level"] = {"scheme": "usgs-pager", "value": "yellow", "label": "PAGER Gelb"}
        it["level_change"] = {"from": {"scheme": "usgs-pager", "value": "green", "label": "PAGER Grün"},
                              "detected_between": ["2026-09-01T00:00:00Z", it["ingest"]["last_seen_at"]],
                              "source_changed_at": None}
        probs = check_state(items, self.sources, registry(), at())
        self.assertTrue(any("außerhalb der gespeicherten Beobachtungen" in p for p in probs))

    def test_noaa_status_ids_bound_to_scale(self):
        reg = registry()
        scheme = lambda sid, letter: {"id": sid, "ordered_values": [str(i) for i in range(6)],
                                      "labels": {str(i): f"{letter}{i}" for i in range(6)},
                                      "reference_url": "https://www.swpc.noaa.gov/"}
        reg["domains"].append({"id": "spaceweather", "label": "Weltraumwetter"})
        reg["sources"].append(dict(reg["sources"][0], id="noaa-swpc", domain="spaceweather", kinds=["status"],
                                   level_schemes=[scheme("noaa-g", "G"), scheme("noaa-s", "S"), scheme("noaa-r", "R")]))

        def status(sid_letter, scheme_id):
            return {"id": f"noaa-swpc:scale:{sid_letter}", "kind": "status", "domain": "spaceweather",
                    "source": "noaa-swpc", "provenance": "original", "original_publisher": None,
                    "title": "x" * 5, "lang": "de", "url": "https://www.swpc.noaa.gov/",
                    "occurred_at": None, "published_at": None, "observed_at": "2026-09-19T13:00:00Z",
                    "source_updated_at": None, "ongoing": None, "data_status": "unknown",
                    "source_status_raw": None, "level": {"scheme": scheme_id, "value": "1", "label": "1"},
                    "level_change": None, "location": {"precision": "global", "name": None, "countries": [],
                                                        "lat": None, "lon": None}, "metrics": {}}
        good = [status("G", "noaa-g"), status("S", "noaa-s"), status("R", "noaa-r")]
        self.assertEqual(check_items(good, reg, at()), [])
        swapped = [status("G", "noaa-s"), status("S", "noaa-g"), status("R", "noaa-r")]
        self.assertTrue(check_items(swapped, reg, at()))
        wrong_id = [status("X", "noaa-g"), status("S", "noaa-s"), status("R", "noaa-r")]
        self.assertTrue(check_items(wrong_id, reg, at()))


class Pipeline(unittest.TestCase):
    def test_p1_all_sources_fail_keeps_state_and_raises_alarm(self):
        d = Path(tempfile.mkdtemp())
        run_once(d, ok_fetcher(), at())
        before, _ = state.load(d)
        alarm = d.parent / (d.name + ".alarm")
        code, _ = run_once(d, failing("network"), at(hours=1), alarm=alarm)
        after, sources = state.load(d)
        self.assertEqual(code, 0)
        self.assertEqual(before["items"], after["items"])
        self.assertEqual(sources["sources"][0]["fetch_health"], "degraded")
        self.assertTrue(alarm.exists())

    def test_first_failure_of_new_public_source_raises_alarm(self):
        d = Path(tempfile.mkdtemp())
        run_once(d, ok_fetcher(), at())

        reg = full_registry()
        reg["sources"] = [s for s in reg["sources"]
                          if s["id"] in {"usgs", "gdacs-volcano"}]
        reg["domains"] = [x for x in reg["domains"] if x["id"] == "disaster"]

        def mixed_fetch(url):
            if url.endswith("4.5_day.geojson"):
                return raw(real_doc())
            raise AdapterError("network", "simulierter Erstausfall neuer Quelle")

        alarm = d.parent / (d.name + ".new-source.alarm")
        code, _ = run_once(d, mixed_fetch, at(hours=1), alarm=alarm, reg=reg)
        self.assertEqual(code, 0)
        self.assertTrue(alarm.exists())
        payload = json.loads(alarm.read_text())
        self.assertIn("gdacs-volcano", payload["newly_down"])
        self.assertFalse(payload["all_failed"])

    def test_p2_validation_failure_writes_nothing(self):
        d = Path(tempfile.mkdtemp())
        run_once(d, ok_fetcher(), at())
        before = {p.name: p.read_bytes() for p in d.iterdir()}
        real_merge = pipeline.merge_items

        def corrupt(*a, **k):
            out = real_merge(*a, **k)
            next(iter(out.values()))["ingest"]["first_seen_at"] = "2026-02-30T10:00:00Z"
            return out
        with mock.patch("cw.pipeline.merge_items", side_effect=corrupt):
            code, logs = run_once(d, ok_fetcher(), at(hours=1))
        self.assertEqual(code, 2)
        self.assertEqual({p.name: p.read_bytes() for p in d.iterdir()}, before)

    def test_internal_error_isolated_to_source(self):
        d = Path(tempfile.mkdtemp())
        run_once(d, ok_fetcher(), at())
        items_before, _ = state.load(d)
        with mock.patch("cw.pipeline.merge_items", side_effect=ZeroDivisionError("bug")):
            code, _ = run_once(d, ok_fetcher(), at(hours=1))
        items_after, sources = state.load(d)
        self.assertEqual(code, 0)
        self.assertEqual(items_before["items"], items_after["items"])
        st = sources["sources"][0]
        self.assertEqual((st["fetch_health"], st["last_error"]["kind"]), ("degraded", "sanity"))

    def test_first_run_without_fetch(self):
        d = Path(tempfile.mkdtemp())
        code = pipeline.run(registry(), d, fetch=False, now=at(), log=lambda *_: None)
        _, sources = state.load(d)
        self.assertEqual(code, 0)
        self.assertEqual((sources["sources"][0]["fetch_health"], sources["sources"][0]["data_state"]),
                         ("down", "unknown"))


class StateLoading(unittest.TestCase):
    """P0-2: Bestand wird vor jedem Abruf geprüft; ein beschädigter Bestand wird nie neu angelegt."""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        run_once(self.d, ok_fetcher(), at())
        self.calls = []

    def fetcher(self, url):
        self.calls.append(url)
        return raw(real_doc())

    def assertAbortsUntouched(self):
        before = {p.name: p.read_bytes() for p in self.d.iterdir()}
        code, logs = run_once(self.d, self.fetcher, at(hours=1))
        self.assertEqual(code, 2)
        self.assertEqual(self.calls, [])  # kein externer Abruf
        self.assertEqual({p.name: p.read_bytes() for p in self.d.iterdir()}, before)

    def test_only_items_file(self):
        (self.d / "sources.json").unlink()
        self.assertAbortsUntouched()

    def test_only_sources_file(self):
        (self.d / "items.json").unlink()
        self.assertAbortsUntouched()

    def test_unreadable_json(self):
        (self.d / "items.json").write_text("{ kaputt")
        self.assertAbortsUntouched()

    def test_sources_schema_violation(self):
        doc = json.loads((self.d / "sources.json").read_text())
        doc["sources"][0]["fetch_health"] = "fine"
        (self.d / "sources.json").write_text(json.dumps(doc))
        self.assertAbortsUntouched()

    def test_impossible_date_in_stored_items(self):
        doc = json.loads((self.d / "items.json").read_text())
        doc["items"][0]["occurred_at"] = "2026-02-30T10:00:00Z"
        (self.d / "items.json").write_text(json.dumps(doc))
        self.assertAbortsUntouched()

    def test_first_run_both_missing_is_allowed(self):
        d = Path(tempfile.mkdtemp())
        code, _ = run_once(d, self.fetcher, at())
        self.assertEqual(code, 0)
        self.assertEqual(len(self.calls), 1)

    def test_removed_registry_source_is_not_corruption(self):
        reg = registry()
        reg["sources"] = []
        code, _ = run_once(self.d, self.fetcher, at(hours=1), reg=reg)
        self.assertEqual(code, 0)


class LiveTestA(unittest.TestCase):
    """P1-4 A: Eine gültige LEERE Antwort besteht den technischen Live-Test."""

    def test_valid_empty_response(self):
        doc = real_doc()
        doc["features"], doc["metadata"]["count"] = [], 0
        d = Path(tempfile.mkdtemp())
        code, _ = run_once(d, ok_fetcher(doc), at())
        items, sources = state.load(d)
        st = sources["sources"][0]
        self.assertEqual(code, 0)
        self.assertEqual((st["fetch_health"], st["data_state"], st["items_in_window"]), ("ok", "empty", 0))
        snap = snapshot.build(items, sources, registry(), "abc1234", "2026-09-19T13:18:00Z", include_unreleased=True)
        self.assertEqual(check_snapshot(snap, registry(), at(), preview=True), [])

    def test_count_mismatch_keeps_state_and_last_success(self):
        d = Path(tempfile.mkdtemp())
        run_once(d, ok_fetcher(), at())
        items_before, src_before = state.load(d)
        bad = real_doc()
        bad["metadata"]["count"] = 5
        code, _ = run_once(d, ok_fetcher(bad), at(hours=1))
        items_after, src_after = state.load(d)
        self.assertEqual(code, 0)
        self.assertEqual(items_before["items"], items_after["items"])
        st = src_after["sources"][0]
        self.assertEqual(st["last_success_at"], src_before["sources"][0]["last_success_at"])
        self.assertEqual((st["fetch_health"], st["last_error"]["kind"]), ("degraded", "sanity"))


class P4Snapshot(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        run_once(self.d, ok_fetcher(), at())
        self.items, self.sources = state.load(self.d)

    @staticmethod
    def blocked_registry():
        """Ausdruecklich gesperrte Quelle. Diese Zusicherung darf nicht davon abhaengen,
        was in registry.json gerade freigegeben ist."""
        reg = registry()
        reg["sources"][0]["public"] = False
        return reg

    def test_unreleased_source_not_published(self):
        reg = self.blocked_registry()
        snap = snapshot.build(self.items, self.sources, reg, "abc1234", "2026-09-19T13:18:00Z")
        self.assertEqual((snap["sources"], snap["items"]), ([], []))
        self.assertEqual(check_snapshot(snap, reg, at()), [])

    def test_released_source_published_without_ingest(self):
        reg = registry()
        reg["sources"][0]["public"] = True
        snap = snapshot.build(self.items, self.sources, reg, "abc1234", "2026-09-19T13:18:00Z")
        self.assertEqual(len(snap["items"]), 1)
        self.assertNotIn("ingest", snap["items"][0])
        self.assertEqual(snap["state_revision"], "abc1234")
        self.assertEqual(check_snapshot(snap, reg, at()), [])

    def test_preview_must_not_pass_as_production(self):
        reg = self.blocked_registry()
        snap = snapshot.build(self.items, self.sources, reg, "abc1234", "2026-09-19T13:18:00Z",
                              include_unreleased=True)
        self.assertEqual(check_snapshot(snap, reg, at(), preview=True), [])
        self.assertTrue(check_snapshot(snap, reg, at(), preview=False))


class SiteStatic(unittest.TestCase):
    site = ROOT / "site"

    def test_f2_no_html_injection_sinks(self):
        js = (self.site / "app.js").read_text()
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
            self.assertNotIn(sink, js)

    def test_f2_exactly_one_data_request(self):
        js = (self.site / "app.js").read_text()
        self.assertEqual(len(re.findall(r"\bfetch\(", js)), 1)
        self.assertIn("data/snapshot.json", js)
        self.assertIn('cache: "no-store"', js)
        self.assertIn('headers.get("Date")', js)  # Serverzeit für die Altersprüfung

    def test_no_external_resources(self):
        for name in ("index.html", "style.css", "app.js"):
            text = (self.site / name).read_text()
            refs = re.findall(r"""(?:src|href)\s*=\s*["'](https?:)?//""", text) + re.findall(r"url\(\s*['\"]?https?:", text)
            self.assertEqual(refs, [], name)
        self.assertIn("Content-Security-Policy", (self.site / "index.html").read_text())

    def test_f1_titles_set_as_text(self):
        js = (self.site / "app.js").read_text()
        self.assertIn('el("span", "title", it.title)', js)
        self.assertIn("textContent", js)


class WorkflowLiveFetch(unittest.TestCase):
    """Regression: main pushes must not silently skip the first real USGS fetch."""

    def test_pipeline_workflow_uses_due_based_fetch_for_every_trigger(self):
        workflow = (ROOT / ".github" / "workflows" / "pipeline.yml").read_text()
        self.assertIn("schedule:", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("branches: [main]", workflow)
        self.assertIn("python -m cw run --state state-repo/state --raw-dir raw --alarm-file alarm.json", workflow)
        self.assertNotIn("--no-fetch", workflow)
        self.assertNotIn("github.event_name != 'push'", workflow)


if __name__ == "__main__":
    unittest.main()
