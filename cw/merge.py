"""Zusammenführung (Spezifikation A3, A4, A7).

Wird für eine Quelle NUR nach einem erfolgreichen Abruf aufgerufen. Ein Fehler ruft
ausschließlich fail_source_state() auf und fasst den Bestand nicht an.
"""
from __future__ import annotations
import copy
import datetime as dt

from .timeutil import fmt, parse_utc

MATERIAL_FIELDS = ("title", "url", "occurred_at", "published_at", "observed_at", "level",
                   "data_status", "source_status_raw", "location", "metrics", "ongoing")
TIME_FIELDS = ("occurred_at", "published_at", "observed_at", "source_updated_at")


def display_time(item: dict) -> dt.datetime:
    key = {"event": "occurred_at", "report": "published_at", "status": "observed_at"}[item["kind"]]
    return parse_utc(item[key])


def next_level_change(old: dict, new_level, run_at: str):
    """Tabelle A3. old = gespeicherter Eintrag, new_level = Stufe aus dem aktuellen Abruf."""
    prev = old["level"]
    if new_level is None or prev is None:
        return None  # X -> null  und  null -> X
    if prev["value"] == new_level["value"] and prev["scheme"] == new_level["scheme"]:
        return copy.deepcopy(old["level_change"])  # X -> X
    return {  # X -> Y: beide Stufen tatsächlich beobachtet
        "from": copy.deepcopy(prev),
        "detected_between": [old["ingest"]["last_seen_at"], run_at],
        "source_changed_at": None,
    }


def merge_items(items: dict, source_id: str, entry: dict, result, run_at: str) -> dict:
    """Gibt einen neuen Bestand zurück (items: id -> Item). Eingabe bleibt unverändert."""
    out = copy.deepcopy(items)
    returned = set()
    for draft in result.items:
        candidates = [draft["id"]] + list(result.aliases.get(draft["id"], []))
        existing_id = next((c for c in candidates if c in out and out[c]["source"] == source_id), None)
        if existing_id is None:
            item = copy.deepcopy(draft)
            item["level_change"] = None
            item["ingest"] = {"first_seen_at": run_at, "last_seen_at": run_at, "last_changed_at": run_at}
            out[item["id"]] = item
            returned.add(item["id"])
            continue
        old = out[existing_id]
        item = copy.deepcopy(draft)
        item["id"] = existing_id  # Identität ist unveränderlich, auch wenn die Quelle die bevorzugte ID wechselt.
        item["level_change"] = next_level_change(old, draft["level"], run_at)
        changed = any(old.get(k) != item.get(k) for k in MATERIAL_FIELDS)
        item["ingest"] = {
            "first_seen_at": old["ingest"]["first_seen_at"],
            "last_seen_at": run_at,
            "last_changed_at": run_at if changed else old["ingest"]["last_changed_at"],
        }
        out[existing_id] = item
        returned.add(existing_id)

    if result.complete:
        cutoff = parse_utc(run_at) - dt.timedelta(days=entry["retention_days"])
        for iid in [i for i, it in out.items() if it["source"] == source_id]:
            it = out[iid]
            if it["kind"] != "status" and iid not in returned and display_time(it) < cutoff:
                del out[iid]
    else:
        # A missing item in an incomplete feed is NOT evidence of withdrawal.
        # Expiry is a technical bound on active storage, measured since last
        # successful sighting, never from event time or failed/skipped fetches.
        expiry = entry.get("unseen_expiry_days")
        if expiry is not None:
            cutoff = parse_utc(run_at) - dt.timedelta(days=expiry)
            for iid in [i for i, it in out.items() if it["source"] == source_id]:
                it = out[iid]
                if (it["kind"] != "status" and iid not in returned
                        and parse_utc(it["ingest"]["last_seen_at"]) < cutoff):
                    del out[iid]
    return out


