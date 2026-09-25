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

    @property
    def missing(self) -> list[str]:
        needed: list[str] = []
        if self.mysql_conn_mode == "ssh" and not self.ssh_host:
            needed.append("SSH_HOST")
        if not self.mysql_user:
            needed.append("MYSQL_USER")
        return needed


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
    )
