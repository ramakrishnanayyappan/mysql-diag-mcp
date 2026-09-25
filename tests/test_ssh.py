import unittest

from mysql_diag_mcp.config import Settings
from mysql_diag_mcp.ssh import _client_cnf, _remote_mysql_script, run_mysql, ssh_base_args, ssh_command


def _settings(**overrides: object) -> Settings:
    base = dict(
        ssh_host="user@dbhost",
        ssh_jump="user@bastion",
        ssh_key="/tmp/id_ed25519",
        mysql_conn_mode="ssh",
        mysql_user="mcp_diag",
        mysql_password="s3cret",
        mysql_socket="/var/run/mysqld/mysqld.sock",
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


class SshArgTests(unittest.TestCase):
    def test_jump_sshs_bastion_then_db_host(self):
        args = ssh_base_args(_settings())
        self.assertEqual(args[0], "ssh")
        self.assertIn("BatchMode=yes", args)
        self.assertIn("ControlMaster=auto", args)
        self.assertTrue(any(a.startswith("ControlPath=/tmp/mdm-cm/") for a in args))
        self.assertNotIn("-J", args)
        self.assertIn("-i", args)
        self.assertEqual(args[-1], "user@bastion")
        cmd = ssh_command(_settings())
        self.assertEqual(cmd[-3:], ["user@dbhost", "bash", "-s"])
        self.assertIn("user@dbhost", cmd)
        self.assertIn("user@bastion", cmd)

    def test_no_jump_goes_straight_to_host(self):
        args = ssh_base_args(_settings(ssh_jump=None, ssh_key=None))
        self.assertNotIn("-J", args)
        self.assertNotIn("-i", args)
        self.assertEqual(args[-1], "user@dbhost")
        self.assertEqual(ssh_command(_settings(ssh_jump=None, ssh_key=None))[-2:], ["bash", "-s"])

    def test_password_not_plaintext_in_remote_script(self):
        script = _remote_mysql_script(_settings(), "SHOW FULL PROCESSLIST")
        self.assertNotIn("s3cret", script)
        self.assertIn("defaults-extra-file", script)
        self.assertIn('> "$cnf"', script)
        self.assertIn("SHOW FULL PROCESSLIST", script)

    def test_socket_in_client_cnf(self):
        cnf = _client_cnf(_settings())
        self.assertIn("socket=/var/run/mysqld/mysqld.sock", cnf)
        self.assertIn("user=mcp_diag", cnf)

    def test_missing_settings_do_not_ssh(self):
        result = run_mysql("SELECT 1", settings=_settings(ssh_host=None, mysql_user=None))
        self.assertFalse(result["ok"])
        self.assertIn("SSH_HOST", result["error"])
        self.assertIn("MYSQL_USER", result["error"])


if __name__ == "__main__":
    unittest.main()
