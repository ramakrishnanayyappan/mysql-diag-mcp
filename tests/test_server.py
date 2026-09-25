import unittest
from unittest.mock import patch

from mysql_diag_mcp.capabilities import ServerCapabilities
from mysql_diag_mcp.server import mcp, mysql_global_status, mysql_lock_waits, mysql_replica_status, mysql_variables

LEGACY_CAPS = {"ok": True, "capabilities": ServerCapabilities((5, 7, 44), "5.7.44")}
MODERN_CAPS = {"ok": True, "capabilities": ServerCapabilities((8, 0, 34), "8.0.34")}


class ServerSurfaceTests(unittest.TestCase):
    def test_expected_tools_registered(self):
        tools = mcp._tool_manager.list_tools()
        names = {tool.name for tool in tools}
        self.assertEqual(
            names,
            {
                "mysql_ping",
                "mysql_processlist",
                "mysql_active_queries",
                "mysql_global_status",
                "mysql_status_delta",
                "mysql_variables",
                "mysql_innodb_status",
                "mysql_innodb_trx",
                "mysql_lock_waits",
                "mysql_digest_top",
                "mysql_wait_events",
                "mysql_table_io",
                "mysql_monitor_clients",
                "mysql_replica_status",
                "mysql_replica_topology",
                "mysql_explain",
            },
        )

    def test_spike_runbook_resource(self):
        resources = mcp._resource_manager.list_resources()
        uris = {str(resource.uri) for resource in resources}
        self.assertIn("runbook://spike", uris)


class LockWaitsVariantTests(unittest.TestCase):
    @patch("mysql_diag_mcp.server.run_mysql")
    @patch("mysql_diag_mcp.server.capabilities.get_capabilities", return_value=LEGACY_CAPS)
    def test_uses_legacy_query_below_8_0(self, _caps, run_mysql):
        run_mysql.return_value = {"ok": True, "rows": []}
        mysql_lock_waits()
        sql = run_mysql.call_args[0][0]
        self.assertIn("information_schema.innodb_lock_waits", sql)

    @patch("mysql_diag_mcp.server.run_mysql")
    @patch("mysql_diag_mcp.server.capabilities.get_capabilities", return_value=MODERN_CAPS)
    def test_uses_data_locks_on_8_0_plus(self, _caps, run_mysql):
        run_mysql.return_value = {"ok": True, "rows": []}
        mysql_lock_waits()
        sql = run_mysql.call_args[0][0]
        self.assertIn("performance_schema.data_lock_waits", sql)

    @patch("mysql_diag_mcp.server.capabilities.get_capabilities", return_value={"ok": False, "error": "boom"})
    def test_propagates_capability_error(self, _caps):
        result = mysql_lock_waits()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "boom")


class ReplicaStatusTests(unittest.TestCase):
    @patch("mysql_diag_mcp.server.run_mysql")
    @patch("mysql_diag_mcp.server.capabilities.get_capabilities", return_value=MODERN_CAPS)
    def test_not_a_replica_is_ok(self, _caps, run_mysql):
        run_mysql.return_value = {"ok": True, "rows": []}
        result = mysql_replica_status()
        self.assertTrue(result["ok"])
        self.assertFalse(result["is_replica"])
        self.assertEqual(result["rows"], [])

    @patch("mysql_diag_mcp.server.run_mysql")
    @patch("mysql_diag_mcp.server.capabilities.get_capabilities", return_value=MODERN_CAPS)
    def test_replica_truncates_error_fields(self, _caps, run_mysql):
        run_mysql.return_value = {
            "ok": True,
            "rows": [{"Last_IO_Error": "x" * 600, "Last_SQL_Error": "y" * 600}],
        }
        result = mysql_replica_status()
        self.assertTrue(result["is_replica"])
        self.assertIn("truncated", result["rows"][0]["Last_IO_Error"])


class QueryCacheFieldTests(unittest.TestCase):
    @patch("mysql_diag_mcp.server.run_mysql")
    @patch("mysql_diag_mcp.server.capabilities.get_capabilities", return_value=LEGACY_CAPS)
    def test_status_reports_query_cache_available_on_5_7(self, _caps, run_mysql):
        run_mysql.return_value = {"ok": True, "rows": []}
        result = mysql_global_status()
        self.assertTrue(result["query_cache_available"])

    @patch("mysql_diag_mcp.server.run_mysql")
    @patch("mysql_diag_mcp.server.capabilities.get_capabilities", return_value=MODERN_CAPS)
    def test_variables_reports_query_cache_unavailable_on_8_0(self, _caps, run_mysql):
        run_mysql.return_value = {"ok": True, "rows": []}
        result = mysql_variables()
        self.assertFalse(result["query_cache_available"])


if __name__ == "__main__":
    unittest.main()
