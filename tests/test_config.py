import unittest
from unittest.mock import patch

from mysql_diag_mcp.config import load_settings


def _env(**overrides: str):
    base = {
        "SSH_HOST": "",
        "SSH_JUMP": "",
        "SSH_KEY": "",
        "MYSQL_CONN_MODE": "",
        "MYSQL_USER": "mcp_diag",
        "MYSQL_PASSWORD": "",
        "MYSQL_SOCKET": "",
        "MYSQL_HOST": "",
        "MYSQL_PORT": "",
        "MYSQL_SSL_MODE": "",
        "MYSQL_SSL_CA": "",
        "MYSQL_SSL_CERT": "",
        "MYSQL_SSL_KEY": "",
        "MCP_TRANSPORT": "",
        "MCP_HOST": "",
        "MCP_PORT": "",
        "MCP_ALLOWED_HOSTS": "",
        "MCP_ALLOWED_ORIGINS": "",
        "MCP_AUTH_TOKENS": "",
        "MCP_ALLOW_NO_AUTH": "",
    }
    base.update(overrides)
    return base


class DefaultsTests(unittest.TestCase):
    def test_defaults_to_stdio_no_auth_required(self):
        with patch.dict("os.environ", _env(), clear=True):
            cfg = load_settings()
        self.assertEqual(cfg.mcp_transport, "stdio")
        self.assertEqual(cfg.mcp_host, "127.0.0.1")
        self.assertEqual(cfg.mcp_port, 8000)
        self.assertIsNone(cfg.network_auth_error)


class NetworkAuthValidationTests(unittest.TestCase):
    def test_network_transport_without_tokens_is_refused(self):
        with patch.dict("os.environ", _env(MCP_TRANSPORT="streamable-http"), clear=True):
            cfg = load_settings()
        self.assertIsNotNone(cfg.network_auth_error)
        self.assertIn("MCP_AUTH_TOKENS", cfg.network_auth_error)

    def test_network_transport_with_tokens_is_allowed(self):
        with patch.dict(
            "os.environ",
            _env(MCP_TRANSPORT="streamable-http", MCP_AUTH_TOKENS="tok:alice"),
            clear=True,
        ):
            cfg = load_settings()
        self.assertIsNone(cfg.network_auth_error)

    def test_network_transport_with_explicit_opt_out_is_allowed(self):
        with patch.dict(
            "os.environ",
            _env(MCP_TRANSPORT="streamable-http", MCP_ALLOW_NO_AUTH="true"),
            clear=True,
        ):
            cfg = load_settings()
        self.assertIsNone(cfg.network_auth_error)

    def test_sse_transport_also_requires_auth(self):
        with patch.dict("os.environ", _env(MCP_TRANSPORT="sse"), clear=True):
            cfg = load_settings()
        self.assertIsNotNone(cfg.network_auth_error)


class ListParsingTests(unittest.TestCase):
    def test_allowed_hosts_and_origins_parsed_as_tuples(self):
        with patch.dict(
            "os.environ",
            _env(MCP_ALLOWED_HOSTS="a.example.com, b.example.com", MCP_ALLOWED_ORIGINS="https://a.example.com"),
            clear=True,
        ):
            cfg = load_settings()
        self.assertEqual(cfg.mcp_allowed_hosts, ("a.example.com", "b.example.com"))
        self.assertEqual(cfg.mcp_allowed_origins, ("https://a.example.com",))

    def test_empty_allowed_hosts_is_empty_tuple(self):
        with patch.dict("os.environ", _env(), clear=True):
            cfg = load_settings()
        self.assertEqual(cfg.mcp_allowed_hosts, ())


if __name__ == "__main__":
    unittest.main()
