"""Detect MySQL server version once per process and expose feature flags.

Query variants live as functions in queries.py; this module only answers
"which variant does this server need" from a cached VERSION() probe.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any, Callable

from mysql_diag_mcp import queries

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")

_lock = threading.Lock()
_cached: ServerCapabilities | None = None


@dataclass(frozen=True)
class ServerCapabilities:
    version: tuple[int, int, int]
    version_string: str

    @property
    def supports_data_locks(self) -> bool:
        """performance_schema.data_locks/data_lock_waits replace innodb_locks/innodb_lock_waits."""
        return self.version >= (8, 0, 0)

    @property
    def has_query_cache(self) -> bool:
        """Query cache was removed entirely in MySQL 8.0."""
        return self.version < (8, 0, 0)

    @property
    def supports_show_replica_status(self) -> bool:
        """SHOW REPLICA STATUS / SHOW REPLICAS replace the SLAVE-named forms in 8.0.22+."""
        return self.version >= (8, 0, 22)


def _parse_version(raw: str) -> tuple[int, int, int] | None:
    match = _VERSION_RE.match(raw.strip())
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def get_capabilities(
    run_mysql_fn: Callable[..., dict[str, Any]], *, force_refresh: bool = False
) -> dict[str, Any]:
    """Probe and cache server capabilities for the lifetime of this process.

    Safe to cache per-process: this server targets exactly one fixed MySQL
    instance for its whole run (single-target-per-process configuration).
    """
    global _cached
    with _lock:
        if _cached is not None and not force_refresh:
            return {"ok": True, "capabilities": _cached}

        result = run_mysql_fn(queries.VERSION_PROBE)
        if not result.get("ok"):
            return result
        rows = result.get("rows") or []
        if not rows:
            return {"ok": False, "error": "VERSION() probe returned no rows"}

        raw_version = rows[0].get("version") or rows[0].get("VERSION") or ""
        parsed = _parse_version(raw_version)
        if parsed is None:
            return {"ok": False, "error": f"could not parse server version from {raw_version!r}"}

        _cached = ServerCapabilities(version=parsed, version_string=raw_version)
        return {"ok": True, "capabilities": _cached}


def reset_cache() -> None:
    global _cached
    with _lock:
        _cached = None
