"""Pick the configured connection backend (SSH+remote CLI, or direct TCP/socket)."""

from __future__ import annotations

from typing import Any

from mysql_diag_mcp import direct, ssh
from mysql_diag_mcp.config import Settings, load_settings


def run_mysql(
    sql: str,
    *,
    settings: Settings | None = None,
    max_rows: int | None = None,
    timeout_sec: int | None = None,
) -> dict[str, Any]:
    cfg = settings or load_settings()
    backend = direct.run_mysql if cfg.mysql_conn_mode == "direct" else ssh.run_mysql
    return backend(sql, settings=cfg, max_rows=max_rows, timeout_sec=timeout_sec)
