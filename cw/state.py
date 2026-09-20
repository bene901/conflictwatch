"""Laden und Schreiben des internen Bestands (Branch data-state, Ordner state/)."""
from __future__ import annotations
import datetime as dt
import json
import os
from pathlib import Path

from . import SCHEMA_VERSION
from .timeutil import parse_utc

ITEMS, SOURCES, RUNLOG = "items.json", "sources.json", "runlog.jsonl"
RUNLOG_DAYS = 14


class StateError(Exception):
    """Vorhandener Bestand ist unvollständig oder nicht lesbar. Nie durch leeren Bestand ersetzen."""


def load(state_dir: Path):
    """(None, None) nur beim ersten Lauf (beide Dateien fehlen). Genau eine Datei -> StateError."""
    items_p, src_p = state_dir / ITEMS, state_dir / SOURCES
    if items_p.exists() != src_p.exists():
        present = ITEMS if items_p.exists() else SOURCES
        raise StateError(f"Bestand unvollständig: nur {present} vorhanden")
    if not items_p.exists():
        return None, None
    try:
        items = json.loads(items_p.read_text(encoding="utf-8"))
        sources = json.loads(src_p.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StateError(f"Bestand nicht lesbar: {exc}") from None
    return items, sources


def dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def _atomic_write(path: Path, text: str):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def save(state_dir: Path, items: dict, sources: dict, generated_at: str):
    state_dir.mkdir(parents=True, exist_ok=True)
    items_doc = {"schema_version": SCHEMA_VERSION, "generated_at": generated_at,
                 "items": [items[k] for k in sorted(items)]}
    src_doc = {"schema_version": SCHEMA_VERSION, "generated_at": generated_at,
               "sources": [sources[k] for k in sorted(sources)]}
    _atomic_write(state_dir / ITEMS, dump(items_doc))
    _atomic_write(state_dir / SOURCES, dump(src_doc))
    return items_doc, src_doc


def docs(items: dict, sources: dict, generated_at: str):
    return ({"schema_version": SCHEMA_VERSION, "generated_at": generated_at,
             "items": [items[k] for k in sorted(items)]},
            {"schema_version": SCHEMA_VERSION, "generated_at": generated_at,
             "sources": [sources[k] for k in sorted(sources)]})


def append_runlog(state_dir: Path, entry: dict, now: dt.datetime):
    path = state_dir / RUNLOG
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    keep = []
    for line in lines:
        try:
            if now - parse_utc(json.loads(line)["run_at"]) <= dt.timedelta(days=RUNLOG_DAYS):
                keep.append(line)
        except (ValueError, KeyError, TypeError):
            continue
    keep.append(json.dumps(entry, ensure_ascii=False, sort_keys=True))
    _atomic_write(path, "\n".join(keep) + "\n")
