"""Validierung: JSON-Schema (Struktur) + Querregeln (Spezifikation A5) + Integritätsregeln
aus dem Review zu Rev. 2 (detected_between, NOAA-Status-IDs, Fehlerabrufe)."""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from .timeutil import parse_utc

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema" / "conflictwatch-v6.schema.json"
MAX_FUTURE = dt.timedelta(hours=2)
ITEM_TIME_KEYS = ("occurred_at", "published_at", "observed_at", "source_updated_at")
STATE_TIME_KEYS = ("last_attempt_at", "last_success_at", "newest_source_time", "empty_since")
# Feste Status-IDs je Quelle und ihre Skala. Gilt, sobald die Quelle in der Registry steht.
STATUS_IDS = {
    "noaa-swpc": {"noaa-swpc:scale:G": "noaa-g", "noaa-swpc:scale:S": "noaa-s", "noaa-swpc:scale:R": "noaa-r"},
}

_validator = None


def schema_validator() -> Draft202012Validator:
    global _validator
    if _validator is None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        _validator = Draft202012Validator(schema)
    return _validator


def schema_errors(doc) -> list[str]:
    return [f"schema: {'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message[:160]}"
            for e in schema_validator().iter_errors(doc)]


def _time(problems, where, value, now=None):
    if value is None:
        return None
    try:
        t = parse_utc(value)
    except (ValueError, TypeError):
        problems.append(f"{where}: ungültiger Zeitstempel {value!r}")
        return None
    if now is not None and t > now + MAX_FUTURE:
        problems.append(f"{where}: liegt mehr als 2 h in der Zukunft")
    return t


def check_registry(registry: dict, adapters: dict) -> list[str]:
    p = schema_errors(registry)
    if p:
        return p
    ids = [s["id"] for s in registry["sources"]]
    domains = {d["id"] for d in registry["domains"]}
    if len(ids) != len(set(ids)):
        p.append("registry: doppelte Quellen-ID")
    for s in registry["sources"]:
        if s["id"] not in adapters:
            p.append(f"registry: {s['id']} hat keinen Adapter")
        if s["domain"] not in domains:
            p.append(f"registry: {s['id']} unbekannte Domain {s['domain']}")
        schemes = {x["id"]: x for x in s["level_schemes"]}
        for sch_id, floor in s["highlight"]["min_levels"].items():
            if sch_id not in schemes or floor not in schemes[sch_id]["ordered_values"]:
                p.append(f"registry: {s['id']} min_levels {sch_id}={floor} nicht in Skala")
    return p


def check_items(items: list, registry: dict, now: dt.datetime, public_only: bool = False) -> list[str]:
    p, seen = [], set()
    reg = {s["id"]: s for s in registry["sources"]}
    domains = {d["id"] for d in registry["domains"]}
    for it in items:
        i = it["id"]
        if i in seen:
            p.append(f"{i}: doppelte ID")
        seen.add(i)
        for k in ITEM_TIME_KEYS:
            _time(p, f"{i}.{k}", it[k], now)
        entry = reg.get(it["source"])
        if entry is None:
            p.append(f"{i}: Quelle {it['source']} nicht in Registry")
            continue
        if public_only and not entry["public"]:
            p.append(f"{i}: Quelle nicht freigegeben, darf nicht im Snapshot stehen")
        if not i.startswith(it["source"] + ":"):
            p.append(f"{i}: ID-Präfix passt nicht zur Quelle")
        if it["kind"] not in entry["kinds"]:
            p.append(f"{i}: kind {it['kind']} für Quelle nicht erlaubt")
        if it["domain"] != entry["domain"] or it["domain"] not in domains:
            p.append(f"{i}: domain passt nicht zur Registry")
        schemes = {s["id"]: s for s in entry["level_schemes"]}
        lvl = it["level"]
        if lvl is not None:
            sch = schemes.get(lvl["scheme"])
            if sch is None or lvl["value"] not in sch["ordered_values"]:
                p.append(f"{i}: Stufe {lvl['scheme']}:{lvl['value']} nicht in Registry-Skala")
        # Feste Status-IDs (Integritätsregel 2)
        fixed = STATUS_IDS.get(it["source"])
        if fixed is not None:
            if i not in fixed:
                p.append(f"{i}: keine zulässige Status-ID dieser Quelle")
            elif lvl is not None and lvl["scheme"] != fixed[i]:
                p.append(f"{i}: Skala {lvl['scheme']} passt nicht zur ID (erwartet {fixed[i]})")
        # level_change (A3 + Integritätsregel 1)
        lc = it["level_change"]
        ing = it.get("ingest")
        if lc is not None:
            if lvl is None:
                p.append(f"{i}: level_change ohne aktuelle Stufe")
            else:
                if lc["from"]["scheme"] != lvl["scheme"]:
                    p.append(f"{i}: level_change wechselt die Skala")
                if lc["from"]["value"] == lvl["value"]:
                    p.append(f"{i}: level_change ohne Wertänderung")
            a = _time(p, f"{i}.detected_between[0]", lc["detected_between"][0])
            b = _time(p, f"{i}.detected_between[1]", lc["detected_between"][1])
            if a and b and not a < b:
                p.append(f"{i}: detected_between nicht aufsteigend")
            if ing and a and b:
                first, last = parse_utc(ing["first_seen_at"]), parse_utc(ing["last_seen_at"])
                if not (first <= a and b <= last):
                    p.append(f"{i}: detected_between liegt außerhalb der gespeicherten Beobachtungen")
        if ing:
            f = _time(p, f"{i}.first_seen_at", ing["first_seen_at"], now)
            l = _time(p, f"{i}.last_seen_at", ing["last_seen_at"], now)
            c = _time(p, f"{i}.last_changed_at", ing["last_changed_at"], now)
            if f and l and c and not (f <= c <= l):
                p.append(f"{i}: ingest-Zeiten nicht geordnet")
    for src, fixed in STATUS_IDS.items():
        if src in reg:
            present = {it["id"] for it in items if it["source"] == src}
            if present and present != set(fixed):
                p.append(f"{src}: Status-IDs unvollständig oder überzählig")
    return p


