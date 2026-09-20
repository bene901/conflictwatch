"""Öffentliche Projektion: genau eine Datei data/snapshot.json (Spezifikation A8)."""
from __future__ import annotations

from . import SCHEMA_VERSION
from .merge import display_time

PUBLIC_REGISTRY_FIELDS = ("id", "name", "domain", "attribution", "level_schemes", "highlight", "coverage_note")
PUBLIC_STATE_FIELDS = ("fetch_health", "data_state", "last_attempt_at", "last_success_at",
                       "last_fetch_complete", "newest_source_time")


def build(items_doc: dict, sources_doc: dict, registry: dict, revision: str, generated_at: str,
          include_unreleased: bool = False) -> dict:
    states = {s["source"]: s for s in sources_doc["sources"]}
    released = [s for s in registry["sources"] if include_unreleased or s["public"]]
    released_ids = {s["id"] for s in released}
    sources = []
    for entry in released:
        st = states[entry["id"]]
        sources.append({**{k: entry[k] for k in PUBLIC_REGISTRY_FIELDS},
                        **{k: st[k] for k in PUBLIC_STATE_FIELDS}})
    # Das interne ingest-Objekt wird NICHT veroeffentlicht. Genau ein Feld daraus wird
    # abgeleitet: wann die Quelle den Eintrag zuletzt geliefert hat. Das Schema erzwingt
    # die Trennung (Item traegt ingest, PublicItem traegt last_seen_at - nie beides).
    items = [{**{k: v for k, v in it.items() if k != "ingest"},
              "last_seen_at": it["ingest"]["last_seen_at"]}
             for it in items_doc["items"] if it["source"] in released_ids]
    items.sort(key=lambda it: (display_time(it), it["id"]), reverse=True)
    return {"schema_version": SCHEMA_VERSION, "state_revision": revision,
            "generated_at": generated_at, "sources": sources, "items": items}
