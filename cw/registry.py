from __future__ import annotations
import json
from pathlib import Path


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sources_by_id(registry: dict) -> dict:
    return {s["id"]: s for s in registry["sources"]}


def scheme(entry: dict, scheme_id: str) -> dict | None:
    return next((s for s in entry["level_schemes"] if s["id"] == scheme_id), None)


def level_obj(entry: dict, scheme_id: str, value: str) -> dict:
    """Stufenobjekt aus der Registry. Unbekannter Wert -> KeyError (Aufrufer macht daraus schema-Fehler)."""
    sch = scheme(entry, scheme_id)
    if sch is None or value not in sch["ordered_values"]:
        raise KeyError(f"{scheme_id}:{value}")
    return {"scheme": scheme_id, "value": value, "label": sch["labels"].get(value, value)}
