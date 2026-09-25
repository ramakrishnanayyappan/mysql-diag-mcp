# Spike runbook

Call tools in this order. Do not invent free-form SQL. Stop and report if a tool returns `ok: false`.

1. **mysql_ping** — confirm connectivity + MySQL are reachable. If this fails, the outage is connectivity, not query load.
2. **mysql_global_status** — look at `Threads_running`, `Threads_connected`, `Created_tmp_disk_tables`, `Innodb_row_lock_waits`, `Aborted_connects`, `Slow_queries`.
3. **mysql_processlist** and **mysql_active_queries** — stuck queries, metadata locks (`Waiting for table metadata lock`), too many `Sleep` connections.
4. **mysql_lock_waits** — blocking chains (`performance_schema.data_locks` on 8.0+, `innodb_lock_waits` on older 5.7). Empty is normal if no one is blocked.
5. **mysql_innodb_trx** — long-open transactions (large `trx_age_sec`) that pin the history list / row locks.
6. **mysql_innodb_status** — `history_list_length`, deadlocks, semaphore waits, buffer pool.
7. **mysql_digest_top** — highest-latency statement digests from performance_schema (no app-table reads).
8. **mysql_status_delta** — 2–5 second sample for QPS, tmp-disk tables/s, lock waits/s.
9. **mysql_monitor_clients** — group by user/host. A flood from a single monitoring-agent user/host is a monitoring storm, not an app bug.
10. **mysql_wait_events** / **mysql_table_io** — IO vs lock vs mutex; hot tables. May be empty if wait instruments are off.
11. **mysql_replica_status** / **mysql_replica_topology** — if this server replicates or has replicas, check lag (`Seconds_Behind_Source`/`Seconds_Behind_Master`) and IO/SQL thread health before blaming query load.
12. **mysql_variables** — sanity-check buffer pool, `max_connections`, slow log, and query cache (if the server version still has one).
13. **mysql_explain** — only on a single `SELECT` or `SHOW` copied from processlist/digest. Never DML.

Correlate with your monitoring/dashboarding tool's graphs after the live snapshot. Do not restart MySQL or change config from this MCP.
