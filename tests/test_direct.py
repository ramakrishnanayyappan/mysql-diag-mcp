import unittest
from unittest.mock import MagicMock, patch

import pymysql

from mysql_diag_mcp import direct
from mysql_diag_mcp.config import Settings


def _settings(**overrides: object) -> Settings:
    base = dict(
        ssh_host=None,
        ssh_jump=None,
        ssh_key=None,
        mysql_conn_mode="direct",
        mysql_user="mcp_diag",
        mysql_password="s3cret",
        mysql_socket=None,
        mysql_host="127.0.0.1",
        mysql_port=3306,
        mysql_timeout_sec=8,
        mysql_connect_timeout_sec=5,
        mysql_max_rows=200,
        mysql_ssl_mode="disabled",
        mysql_ssl_ca=None,
        mysql_ssl_cert=None,
        mysql_ssl_key=None,
        info_truncate=512,
        innodb_section_truncate=8000,
        mcp_transport="stdio",
        mcp_host="127.0.0.1",
        mcp_port=8000,
        mcp_allowed_hosts=(),
        mcp_allowed_origins=(),
        mcp_auth_tokens=None,
        mcp_allow_no_auth=False,
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _fake_conn(rows):
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.description = [("a",), ("b",)] if rows else []
    remaining = list(rows)

    def fetchmany(limit):
        chunk = remaining[:limit]
        del remaining[:limit]
        return chunk

    cursor.fetchmany.side_effect = fetchmany
    cursor.fetchone.side_effect = lambda: remaining.pop(0) if remaining else None

    conn = MagicMock()
    conn.open = True
    conn.cursor.return_value = cursor
    return conn


class RunMysqlTests(unittest.TestCase):
    def setUp(self):
        direct.reset_connection()

    def tearDown(self):
        direct.reset_connection()

    def test_missing_settings_short_circuits(self):
        result = direct.run_mysql("SELECT 1", settings=_settings(mysql_user=None))
        self.assertFalse(result["ok"])
        self.assertIn("MYSQL_USER", result["error"])

    @patch("mysql_diag_mcp.direct.pymysql.connect")
    def test_connect_kwargs_from_settings(self, mock_connect):
        mock_connect.return_value = _fake_conn([{"a": 1, "b": 2}])
        direct.run_mysql("SELECT 1", settings=_settings())
        _, kwargs = mock_connect.call_args
        self.assertEqual(kwargs["user"], "mcp_diag")
        self.assertEqual(kwargs["host"], "127.0.0.1")
        self.assertEqual(kwargs["port"], 3306)
        self.assertTrue(kwargs["ssl_disabled"])

    @patch("mysql_diag_mcp.direct.pymysql.connect")
    def test_returns_rows_and_shape(self, mock_connect):
        mock_connect.return_value = _fake_conn([{"a": 1, "b": 2}, {"a": 3, "b": 4}])
        result = direct.run_mysql("SELECT 1", settings=_settings())
        self.assertTrue(result["ok"])
        self.assertEqual(result["row_count"], 2)
        self.assertFalse(result["truncated"])

    @patch("mysql_diag_mcp.direct.pymysql.connect")
    def test_truncation_detected(self, mock_connect):
        mock_connect.return_value = _fake_conn([{"a": i, "b": i} for i in range(5)])
        result = direct.run_mysql("SELECT 1", settings=_settings(mysql_max_rows=2))
        self.assertTrue(result["ok"])
        self.assertEqual(result["row_count"], 2)
        self.assertTrue(result["truncated"])

    @patch("mysql_diag_mcp.direct.pymysql.connect")
    def test_reconnects_once_then_fails(self, mock_connect):
        good = _fake_conn([{"a": 1, "b": 2}])
        bad = MagicMock()
        bad.open = True
        bad.cursor.side_effect = pymysql.err.OperationalError("gone away")
        mock_connect.side_effect = [bad, bad]
        result = direct.run_mysql("SELECT 1", settings=_settings())
        self.assertFalse(result["ok"])
        self.assertIn("connection error", result["error"])
        self.assertEqual(mock_connect.call_count, 2)

    @patch("mysql_diag_mcp.direct.pymysql.connect")
    def test_non_operational_mysql_error_does_not_retry(self, mock_connect):
        bad = MagicMock()
        bad.open = True
        bad.cursor.side_effect = pymysql.err.ProgrammingError("syntax error")
        mock_connect.return_value = bad
        result = direct.run_mysql("SELECT 1", settings=_settings())
        self.assertFalse(result["ok"])
        self.assertEqual(mock_connect.call_count, 1)


if __name__ == "__main__":
    unittest.main()
