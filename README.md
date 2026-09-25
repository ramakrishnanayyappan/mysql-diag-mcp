# mysql-diag-mcp

Lives at `/Users/ayyappar/.cursor/mysql-diag-mcp` (not under the n8n workspace). It is registered in `~/.cursor/mcp.json` so Cursor can use it from any project.

Read-only **MySQL 5.7** diagnostic MCP for Cursor. The agent hops SSH through a bastion and runs a curated `mysql` CLI on the database host (unix socket or `127.0.0.1`). There is **no generic SQL tool**.

```
Cursor agent  →  mysql-diag (stdio)  →  ssh -J bastion dbhost  →  mysql (socket)
```

## Setup

1. Install [uv](https://docs.astral.sh/uv/) if needed, then from this repo:

   ```bash
   uv sync
   ```

2. Copy env and fill it in (do not commit `.env`):

   ```bash
   cp .env.example .env
   ```

   | Variable | Required | Meaning |
   |---|---|---|
   | `SSH_HOST` | yes | `user@dbhost` — or the bastion if MySQL runs there |
   | `SSH_JUMP` | no | `user@bastion` (`ssh -J`). Leave empty when the bastion **is** the DB host |
   | `SSH_KEY` | no | Private key path; otherwise ssh-agent / `~/.ssh/config` |
   | `MYSQL_USER` | yes | Dedicated `mcp_diag` user (not app root) |
   | `MYSQL_PASSWORD` | no | Omit if the remote user uses socket peer-auth / `.my.cnf` |
   | `MYSQL_SOCKET` | preferred | Socket **as seen on the DB host**, e.g. `/var/run/mysqld/mysqld.sock` |
   | `MYSQL_HOST` / `MYSQL_PORT` | fallback | Used only when `MYSQL_SOCKET` is unset (`127.0.0.1:3306`) |
   | `MYSQL_TIMEOUT_SEC` | no | Default `8` |
   | `MYSQL_MAX_ROWS` | no | Default `200` |

3. Confirm the hop by hand (same identity the MCP will use):

   ```bash
   ssh -o BatchMode=yes -J "$SSH_JUMP" "$SSH_HOST" \
     mysql --socket="$MYSQL_SOCKET" -u "$MYSQL_USER" -e 'SELECT 1'
   ```

4. Cursor loads this server from `~/.cursor/mcp.json` (and from this project's `.cursor/mcp.json`). Copy `.env.example` to `.env` first, then reload MCP in Cursor.

Password is sent as a remote `--defaults-extra-file` (base64 over SSH stdin), not on `ps` argv.

## MySQL grants

Run as an admin on the 5.7 server. No application-schema grants.

```sql
CREATE USER 'mcp_diag'@'localhost' IDENTIFIED BY 'choose-a-strong-password';

GRANT PROCESS ON *.* TO 'mcp_diag'@'localhost';
GRANT SELECT ON performance_schema.* TO 'mcp_diag'@'localhost';
GRANT SELECT ON information_schema.* TO 'mcp_diag'@'localhost';
-- optional, only if you later add a slow-log tool:
-- GRANT SELECT ON mysql.slow_log TO 'mcp_diag'@'localhost';

FLUSH PRIVILEGES;
```

Use `'mcp_diag'@'127.0.0.1'` as well if you connect via TCP instead of the unix socket.

## Tools

| Tool | Purpose |
|---|---|
| `mysql_ping` | Reachability, version, hostname |
| `mysql_processlist` | `SHOW FULL PROCESSLIST` |
| `mysql_active_queries` | Non-`Sleep` threads |
| `mysql_global_status` | Curated status counters |
| `mysql_status_delta` | Two samples → per-second rates |
| `mysql_variables` | Curated variables (buffer pool, query cache, slow log) |
| `mysql_innodb_status` | Parsed InnoDB status + history list length |
| `mysql_innodb_trx` | Open transactions |
| `mysql_lock_waits` | 5.7 `innodb_lock_waits` / `innodb_locks` (not present on 8.0) |
| `mysql_digest_top` | Top statement digests by wait time |
| `mysql_wait_events` | Wait event summary (often empty if instruments are off) |
| `mysql_table_io` | Hottest application tables |
| `mysql_monitor_clients` | Connections grouped by user/host — Zabbix storms |
| `mysql_explain` | `EXPLAIN` of one `SELECT`/`SHOW` only |

Resource `runbook://spike` is the call order for a user-facing slowdown.

## Safety

- Allowlisted SQL only. `mysql_explain` must start with `SELECT` or `SHOW`, contain no `;`, and no DML/DDL keywords.
- Timeouts kill the SSH/mysql process group. `Info` / InnoDB dumps are truncated.
- SSH uses `BatchMode`, `ControlMaster` (reuse for `mysql_status_delta`), optional `ProxyJump`.
- This MCP cannot `INSERT`/`UPDATE`/`DELETE` or dump application tables.

## Phase 2 — Zabbix MySQL plugin (not applied by this MCP)

The plugin is a common cause of “everyone is slow” spikes: connection storms and heavy custom SQL.

- Prefer **Zabbix agent 2** native MySQL plugin over `mysqladmin` UserParameters.
- Connect via **unix socket**, set `Plugins.Mysql.KeepAlive` and a short `CallTimeout`.
- Dedicated `zbx_monitor` user; use **dependent items** instead of repeating `SHOW GLOBAL STATUS`.
- Audit `Plugins.Mysql.CustomQueriesPath` for `information_schema` full scans.
- Keep `Threads_running` / `Innodb_row_lock_waits` frequent; lengthen intervals on expensive items.

During a spike, call `mysql_monitor_clients` first to see if `zabbix` dominates `Threads_connected`.

Phase 3: overlay those metrics in Grafana (Grafana MCP is already available in this Cursor setup).

## Development

```bash
uv sync
uv run python -m unittest discover -s tests -v
uv run python -m mysql_diag_mcp   # stdio MCP; Cursor launches this
```

Logs go to **stderr** only (stdout is the MCP protocol).
