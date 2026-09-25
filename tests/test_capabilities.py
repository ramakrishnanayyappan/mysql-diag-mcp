import unittest

from mysql_diag_mcp import capabilities
from mysql_diag_mcp.capabilities import _parse_version, get_capabilities, reset_cache


class ParseVersionTests(unittest.TestCase):
    def test_plain_version(self):
        self.assertEqual(_parse_version("8.0.34"), (8, 0, 34))

    def test_version_with_cloud_suffix(self):
        self.assertEqual(_parse_version("8.0.34-cloud"), (8, 0, 34))

    def test_version_with_log_suffix(self):
        self.assertEqual(_parse_version("5.7.44-log"), (5, 7, 44))

    def test_version_8_4(self):
        self.assertEqual(_parse_version("8.4.2"), (8, 4, 2))

    def test_unparseable(self):
        self.assertIsNone(_parse_version("not-a-version"))


class GetCapabilitiesTests(unittest.TestCase):
    def setUp(self):
        reset_cache()

    def tearDown(self):
        reset_cache()

    def test_caches_after_first_call(self):
        calls = []

        def stub(sql, **kwargs):
            calls.append(sql)
            return {"ok": True, "rows": [{"version": "8.0.34"}]}

        first = get_capabilities(stub)
        second = get_capabilities(stub)
        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(first["capabilities"].version, (8, 0, 34))
        self.assertIs(first["capabilities"], second["capabilities"])

    def test_force_refresh_reprobes(self):
        calls = []

        def stub(sql, **kwargs):
            calls.append(sql)
            return {"ok": True, "rows": [{"version": "5.7.44"}]}

        get_capabilities(stub)
        get_capabilities(stub, force_refresh=True)
        self.assertEqual(len(calls), 2)

    def test_propagates_backend_error(self):
        def stub(sql, **kwargs):
            return {"ok": False, "error": "boom"}

        result = get_capabilities(stub)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "boom")

    def test_no_rows_is_an_error(self):
        def stub(sql, **kwargs):
            return {"ok": True, "rows": []}

        result = get_capabilities(stub)
        self.assertFalse(result["ok"])

    def test_unparseable_version_is_an_error(self):
        def stub(sql, **kwargs):
            return {"ok": True, "rows": [{"version": "garbage"}]}

        result = get_capabilities(stub)
        self.assertFalse(result["ok"])


class ServerCapabilitiesTests(unittest.TestCase):
    def test_supports_data_locks(self):
        self.assertFalse(capabilities.ServerCapabilities((5, 7, 44), "5.7.44").supports_data_locks)
        self.assertTrue(capabilities.ServerCapabilities((8, 0, 0), "8.0.0").supports_data_locks)
        self.assertTrue(capabilities.ServerCapabilities((8, 4, 2), "8.4.2").supports_data_locks)

    def test_has_query_cache(self):
        self.assertTrue(capabilities.ServerCapabilities((5, 7, 44), "5.7.44").has_query_cache)
        self.assertFalse(capabilities.ServerCapabilities((8, 0, 0), "8.0.0").has_query_cache)

    def test_supports_show_replica_status(self):
        self.assertFalse(capabilities.ServerCapabilities((8, 0, 21), "8.0.21").supports_show_replica_status)
        self.assertTrue(capabilities.ServerCapabilities((8, 0, 22), "8.0.22").supports_show_replica_status)
        self.assertTrue(capabilities.ServerCapabilities((8, 4, 0), "8.4.0").supports_show_replica_status)


if __name__ == "__main__":
    unittest.main()
