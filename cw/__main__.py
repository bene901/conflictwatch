"""CLI: python -m cw {run,snapshot,validate} – siehe docs/RUNBOOK.md."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from . import pipeline, registry as reg_mod, snapshot, state
from .state import StateError
from .timeutil import fmt, now_utc, parse_utc
from .validate import check_snapshot, check_state


def _fixture_fetcher(pairs, registry):
    """Offline-Lauf: ordnet Fixture-Dateien den Registry-Endpunkten zu (quelle=pfad)."""
    endpoints = {s["endpoints"][0]: s["id"] for s in registry["sources"]}
    table = dict(pair.split("=", 1) for pair in pairs)

    def fetch(url):
        sid = endpoints[url]
        if sid not in table:
            from .errors import AdapterError
            raise AdapterError("network", f"keine Fixture für {sid}")
        return Path(table[sid]).read_bytes()
    return fetch


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cw")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="Quellen abrufen, zusammenführen, validieren, Bestand schreiben")
    r.add_argument("--registry", default="registry.json")
    r.add_argument("--state", required=True)
    r.add_argument("--no-fetch", action="store_true", help="nur Alterung prüfen (Push-Lauf)")
    r.add_argument("--force-fetch", action="store_true", help="nur bei ausdrücklich angefordertem Veröffentlichungs-Abruf: Intervall einmal übergehen")
    r.add_argument("--raw-dir", help="Rohantworten hier ablegen (für Fixtures)")
    r.add_argument("--alarm-file", help="wird bei Alarm geschrieben")
    r.add_argument("--fixture", action="append", default=[], help="offline: quelle=pfad statt HTTP")
    r.add_argument("--now", help="nur Darstellungstest: Laufzeit als UTC-Zeitstempel statt Systemzeit")
    s = sub.add_parser("snapshot", help="öffentliche Projektion erzeugen und validieren")
    s.add_argument("--registry", default="registry.json")
    s.add_argument("--state", required=True)
    s.add_argument("--revision", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--now", help="nur Darstellungstest: Erzeugungszeit als UTC-Zeitstempel")
    s.add_argument("--include-unreleased", action="store_true",
                   help="NUR für Vorschau-Artefakt/lokal: auch nicht freigegebene Quellen")
    v = sub.add_parser("validate", help="gespeicherten Bestand prüfen")
    v.add_argument("--registry", default="registry.json")
    v.add_argument("--state", required=True)
    a = ap.parse_args(argv)
    registry = reg_mod.load(a.registry)
    state_dir = Path(a.state)

    if a.cmd == "run":
        kwargs = {}
        if a.fixture:
            kwargs["fetcher"] = _fixture_fetcher(a.fixture, registry)
        if a.no_fetch and a.force_fetch:
            ap.error("--no-fetch und --force-fetch schließen sich aus")
        return pipeline.run(registry, state_dir, fetch=not a.no_fetch,
                            force_fetch=a.force_fetch,
                            now=parse_utc(a.now) if a.now else None,
                            raw_dir=Path(a.raw_dir) if a.raw_dir else None,
                            alarm_path=Path(a.alarm_file) if a.alarm_file else None, **kwargs)

    try:
        items_doc, sources_doc = state.load(state_dir)
    except StateError as exc:
        print(f"Bestand ungültig: {exc}", file=sys.stderr)
        return 2
    now = parse_utc(a.now) if getattr(a, "now", None) else now_utc()
    if items_doc is None or sources_doc is None:
        print("Kein Bestand vorhanden – zuerst 'run' ausführen.", file=sys.stderr)
        return 2
    if a.cmd == "validate":
        problems = check_state(items_doc, sources_doc, registry, now)
        print("\n".join(problems) if problems else f"OK: {len(items_doc['items'])} Einträge")
        return 2 if problems else 0

    snap = snapshot.build(items_doc, sources_doc, registry, a.revision, fmt(now), a.include_unreleased)
    problems = check_snapshot(snap, registry, now, preview=a.include_unreleased)
    if problems:
        print("SNAPSHOT UNGÜLTIG:\n  " + "\n  ".join(problems[:30]), file=sys.stderr)
        return 2
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Snapshot: {len(snap['items'])} Einträge, {len(snap['sources'])} Quellen -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
