# mysql-diag-mcp

A read-only [MCP](https://modelcontextprotocol.io) server that gives an AI
agent (or any MCP client) a curated set of **diagnostic-only** tools for
troubleshooting MySQL performance problems — the kind of thing a DBA or ops
engineer reaches for during a slowdown: processlist, blocking chains, InnoDB
status, statement digests, replication lag, and curated status/variable
snapshots.

Supports **MySQL 5.7 through 8.4+**. The server detects the target server's
version once per run and automatically selects the right query variant
where MySQL's schema changed between major versions (e.g. lock-wait
diagnostics, replication status).

There is **no generic SQL tool** and this MCP never reads application row
data — every tool is backed by a fixed query against
`information_schema`/`performance_schema`/`SHOW ...` metadata. The one
exception, `mysql_explain`, only runs `EXPLAIN` on a single `SELECT`/`SHOW`
statement you provide; it never executes DML/DDL.

## Connection modes

Pick whichever fits your environment via `MYSQL_CONN_MODE`:

```
MYSQL_CONN_MODE=ssh (default)
  MCP client  →  mysql-diag (stdio)  →  ssh [-J bastion] dbhost  →  mysql CLI (socket or TCP)

MYSQL_CONN_MODE=direct
  MCP client  →  mysql-diag (stdio)  →  PyMySQL  →  MySQL (TCP or unix socket)
```

- **`ssh`** — hops over SSH (optionally through a bastion) and runs the
  remote host's `mysql` CLI binary. Good when MySQL is only reachable from
  inside a network you access via SSH, and you'd rather not open a DB port
  to the machine running this MCP.
- **`direct`** — connects straight to MySQL over TCP or a local unix
  socket using a bundled Python driver ([PyMySQL](https://pymysql.readthedocs.io/)).
  No SSH, no remote CLI dependency. Use this if you already have network
  access to the DB (directly, via VPN, or via your own port-forward/tunnel).
  Configure `MYSQL_SSL_MODE` (`disabled` by default, or `required`/
  `verify_ca`/`verify_identity` with `MYSQL_SSL_CA`/`MYSQL_SSL_CERT`/
  `MYSQL_SSL_KEY`) if you're connecting over an untrusted network.

## Setup

1. Install [uv](https://docs.astral.sh/uv/) if needed, then from this repo:

   ```bash
   uv sync
   ```

2. Copy the env template and fill it in (never commit `.env`):

   ```bash
   cp .env.example .env
   ```

   See `.env.example` for every setting; the essentials:

   | Variable | Required | Meaning |
   |---|---|---|
   | `MYSQL_CONN_MODE` | no | `ssh` (default) or `direct` |
   | `SSH_HOST` | yes, if `ssh` mode | `user@dbhost` — or the bastion if MySQL runs there |
   | `SSH_JUMP` | no | `user@bastion` (`ssh -J`). Leave empty when the bastion **is** the DB host |
   | `SSH_KEY` | no | Private key path; otherwise ssh-agent / `~/.ssh/config` |
   | `MYSQL_USER` | yes | Dedicated `mcp_diag` user (not app root) |
   | `MYSQL_PASSWORD` | no | Omit if the remote user uses socket peer-auth / `.my.cnf` |
   | `MYSQL_SOCKET` | preferred for `ssh` mode | Socket **as seen on the DB host** |
   | `MYSQL_HOST` / `MYSQL_PORT` | fallback / required for `direct` | Used when `MYSQL_SOCKET` is unset |
   | `MYSQL_SSL_MODE` | no, `direct` mode only | `disabled` (default) / `required` / `verify_ca` / `verify_identity` |
   | `MYSQL_TIMEOUT_SEC` | no | Default `8` |
   | `MYSQL_MAX_ROWS` | no | Default `200` |

3. In `ssh` mode, confirm the hop by hand (same identity the MCP will use):

   ```bash
   ssh -o BatchMode=yes -J "$SSH_JUMP" "$SSH_HOST" \
     mysql --socket="$MYSQL_SOCKET" -u "$MYSQL_USER" -e 'SELECT 1'
   ```

4. Register the server with your MCP client, pointing it at this directory
   and your `.env` file, e.g.:

   ```json
   {
     "mcpServers": {
       "mysql-diag": {
         "command": "uv",
         "args": ["run", "--directory", "/path/to/mysql-diag-mcp", "python", "-m", "mysql_diag_mcp"],
         "envFile": "/path/to/mysql-diag-mcp/.env"
       }
     }
   }
   ```

Password is sent as a remote `--defaults-extra-file` (base64 over SSH
stdin), not on `ps` argv, in `ssh` mode.

## MySQL grants

Run as an admin on the target server. No application-schema grants — these
work unchanged on 5.7 and 8.0/8.4:

```sql
CREATE USER 'mcp_diag'@'localhost' IDENTIFIED BY 'choose-a-strong-password';

GRANT PROCESS, REPLICATION CLIENT, REPLICATION SLAVE ON *.* TO 'mcp_diag'@'localhost';
GRANT SELECT ON performance_schema.* TO 'mcp_diag'@'localhost';
GRANT SELECT ON information_schema.* TO 'mcp_diag'@'localhost';

FLUSH PRIVILEGES;
```

Use `'mcp_diag'@'%'` (or a specific client CIDR) as well if you connect via
`MYSQL_CONN_MODE=direct` from a different host than the DB server.

## Tools

| Tool | Purpose |
|---|---|
| `mysql_ping` | Reachability, version, hostname |
| `mysql_processlist` | `SHOW FULL PROCESSLIST` |
| `mysql_active_queries` | Non-`Sleep` threads |
| `mysql_global_status` | Curated status counters (+ whether query cache exists on this version) |
| `mysql_status_delta` | Two samples → per-second rates |
| `mysql_variables` | Curated variables (buffer pool, query cache if present, slow log) |
| `mysql_innodb_status` | Parsed InnoDB status + history list length |
| `mysql_innodb_trx` | Open transactions |
| `mysql_lock_waits` | Blocking chains — `performance_schema.data_locks` (8.0+) or `innodb_lock_waits` (older) |
| `mysql_digest_top` | Top statement digests by wait time |
| `mysql_wait_events` | Wait event summary (often empty if instruments are off) |
| `mysql_table_io` | Hottest tables by IO wait |
| `mysql_monitor_clients` | Connections grouped by user/host — spot monitoring-agent storms |
| `mysql_replica_status` | Replica lag/thread health — `SHOW REPLICA STATUS` (8.0.22+) or `SHOW SLAVE STATUS` (older) |
| `mysql_replica_topology` | Connected replicas — `SHOW REPLICAS` (8.0.22+) or `SHOW SLAVE HOSTS` (older) |
| `mysql_explain` | `EXPLAIN` of one `SELECT`/`SHOW` only |

Resource `runbook://spike` is the suggested call order for a user-facing
slowdown.

## Safety

- Allowlisted SQL only. `mysql_explain` must start with `SELECT` or `SHOW`, contain no `;`, and no DML/DDL keywords.
- Timeouts kill the SSH/mysql process (or the direct connection). `Info` / InnoDB dumps and replication error fields are truncated.
- In `ssh` mode: `BatchMode`, `ControlMaster` connection reuse, optional `ProxyJump`.
- This MCP cannot `INSERT`/`UPDATE`/`DELETE`, dump application row data, or change server configuration.

## Development

```bash
uv sync
uv run python -m unittest discover -s tests -v
uv run python -m mysql_diag_mcp   # stdio MCP server
```

Logs go to **stderr** only (stdout is the MCP protocol).

## License

MIT — see [LICENSE](LICENSE).
