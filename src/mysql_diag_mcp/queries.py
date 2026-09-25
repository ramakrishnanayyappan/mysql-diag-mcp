"""Fixed SQL only. User text is never interpolated except via validate_explain_sql."""

PING = """
SELECT
  VERSION() AS version,
  @@hostname AS hostname,
  @@port AS port,
  NOW() AS server_time,
  @@read_only AS read_only
""".strip()

VERSION_PROBE = "SELECT VERSION() AS version"

PROCESSLIST = "SHOW FULL PROCESSLIST"

ACTIVE_QUERIES = """
SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, INFO
FROM information_schema.PROCESSLIST
WHERE COMMAND != 'Sleep'
ORDER BY TIME DESC
""".strip()

GLOBAL_STATUS = "SHOW GLOBAL STATUS"

GLOBAL_VARIABLES = "SHOW GLOBAL VARIABLES"

INNODB_STATUS = "SHOW ENGINE INNODB STATUS"

INNODB_TRX = """
SELECT
  trx_id,
  trx_state,
  trx_started,
  TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_sec,
  trx_wait_started,
  trx_mysql_thread_id,
  trx_query,
  trx_tables_in_use,
  trx_tables_locked,
  trx_rows_locked,
  trx_rows_modified,
  trx_isolation_level,
  trx_operation_state
FROM information_schema.innodb_trx
ORDER BY trx_started
""".strip()

LOCK_WAITS = """
SELECT
  r.trx_id AS waiting_trx_id,
  r.trx_mysql_thread_id AS waiting_thread,
  r.trx_query AS waiting_query,
  b.trx_id AS blocking_trx_id,
  b.trx_mysql_thread_id AS blocking_thread,
  b.trx_query AS blocking_query,
  l.lock_table,
  l.lock_index,
  l.lock_mode,
  l.lock_type
FROM information_schema.innodb_lock_waits w
JOIN information_schema.innodb_trx r ON r.trx_id = w.requesting_trx_id
JOIN information_schema.innodb_trx b ON b.trx_id = w.blocking_trx_id
JOIN information_schema.innodb_locks l ON l.lock_id = w.requested_lock_id
""".strip()

DIGEST_TOP = """
SELECT
  SCHEMA_NAME,
  DIGEST_TEXT,
  COUNT_STAR,
  ROUND(SUM_TIMER_WAIT / 1e12, 4) AS sum_wait_sec,
  ROUND(AVG_TIMER_WAIT / 1e12, 6) AS avg_wait_sec,
  SUM_ROWS_EXAMINED,
  SUM_ROWS_SENT,
  SUM_CREATED_TMP_DISK_TABLES,
  SUM_NO_INDEX_USED,
  SUM_NO_GOOD_INDEX_USED,
  FIRST_SEEN,
  LAST_SEEN
FROM performance_schema.events_statements_summary_by_digest
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20
""".strip()

WAIT_EVENTS = """
SELECT
  EVENT_NAME,
  COUNT_STAR,
  ROUND(SUM_TIMER_WAIT / 1e12, 4) AS sum_wait_sec
FROM performance_schema.events_waits_summary_global_by_event_name
WHERE COUNT_STAR > 0
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 30
""".strip()

TABLE_IO = """
SELECT
  OBJECT_SCHEMA,
  OBJECT_NAME,
  COUNT_STAR,
  ROUND(SUM_TIMER_WAIT / 1e12, 4) AS sum_wait_sec,
  COUNT_READ,
  COUNT_WRITE
FROM performance_schema.table_io_waits_summary_by_table
WHERE OBJECT_SCHEMA NOT IN ('mysql', 'performance_schema', 'information_schema', 'sys')
  AND COUNT_STAR > 0
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20
""".strip()

MONITOR_CLIENTS = """
SELECT
  USER,
  SUBSTRING_INDEX(HOST, ':', 1) AS host,
  COMMAND,
  COUNT(*) AS connections,
  MAX(TIME) AS max_time_sec,
  SUM(TIME) AS sum_time_sec
FROM information_schema.PROCESSLIST
GROUP BY USER, SUBSTRING_INDEX(HOST, ':', 1), COMMAND
ORDER BY connections DESC
""".strip()

STATUS_KEYS = (
    "Aborted_clients",
    "Aborted_connects",
    "Bytes_received",
    "Bytes_sent",
    "Com_commit",
    "Com_delete",
    "Com_insert",
    "Com_rollback",
    "Com_select",
    "Com_update",
    "Connections",
    "Created_tmp_disk_tables",
    "Created_tmp_files",
    "Created_tmp_tables",
    "Innodb_buffer_pool_read_requests",
    "Innodb_buffer_pool_reads",
    "Innodb_buffer_pool_wait_free",
    "Innodb_pages_dirty",
    "Innodb_row_lock_time",
    "Innodb_row_lock_time_avg",
    "Innodb_row_lock_time_max",
    "Innodb_row_lock_waits",
    "Max_used_connections",
    "Open_tables",
    "Opened_tables",
    "Qcache_hits",
    "Qcache_inserts",
    "Queries",
    "Questions",
    "Select_full_join",
    "Select_scan",
    "Slow_queries",
    "Sort_merge_passes",
    "Table_locks_waited",
    "Threads_connected",
    "Threads_created",
    "Threads_running",
    "Uptime",
)

STATUS_GAUGES = frozenset(
    {
        "Threads_running",
        "Threads_connected",
        "Innodb_pages_dirty",
        "Max_used_connections",
        "Open_tables",
        "Innodb_row_lock_time_avg",
        "Innodb_row_lock_time_max",
    }
)

VARIABLE_KEYS = (
    "innodb_buffer_pool_instances",
    "innodb_buffer_pool_size",
    "innodb_file_per_table",
    "innodb_flush_log_at_trx_commit",
    "innodb_flush_method",
    "innodb_io_capacity",
    "innodb_lock_wait_timeout",
    "innodb_log_file_size",
    "interactive_timeout",
    "log_queries_not_using_indexes",
    "long_query_time",
    "max_connect_errors",
    "max_connections",
    "max_heap_table_size",
    "performance_schema",
    "query_cache_size",
    "query_cache_type",
    "read_only",
    "skip_name_resolve",
    "slow_query_log",
    "slow_query_log_file",
    "sync_binlog",
    "table_definition_cache",
    "table_open_cache",
    "thread_cache_size",
    "tmp_table_size",
    "tx_isolation",
    "transaction_isolation",
    "version",
    "version_comment",
    "wait_timeout",
)
