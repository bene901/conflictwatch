KINDS = {"network", "timeout", "http", "size", "parse", "schema", "sanity"}


class AdapterError(Exception):
    """Fehler eines Abrufs. kind ist eine der Fehlerarten aus SourceState.last_error."""

    def __init__(self, kind: str, detail: str):
        if kind not in KINDS:
            raise ValueError(kind)
        super().__init__(f"{kind}: {detail}")
        self.kind = kind
        self.detail = detail[:300]