def newest_source_time(items: dict, source_id: str):
    times = [parse_utc(it[k]) for it in items.values() if it["source"] == source_id
             for k in TIME_FIELDS if it.get(k)]
    return fmt(max(times)) if times else None


def blank_source_state(source_id: str, adapter_version: str) -> dict:
    return {
        "source": source_id, "adapter_version": adapter_version,
        "fetch_health": "down", "data_state": "unknown",
        "last_attempt_at": None, "last_success_at": None, "last_fetch_complete": None,
        "newest_source_time": None, "consecutive_failures": 0, "last_error": None,
        "items_in_window": None, "empty_since": None,
    }


def _status_age_state(items: dict, source_id: str, entry: dict, run_at: str, current: str) -> str:
    """Status-Quellen: Messwert älter als max_data_age_h -> old (unabhängig vom Abruferfolg)."""
    if "status" not in entry["kinds"] or entry["max_data_age_h"] is None:
        return current
    obs = [parse_utc(it["observed_at"]) for it in items.values()
           if it["source"] == source_id and it["kind"] == "status"]
    if not obs:
        return current
    too_old = parse_utc(run_at) - min(obs) > dt.timedelta(hours=entry["max_data_age_h"])
    if too_old:
        return "old"
    return "fresh" if current == "old" else current


def succeed_source_state(prev: dict, entry: dict, result, items: dict, run_at: str, adapter_version: str) -> dict:
    st = copy.deepcopy(prev)
    st.update(adapter_version=adapter_version, last_attempt_at=run_at, last_success_at=run_at,
              consecutive_failures=0, last_error=None, last_fetch_complete=result.complete,
              items_in_window=result.items_in_window, fetch_health="ok")
    if result.items_in_window > 0:
        st["data_state"], st["empty_since"] = "fresh", None
    elif result.complete:
        st["data_state"] = "empty"
        st["empty_since"] = prev["empty_since"] or run_at
        if entry["max_empty_h"] is not None and \
                parse_utc(run_at) - parse_utc(st["empty_since"]) > dt.timedelta(hours=entry["max_empty_h"]):
            st["fetch_health"] = "degraded"
            st["last_error"] = {"at": run_at, "kind": "sanity",
                                "detail": f"seit {st['empty_since']} keine Einträge (verdächtig)"}
    # unvollständig und leer: data_state bleibt, wie er war
    st["data_state"] = _status_age_state(items, entry["id"], entry, run_at, st["data_state"])
    st["newest_source_time"] = newest_source_time(items, entry["id"])
    return st


def fail_source_state(prev: dict, entry: dict, items: dict, run_at: str, kind: str, detail: str) -> dict:
    """Fehlschlag: Bestand bleibt unberührt; nur Fehlerfelder und Gesundheit ändern sich."""
    st = copy.deepcopy(prev)
    st["last_attempt_at"] = run_at
    st["consecutive_failures"] = prev["consecutive_failures"] + 1
    st["last_error"] = {"at": run_at, "kind": kind, "detail": detail[:300]}
    last_ok = prev["last_success_at"]
    within = last_ok is not None and \
        parse_utc(run_at) - parse_utc(last_ok) <= dt.timedelta(hours=entry["max_fetch_gap_h"])
    st["fetch_health"] = "degraded" if within else "down"
    st["data_state"] = _status_age_state(items, entry["id"], entry, run_at, prev["data_state"])
    return st


def age_source_state(prev: dict, entry: dict, items: dict, run_at: str) -> dict:
    """Kein Abruf in diesem Lauf (Intervall nicht erreicht oder Push-Lauf): nur Alterung prüfen."""
    st = copy.deepcopy(prev)
    last_ok = prev["last_success_at"]
    if last_ok is None or parse_utc(run_at) - parse_utc(last_ok) > dt.timedelta(hours=entry["max_fetch_gap_h"]):
        st["fetch_health"] = "down"
    st["data_state"] = _status_age_state(items, entry["id"], entry, run_at, prev["data_state"])
    return st
