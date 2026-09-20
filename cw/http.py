"""HTTP-Abruf mit Größen- und Zeitlimit. Keine Wiederholungen: der nächste Lauf ist die Wiederholung."""
from __future__ import annotations
import socket
import urllib.error
import urllib.request

from .errors import AdapterError

USER_AGENT = "ConflictWatch/6.0 (+https://github.com/; public-data research; no-reply)"
MAX_BYTES = 5_000_000


def fetch(url: str, timeout: float = 20.0, max_bytes: int = MAX_BYTES) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                raise AdapterError("http", f"HTTP {resp.status}")
            data = resp.read(max_bytes + 1)
    except AdapterError:
        raise
    except urllib.error.HTTPError as exc:
        raise AdapterError("http", f"HTTP {exc.code}") from None
    except (socket.timeout, TimeoutError):
        raise AdapterError("timeout", f"Zeitlimit {timeout}s überschritten") from None
    except (urllib.error.URLError, ConnectionError, OSError) as exc:
        raise AdapterError("network", str(exc)) from None
    if len(data) > max_bytes:
        raise AdapterError("size", f"Antwort größer als {max_bytes} Bytes")
    return data
