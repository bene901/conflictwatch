"""Ein Pipeline-Lauf (Spezifikation B2, Schritte 2–5).

Exit-Codes: 0 = ok, 2 = Validierung gescheitert (nichts geschrieben).
Alarm (Workflow später rot, NACH Commit und Deploy): Datei alarm_path, außerhalb des State-Ordners.
"""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path

from . import http
from .adapters import ADAPTERS
from .errors import AdapterError
from .merge import (age_source_state, blank_source_state, fail_source_state, merge_items,
                    succeed_source_state)
from .state import StateError, append_runlog, docs, load, save
from .timeutil import fmt, now_utc, parse_utc
from .validate import check_registry, check_state

ADAPTER_VERSION = "1.0.0"
INTERVAL_TOLERANCE = dt.timedelta(minutes=10)  # Cron-Verzögerungen


def _due(state: dict, entry: dict, now: dt.datetime) -> bool:
    last = state["last_attempt_at"]
    return last is None or now - parse_utc(last) >= dt.timedelta(hours=entry["min_fetch_interval_h"]) - INTERVAL_TOLERANCE


def run(registry: dict, state_dir: Path, fetch: bool = True, now: dt.datetime | None = None,
        fetcher=http.fetch, raw_dir: Path | None = None, alarm_path: Path | None = None,
        log=print, force_fetch: bool = False) -> int:
    now = now or now_utc()
    run_at = fmt(now)
    problems = check_registry(registry, ADAPTERS)
    if problems:
        log("REGISTRY UNGÜLTIG:\n  " + "\n  ".join(problems))
        return 2

    # Bestand prüfen, BEVOR irgendeine Quelle abgerufen wird.
    try:
        items_doc, sources_doc = load(state_dir)
    except StateError as exc:
        log(f"BESTAND UNGÜLTIG – Abbruch ohne Abruf und ohne Änderung: {exc}")
        return 2
    if items_doc is None:
        log("Kein Bestand vorhanden: erster Lauf.")
    else:
        problems = check_state(items_doc, sources_doc, registry, now, loaded=True)
        if problems:
            log("BESTAND UNGÜLTIG – Abbruch ohne Abruf und ohne Änderung:\n  " + "\n  ".join(problems[:30]))
            return 2
    items = {it["id"]: it for it in (items_doc or {"items": []})["items"]}
    states = {s["source"]: s for s in (sources_doc or {"sources": []})["sources"]}

    log_entry = {"run_at": run_at, "fetch": fetch, "sources": {}}
    attempted, failed, newly_down = 0, 0, []
    for entry in registry["sources"]:
        sid = entry["id"]
        prev = states.get(sid) or blank_source_state(sid, ADAPTER_VERSION)
        if not fetch or (not force_fetch and not _due(prev, entry, now)):
            states[sid] = age_source_state(prev, entry, items, run_at)
            log_entry["sources"][sid] = {"result": "skipped"}
        else:
            attempted += 1
            try:
                raw = fetcher(entry["endpoints"][0])
                if raw_dir is not None:
                    raw_dir.mkdir(parents=True, exist_ok=True)
                    (raw_dir / f"{sid}_{run_at.replace(':', '')}.json").write_bytes(raw)
                result = ADAPTERS[sid](raw, now, entry)
                candidate = merge_items(items, sid, entry, result, run_at)
                states[sid] = succeed_source_state(prev, entry, result, candidate, run_at, ADAPTER_VERSION)
                items = candidate
                log_entry["sources"][sid] = {"result": "ok", "items": result.items_in_window,
                                             "complete": result.complete}
            except AdapterError as exc:
                failed += 1
                states[sid] = fail_source_state(prev, entry, items, run_at, exc.kind, exc.detail)
                log_entry["sources"][sid] = {"result": "error", "kind": exc.kind, "detail": exc.detail}
            except Exception as exc:  # Programmfehler: nur diese Quelle gilt als gestört, Bestand bleibt
                failed += 1
                detail = f"interner Fehler: {type(exc).__name__}: {exc}"
                states[sid] = fail_source_state(prev, entry, items, run_at, "sanity", detail)
                log_entry["sources"][sid] = {"result": "error", "kind": "sanity", "detail": detail[:300]}
        if prev["fetch_health"] != "down" and states[sid]["fetch_health"] == "down":
            newly_down.append(sid)
        log_entry["sources"][sid]["fetch_health"] = states[sid]["fetch_health"]
        log_entry["sources"][sid]["data_state"] = states[sid]["data_state"]

    # Quellen, die nicht mehr in der Registry stehen, verlieren ihren Zustand (und ihre Einträge).
    reg_ids = {s["id"] for s in registry["sources"]}
    states = {k: v for k, v in states.items() if k in reg_ids}
    items = {k: v for k, v in items.items() if v["source"] in reg_ids}

    new_items_doc, new_sources_doc = docs(items, states, run_at)
    problems = check_state(new_items_doc, new_sources_doc, registry, now)
    if problems:
        log("VALIDIERUNG GESCHEITERT – nichts geschrieben:\n  " + "\n  ".join(problems[:30]))
        return 2

    save(state_dir, items, states, run_at)
    append_runlog(state_dir, log_entry, now)
    alarm = bool(newly_down) or (attempted > 0 and failed == attempted)
    if alarm and alarm_path is not None:
        alarm_path.write_text(json.dumps({"newly_down": newly_down, "all_failed": failed == attempted}) + "\n")
    log(json.dumps(log_entry, ensure_ascii=False, indent=1))
    return 0
