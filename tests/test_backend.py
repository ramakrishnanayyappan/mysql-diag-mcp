import unittest
from unittest.mock import patch

from mysql_diag_mcp import backend
from mysql_diag_mcp.config import Settings


def _settings(**overrides: object) -> Settings:
    base = dict(
        ssh_host="user@dbhost",
        ssh_jump=None,
        ssh_key=None,
        mysql_conn_mode="ssh",
        mysql_user="mcp_diag",
        mysql_password=None,
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
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


class BackendDispatchTests(unittest.TestCase):
    @patch("mysql_diag_mcp.backend.ssh.run_mysql")
    @patch("mysql_diag_mcp.backend.direct.run_mysql")
    def test_ssh_mode_uses_ssh_backend(self, direct_run, ssh_run):
        ssh_run.return_value = {"ok": True, "rows": []}
        backend.run_mysql("SELECT 1", settings=_settings(mysql_conn_mode="ssh"))
        ssh_run.assert_called_once()
        direct_run.assert_not_called()

    @patch("mysql_diag_mcp.backend.ssh.run_mysql")
    @patch("mysql_diag_mcp.backend.direct.run_mysql")
    def test_direct_mode_uses_direct_backend(self, direct_run, ssh_run):
        direct_run.return_value = {"ok": True, "rows": []}
        backend.run_mysql("SELECT 1", settings=_settings(mysql_conn_mode="direct"))
        direct_run.assert_called_once()
        ssh_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
