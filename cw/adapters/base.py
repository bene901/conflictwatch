from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class FetchResult:
    """Adaptervertrag (Spezifikation A6).

    items: ItemDrafts (Item ohne ingest und level_change).
    complete: True nur, wenn nachweislich alle Einträge des abgefragten Umfangs enthalten sind.
    aliases: optionale weitere IDs je Draft, unter denen die Quelle dasselbe Objekt früher geführt hat.
    """
    items: list
    complete: bool
    items_in_window: int
    aliases: dict = field(default_factory=dict)
