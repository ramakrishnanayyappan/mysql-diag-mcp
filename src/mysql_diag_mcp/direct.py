"""Direct TCP/socket MySQL connection backend using PyMySQL.

Alternative to ssh.py for users without an SSH bastion in front of MySQL.
Implements the same run_mysql(sql, ...) contract and return shape so
server.py can use either backend interchangeably (see backend.py).
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import pymysql
import pymysql.cursors
import pymysql.err

from mysql_diag_mcp.config import Settings, load_settings

log = logging.getLogger("mysql_diag_mcp")

_lock = threading.Lock()
_conn: pymysql.connections.Connection | None = None


def _connect(cfg: Settings) -> pymysql.connections.Connection:
    return pymysql.connect(
        user=cfg.mysql_user,
        password=cfg.mysql_password or "",
        host=cfg.mysql_host,
        port=cfg.mysql_port,
        unix_socket=cfg.mysql_socket,
        connect_timeout=cfg.mysql_connect_timeout_sec,
        read_timeout=cfg.mysql_timeout_sec,
        write_timeout=cfg.mysql_timeout_sec,
        cursorclass=pymysql.cursors.DictCursor,
        ssl_disabled=(cfg.mysql_ssl_mode == "disabled"),
        ssl_ca=cfg.mysql_ssl_ca,
        ssl_cert=cfg.mysql_ssl_cert,
        ssl_key=cfg.mysql_ssl_key,
        ssl_verify_cert=cfg.mysql_ssl_mode in ("verify_ca", "verify_identity"),
        ssl_verify_identity=(cfg.mysql_ssl_mode == "verify_identity"),
    )


def _get_connection(cfg: Settings, *, force_new: bool = False) -> pymysql.connections.Connection:
    global _conn
    with _lock:
        if force_new and _conn is not None:
            try:
                _conn.close()
            except Exception:  # noqa: BLE001 - best-effort cleanup of a possibly-dead socket
                pass
            _conn = None
        if _conn is None or not _conn.open:
            _conn = _connect(cfg)
        return _conn


def reset_connection() -> None:
    global _conn
    with _lock:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:  # noqa: BLE001
                pass
        _conn = None


def run_mysql(
    sql: str,
    *,
    settings: Settings | None = None,
    max_rows: int | None = None,
    timeout_sec: int | None = None,
) -> dict[str, Any]:
    cfg = settings or load_settings()
    missing = cfg.missing
    if missing:
        return {
            "ok": False,
            "error": (
                "Missing required settings: "
                + ", ".join(missing)
                + ". Copy .env.example to .env and fill MYSQL_USER (and connection details)."
            ),
        }

    limit = max_rows if max_rows is not None else cfg.mysql_max_rows

    for attempt in (1, 2):
        try:
            conn = _get_connection(cfg, force_new=(attempt == 2))
            with conn.cursor() as cur:
                cur.execute(sql)
                columns = [d[0] for d in cur.description] if cur.description else []
                rows = cur.fetchmany(limit)
                truncated = cur.fetchone() is not None
            return {
                "ok": True,
                "columns": columns,
                "rows": list(rows),
                "row_count": len(rows),
                "truncated": truncated,
            }
        except pymysql.err.OperationalError as exc:
            if attempt == 1:
                log.debug("direct backend: reconnecting after OperationalError: %s", exc)
                continue
            return {"ok": False, "error": f"MySQL connection error: {exc}"}
        except pymysql.MySQLError as exc:
            return {"ok": False, "error": str(exc)}
        except OSError as exc:
            return {"ok": False, "error": f"connection failed: {exc}"}
