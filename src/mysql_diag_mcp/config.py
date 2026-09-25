"""Load connection settings from the environment (and optional .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env", override=True)
load_dotenv(override=False)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return int(raw)


def _env_opt(name: str) -> str | None:
    raw = os.environ.get(name, "").strip()
    return raw or None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _env_list(name: str) -> tuple[str, ...]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return ()
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    ssh_host: str | None
    ssh_jump: str | None
    ssh_key: str | None
    mysql_conn_mode: str
    mysql_user: str | None
    mysql_password: str | None
    mysql_socket: str | None
    mysql_host: str
    mysql_port: int
    mysql_timeout_sec: int
    mysql_connect_timeout_sec: int
    mysql_max_rows: int
    mysql_ssl_mode: str
    mysql_ssl_ca: str | None
    mysql_ssl_cert: str | None
    mysql_ssl_key: str | None
    info_truncate: int
    innodb_section_truncate: int
    mcp_transport: str
    mcp_host: str
    mcp_port: int
    mcp_allowed_hosts: tuple[str, ...]
    mcp_allowed_origins: tuple[str, ...]
    mcp_auth_tokens: str | None
    mcp_allow_no_auth: bool

    @property
    def missing(self) -> list[str]:
        needed: list[str] = []
        if self.mysql_conn_mode == "ssh" and not self.ssh_host:
            needed.append("SSH_HOST")
        if not self.mysql_user:
            needed.append("MYSQL_USER")
        return needed

    @property
    def network_auth_error(self) -> str | None:
        """None if it's safe to start; otherwise the reason to refuse.

        Network transports default to requiring MCP_AUTH_TOKENS so a shared
        server isn't accidentally exposed unauthenticated; MCP_ALLOW_NO_AUTH
        is an explicit opt-out for ops relying on network-level controls
        instead.
        """
        if self.mcp_transport == "stdio":
            return None
        if self.mcp_auth_tokens or self.mcp_allow_no_auth:
            return None
        return (
            "Refusing to start an unauthenticated network MCP server. Set "
            "MCP_AUTH_TOKENS (e.g. token1:alice,token2:bob) or explicitly "
            "set MCP_ALLOW_NO_AUTH=true if you are relying on network-level "
            "access controls instead."
        )


def load_settings() -> Settings:
    return Settings(
        ssh_host=_env_opt("SSH_HOST"),
        ssh_jump=_env_opt("SSH_JUMP"),
        ssh_key=_env_opt("SSH_KEY"),
        mysql_conn_mode=(_env_opt("MYSQL_CONN_MODE") or "ssh").lower(),
        mysql_user=_env_opt("MYSQL_USER"),
        mysql_password=_env_opt("MYSQL_PASSWORD"),
        mysql_socket=_env_opt("MYSQL_SOCKET"),
        mysql_host=_env_opt("MYSQL_HOST") or "127.0.0.1",
        mysql_port=_env_int("MYSQL_PORT", 3306),
        mysql_timeout_sec=_env_int("MYSQL_TIMEOUT_SEC", 8),
        mysql_connect_timeout_sec=_env_int("MYSQL_CONNECT_TIMEOUT_SEC", 5),
        mysql_max_rows=_env_int("MYSQL_MAX_ROWS", 200),
        mysql_ssl_mode=(_env_opt("MYSQL_SSL_MODE") or "disabled").lower(),
        mysql_ssl_ca=_env_opt("MYSQL_SSL_CA"),
        mysql_ssl_cert=_env_opt("MYSQL_SSL_CERT"),
        mysql_ssl_key=_env_opt("MYSQL_SSL_KEY"),
        info_truncate=_env_int("INFO_TRUNCATE", 512),
        innodb_section_truncate=_env_int("INNODB_SECTION_TRUNCATE", 8000),
        mcp_transport=(_env_opt("MCP_TRANSPORT") or "stdio").lower(),
        mcp_host=_env_opt("MCP_HOST") or "127.0.0.1",
        mcp_port=_env_int("MCP_PORT", 8000),
        mcp_allowed_hosts=_env_list("MCP_ALLOWED_HOSTS"),
        mcp_allowed_origins=_env_list("MCP_ALLOWED_ORIGINS"),
        mcp_auth_tokens=_env_opt("MCP_AUTH_TOKENS"),
        mcp_allow_no_auth=_env_bool("MCP_ALLOW_NO_AUTH", False),
    )