def check_state(items_doc: dict, sources_doc: dict, registry: dict, now: dt.datetime,
                loaded: bool = False) -> list[str]:
    """loaded=True: Prüfung des gespeicherten Bestands VOR einem Lauf. Erlaubt Registry-Änderungen
    (neue oder entfernte Quellen), prüft sonst dieselben Regeln wie nach dem Lauf."""
    p = schema_errors(items_doc) + schema_errors(sources_doc)
    if p:
        return p
    reg_ids_all = {s["id"] for s in registry["sources"]}
    items_to_check = [it for it in items_doc["items"] if it["source"] in reg_ids_all] if loaded else items_doc["items"]
    p += check_items(items_to_check, registry, now)
    reg_ids = {s["id"] for s in registry["sources"]}
    st_ids = [s["source"] for s in sources_doc["sources"]]
    if len(st_ids) != len(set(st_ids)):
        p.append("sources: doppelter Quellenzustand")
    if not loaded and set(st_ids) != reg_ids:
        p.append("sources: Quellenzustände passen nicht zur Registry")
    for s in sources_doc["sources"]:
        for k in STATE_TIME_KEYS:
            _time(p, f"sources.{s['source']}.{k}", s[k], now)
        if s["last_error"]:
            _time(p, f"sources.{s['source']}.last_error.at", s["last_error"]["at"], now)
        if s["fetch_health"] == "ok" and s["last_success_at"] is None:
            p.append(f"sources.{s['source']}: ok ohne erfolgreichen Abruf")
        if s["data_state"] == "empty" and s["last_fetch_complete"] is not True:
            p.append(f"sources.{s['source']}: empty ohne vollständigen Abruf")
    for k in ("generated_at",):
        _time(p, f"items.{k}", items_doc[k], now)
        _time(p, f"sources.{k}", sources_doc[k], now)
    return p


def check_snapshot(snap: dict, registry: dict, now: dt.datetime, preview: bool = False) -> list[str]:
    p = schema_errors(snap)
    if p:
        return p
    p += check_items(snap["items"], registry, now, public_only=not preview)
    reg = {s["id"]: s for s in registry["sources"]}
    for s in snap["sources"]:
        if s["id"] not in reg:
            p.append(f"snapshot: Quelle {s['id']} nicht in Registry")
        elif not preview and not reg[s["id"]]["public"]:
            p.append(f"snapshot: Quelle {s['id']} nicht freigegeben")
    listed = {s["id"] for s in snap["sources"]}
    for it in snap["items"]:
        if it["source"] not in listed:
            p.append(f"snapshot: {it['id']} ohne zugehörige Quelle")
    _time(p, "snapshot.generated_at", snap["generated_at"], now)
    return p
