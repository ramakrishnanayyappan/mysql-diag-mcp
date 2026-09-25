import unittest

from mysql_diag_mcp.server import mcp


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
                "mysql_explain",
            },
        )

    def test_spike_runbook_resource(self):
        resources = mcp._resource_manager.list_resources()
        uris = {str(resource.uri) for resource in resources}
        self.assertIn("runbook://spike", uris)


if __name__ == "__main__":
    unittest.main()
