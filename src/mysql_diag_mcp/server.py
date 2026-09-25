"""Stdio FastMCP server: curated, version-agnostic MySQL diagnostic tools (5.7 through 8.4+)."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from mysql_diag_mcp import capabilities, queries
from mysql_diag_mcp.config import load_settings
from mysql_diag_mcp.explain import ExplainRejected, validate_explain_sql
from mysql_diag_mcp.backend import run_mysql
from mysql_diag_mcp.parse import parse_innodb_status, pick_keys, status_map, to_number, truncate_field

log = logging.getLogger("mysql_diag_mcp")

mcp = FastMCP("mysql-diag")

_RUNBOOK = Path(__file__).with_name("runbook.md").read_text(encoding="utf-8")


def _query(sql: str, *truncate_fields: str) -> dict[str, Any]:
    result = run_mysql(sql)
    if result.get("ok") and truncate_fields:
        limit = load_settings().info_truncate
        for field in truncate_fields:
            truncate_field(result["rows"], field, limit)
    return result


@mcp.tool()
def mysql_ping() -> dict[str, Any]:
    """Check SSH + MySQL reachability; return version, hostname, and server time."""
    return _query(queries.PING)


@mcp.tool()
def mysql_processlist() -> dict[str, Any]:
    """SHOW FULL PROCESSLIST. Truncates Info. Use during a user-facing slowdown."""
    return _query(queries.PROCESSLIST, "Info")


@mcp.tool()
def mysql_active_queries() -> dict[str, Any]:
    """Non-Sleep threads from information_schema.PROCESSLIST, longest first."""
    return _query(queries.ACTIVE_QUERIES, "INFO")


@mcp.tool()
def mysql_global_status() -> dict[str, Any]:
    """Curated SHOW GLOBAL STATUS keys (threads, tmp tables, InnoDB locks, QPS counters)."""
    caps = capabilities.get_capabilities(run_mysql)
    if not caps.get("ok"):
        return caps
    result = run_mysql(queries.GLOBAL_STATUS)
    if not result.get("ok"):
        return result
    picked = pick_keys(status_map(result["rows"]), queries.STATUS_KEYS)
    return {
        "ok": True,
        "status": picked,
        "truncated": result.get("truncated", False),
        "query_cache_available": caps["capabilities"].has_query_cache,
    }


@mcp.tool()
def mysql_status_delta(sample_seconds: int = 2) -> dict[str, Any]:
    """Two GLOBAL STATUS samples; counters as per-second rates, gauges as t0/t1."""
    seconds = max(1, min(int(sample_seconds), 10))
    first = run_mysql(queries.GLOBAL_STATUS)
    if not first.get("ok"):
        return first
    time.sleep(seconds)
    second = run_mysql(queries.GLOBAL_STATUS)
    if not second.get("ok"):
        return second
    a = pick_keys(status_map(first["rows"]), queries.STATUS_KEYS)
    b = pick_keys(status_map(second["rows"]), queries.STATUS_KEYS)
    metrics: dict[str, Any] = {}
    for key in queries.STATUS_KEYS:
        if key not in a or key not in b:
            continue
        n0, n1 = to_number(a[key]), to_number(b[key])
        if n0 is None or n1 is None:
            continue
        if key in queries.STATUS_GAUGES:
            metrics[key] = {"t0": n0, "t1": n1}
        else:
            delta = n1 - n0
            metrics[key] = {"delta": delta, "per_sec": round(delta / seconds, 4)}
    return {"ok": True, "sample_seconds": seconds, "metrics": metrics}


@mcp.tool()
def mysql_variables() -> dict[str, Any]:
    """Curated SHOW GLOBAL VARIABLES (buffer pool, connections, slow log, query cache if present)."""
    caps = capabilities.get_capabilities(run_mysql)
    if not caps.get("ok"):
        return caps
    result = run_mysql(queries.GLOBAL_VARIABLES)
    if not result.get("ok"):
        return result
    picked = pick_keys(status_map(result["rows"]), queries.VARIABLE_KEYS)
    return {
        "ok": True,
        "variables": picked,
        "query_cache_available": caps["capabilities"].has_query_cache,
    }


@mcp.tool()
def mysql_innodb_status() -> dict[str, Any]:
    """Parsed SHOW ENGINE INNODB STATUS: history list, deadlocks, semaphores, buffer pool."""
    result = run_mysql(queries.INNODB_STATUS)
    if not result.get("ok"):
        return result
    if not result["rows"]:
        return {"ok": False, "error": "SHOW ENGINE INNODB STATUS returned no rows"}
    blob = result["rows"][0].get("Status") or result["rows"][0].get("status") or ""
    parsed = parse_innodb_status(blob, load_settings().innodb_section_truncate)
    parsed["ok"] = True
    return parsed


@mcp.tool()
def mysql_innodb_trx() -> dict[str, Any]:
    """Open InnoDB transactions (age, thread, query). Long trx_age_sec pins locks/history."""
    return _query(queries.INNODB_TRX, "trx_query")


@mcp.tool()
def mysql_lock_waits() -> dict[str, Any]:
    """Blocking chains: performance_schema.data_locks (8.0+) or innodb_locks (<8.0.18). Empty if nobody is waiting."""
    caps = capabilities.get_capabilities(run_mysql)
    if not caps.get("ok"):
        return caps
    sql = queries.lock_waits_sql(caps["capabilities"])
    return _query(sql, "waiting_query", "blocking_query")


@mcp.tool()
def mysql_digest_top() -> dict[str, Any]:
    """Top statement digests by wait time from performance_schema (no application table reads)."""
    return _query(queries.DIGEST_TOP, "DIGEST_TEXT")


@mcp.tool()
def mysql_wait_events() -> dict[str, Any]:
    """Top wait events. Often empty if wait instruments are disabled."""
    return _query(queries.WAIT_EVENTS)


@mcp.tool()
def mysql_table_io() -> dict[str, Any]:
    """Hottest application tables by IO wait (excludes mysql/performance_schema/sys)."""
    return _query(queries.TABLE_IO)


@mcp.tool()
def mysql_monitor_clients() -> dict[str, Any]:
    """Processlist grouped by user/host/command. Use to spot monitoring-agent connection storms."""
    return _query(queries.MONITOR_CLIENTS)


@mcp.tool()
def mysql_replica_status() -> dict[str, Any]:
    """Replica lag, IO/SQL thread state, last IO/SQL error.

    SHOW REPLICA STATUS (8.0.22+) or SHOW SLAVE STATUS (older). Replication
    channel metadata only, never binlog row contents. `is_replica: false`
    with empty rows is the normal result on a standalone/primary server.
    """
    caps = capabilities.get_capabilities(run_mysql)
    if not caps.get("ok"):
        return caps
    sql = queries.replica_status_sql(caps["capabilities"])
    result = run_mysql(sql)
    if not result.get("ok"):
        return result
    if not result["rows"]:
        return {"ok": True, "is_replica": False, "rows": []}
    limit = load_settings().info_truncate
    truncate_field(result["rows"], "Last_IO_Error", limit)
    truncate_field(result["rows"], "Last_SQL_Error", limit)
    result["ok"] = True
    result["is_replica"] = True
    return result


@mcp.tool()
def mysql_replica_topology() -> dict[str, Any]:
    """Replicas connected to this server: SHOW REPLICAS (8.0.22+) or SHOW SLAVE HOSTS (older)."""
    caps = capabilities.get_capabilities(run_mysql)
    if not caps.get("ok"):
        return caps
    sql = queries.replica_topology_sql(caps["capabilities"])
    return _query(sql)


@mcp.tool()
def mysql_explain(statement: str) -> dict[str, Any]:
    """EXPLAIN a single SELECT or SHOW. Stacked queries and DML are rejected."""
    try:
        sql = validate_explain_sql(statement)
    except ExplainRejected as exc:
        return {"ok": False, "error": str(exc)}
    return _query(f"EXPLAIN {sql}")


@mcp.resource("runbook://spike")
def spike_runbook() -> str:
    """Fixed order of diagnostic tools to call during a user-facing MySQL slowdown."""
    return _RUNBOOK


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(name)s %(levelname)s %(message)s",
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
