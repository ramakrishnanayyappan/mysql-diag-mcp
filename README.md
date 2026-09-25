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

## Running as a shared network server

By default this runs over `stdio`: one client spawns it as a local
subprocess. It can instead run as a persistent HTTP service that many
different users/agents (Claude, Cursor, or anything else that speaks MCP)
connect to over the network, instead of everyone needing their own local
checkout and DB credentials.

**Where you run this, and how it reaches your MySQL server(s), is entirely
up to you/ops** — it doesn't need to sit next to the database. Both
connection modes above work the same regardless of placement: `ssh` if this
host has SSH access to a bastion/DB host, `direct` if it has plain network
(or VPN/tunnel) access to MySQL itself.

1. Set the network env vars (add to `.env` or pass directly):

   | Variable | Meaning |
   |---|---|
   | `MCP_TRANSPORT` | `stdio` (default) / `streamable-http` (recommended) / `sse` (legacy clients) |
   | `MCP_HOST` | Bind address, e.g. `0.0.0.0` to listen on all interfaces |
   | `MCP_PORT` | Default `8000` |
   | `MCP_AUTH_TOKENS` | `token1:alice,token2:bob` — required for any non-`stdio` transport |
   | `MCP_ALLOW_NO_AUTH` | `true` to explicitly run without token auth (see below) |
   | `MCP_ALLOWED_HOSTS` / `MCP_ALLOWED_ORIGINS` | Comma-separated; required once `MCP_HOST` is anything other than localhost (see below) |

2. **Auth is required by default.** Starting a `streamable-http`/`sse`
   server without `MCP_AUTH_TOKENS` refuses to start with a clear error,
   rather than silently exposing an unauthenticated diagnostics endpoint.
   Every request needs an `Authorization: Bearer <token>` header matching
   one of the configured tokens; unmatched/missing tokens get a `401`. Each
   request is logged with the token's label, method, path, status, and
   duration — the audit trail for a shared credential now serving multiple
   people. If you're deliberately relying on network-level access control
   instead (firewall, VPN, an authenticating reverse proxy), set
   `MCP_ALLOW_NO_AUTH=true` to opt out explicitly.

3. **This app serves plain HTTP — it does not terminate TLS.** Put a
   reverse proxy (nginx, Caddy, your load balancer) in front for HTTPS;
   forward `Authorization` headers through unchanged.

4. **DNS-rebinding protection**: once `MCP_HOST` is not `127.0.0.1`/
   `localhost`, set `MCP_ALLOWED_HOSTS`/`MCP_ALLOWED_ORIGINS` to the
   hostname(s)/origin(s) clients will actually use to reach this server —
   otherwise the SDK's rebinding protection will reject requests with
   `421 Invalid Host header`.

5. Run it directly:

   ```bash
   MCP_TRANSPORT=streamable-http MCP_HOST=0.0.0.0 MCP_AUTH_TOKENS=devtoken:alice \
     uv run python -m mysql_diag_mcp
   ```

   Or with Docker:

   ```bash
   docker build -t mysql-diag-mcp .
   docker run -p 8000:8000 --env-file .env \
     -e MCP_AUTH_TOKENS=devtoken:alice \
     mysql-diag-mcp
   ```

   For `MYSQL_CONN_MODE=ssh` inside the container, mount an SSH key
   read-only and point `SSH_KEY` at it, e.g.
   `-v $HOME/.ssh/id_ed25519:/root/.ssh/id_ed25519:ro -e SSH_KEY=/root/.ssh/id_ed25519`.

6. Point your MCP client at `http://<host>:<port>/mcp` (or `/sse` for the
   legacy transport) with an `Authorization: Bearer <token>` header. The
   exact way to add a remote HTTP MCP server varies by client and version —
   check your client's own docs for the current syntax.

All callers share the same MySQL privileges as the one configured DB user —
no new risk versus the single-user model, just now serving more people; the
per-request identity logging above is how you attribute usage.

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
