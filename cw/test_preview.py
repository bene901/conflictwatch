"""Dedicated, explicitly scoped public TEST snapshot, never the regular release feed.

Only USGS and NOAA are allowed. Do not use --include-unreleased to publish
an unrestricted preview of future registry entries.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from . import registry as registry_mod, snapshot, state
from .state import StateError
from .timeutil import fmt, now_utc
from .validate import check_snapshot, check_state

TEST_SOURCE_IDS = frozenset({"usgs", "noaa-swpc"})


def build_test_snapshot(items_doc, sources_doc, registry, revision, now):
    entries = {s["id"]: s for s in registry["sources"]}
    if not TEST_SOURCE_IDS.issubset(entries):
        raise ValueError("Testquelle USGS oder NOAA fehlt in der Registry")
    # Dedicated preview is intentionally limited to still-unreleased entries.
    if any(entries[sid]["public"] is not False for sid in TEST_SOURCE_IDS):
        raise ValueError("Testansicht deaktivieren/anpassen, bevor eine Testquelle regulär freigegeben wird")
    # Build from a narrowed registry: future private providers cannot accidentally
    # enter the public preview, even transiently, when they join the production registry.
    scoped_registry = {**registry, "sources": [
        entry for entry in registry["sources"] if entry["id"] in TEST_SOURCE_IDS
    ]}
    full = snapshot.build(items_doc, sources_doc, scoped_registry, revision, fmt(now),
                          include_unreleased=True)
    if {s["id"] for s in full["sources"]} != TEST_SOURCE_IDS:
        raise ValueError("Testansicht enthält nicht genau USGS und NOAA")
    errors = check_snapshot(full, registry, now, preview=True)
    if errors:
        raise ValueError("Test-Snapshot ungültig: " + "; ".join(errors[:10]))
    return full


def main(argv=None):
    ap = argparse.ArgumentParser(description="Erzeuge streng begrenzten öffentlichen Test-Snapshot")
    ap.add_argument("--registry", default="registry.json")
    ap.add_argument("--state", required=True)
    ap.add_argument("--revision", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    registry = registry_mod.load(args.registry)
    now = now_utc()
    entries = {src["id"]: src for src in registry["sources"]}
    released = sorted(sid for sid in TEST_SOURCE_IDS
                      if sid in entries and entries[sid]["public"] is not False)
    if released:
        # Die separate Testansicht existierte nur fuer NICHT freigegebene Quellen.
        # Sind sie regulaer freigegeben, gibt es nichts mehr gesondert vorzuschauen -
        # das ist kein Fehler und darf den Lauf nicht abbrechen.
        print("TEST-SNAPSHOT ENTFÄLLT: regulär freigegeben – " + ", ".join(released))
        return 0
    try:
        items_doc, sources_doc = state.load(Path(args.state))
        if items_doc is None or sources_doc is None:
            raise ValueError("Keine gespeicherten Quelldaten")
        errors = check_state(items_doc, sources_doc, registry, now)
        if errors:
            raise ValueError("Ungültiger interner Bestand: " + "; ".join(errors[:10]))
        data = build_test_snapshot(items_doc, sources_doc, registry, args.revision, now)
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n",
                        encoding="utf-8")
        print(f"Test-Snapshot: {len(data['items'])} Einträge, {len(data['sources'])} Quellen -> {path}")
        return 0
    except (StateError, ValueError, KeyError) as exc:
        print(f"TEST-SNAPSHOT NICHT VERÖFFENTLICHT: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
