"""SSH ProxyJump + remote mysql CLI with ControlMaster reuse."""

from __future__ import annotations

import base64
import logging
import shlex
import subprocess
from pathlib import Path
from typing import Any

from mysql_diag_mcp.config import Settings, load_settings
from mysql_diag_mcp.parse import parse_tsv

log = logging.getLogger("mysql_diag_mcp")

# macOS sun_path is 104 bytes; /var/folders/.../T is too long with %C.
_CONTROL_DIR = Path("/tmp/mdm-cm")


def ssh_base_args(settings: Settings) -> list[str]:
    """SSH to the bastion when SSH_JUMP is set; otherwise straight to SSH_HOST.

    We do not use ProxyJump. Many DB hosts accept keys/GSSAPI only from the
    jump box, not from the laptop.
    """
    if not settings.ssh_host:
        raise ValueError("SSH_HOST is not set")

    first_hop = settings.ssh_jump or settings.ssh_host
    _CONTROL_DIR.mkdir(mode=0o700, exist_ok=True)
    args = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={settings.mysql_connect_timeout_sec}",
        "-o",
        "ControlMaster=auto",
        "-o",
        f"ControlPath={_CONTROL_DIR}/%C",
        "-o",
        "ControlPersist=60",
        "-o",
        "ServerAliveInterval=5",
        "-o",
        "ServerAliveCountMax=2",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]
    if settings.ssh_key:
        args.extend(["-i", settings.ssh_key, "-o", "IdentitiesOnly=yes"])
    args.append(first_hop)
    return args


def ssh_command(settings: Settings) -> list[str]:
    cmd = ssh_base_args(settings)
    if settings.ssh_jump:
        cmd.extend(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                f"ConnectTimeout={settings.mysql_connect_timeout_sec}",
                "-o",
                "StrictHostKeyChecking=accept-new",
                settings.ssh_host,
            ]
        )
    cmd.extend(["bash", "-s"])
    return cmd


def _client_cnf(settings: Settings) -> str:
    lines = ["[client]", f"user={settings.mysql_user}"]
    if settings.mysql_password:
        lines.append(f"password={settings.mysql_password}")
    if settings.mysql_socket:
        lines.append(f"socket={settings.mysql_socket}")
    else:
        lines.append(f"host={settings.mysql_host}")
        lines.append(f"port={settings.mysql_port}")
    return "\n".join(lines) + "\n"


def _remote_mysql_script(settings: Settings, sql: str) -> str:
    payload = base64.b64encode(_client_cnf(settings).encode("utf-8")).decode("ascii")
    mysql = (
        "mysql --defaults-extra-file=\"$cnf\" --batch --raw "
        f"--connect-timeout={settings.mysql_connect_timeout_sec} "
        f"-e {shlex.quote(sql)}"
    )
    decode = f"printf '%s' {shlex.quote(payload)} | (base64 -d 2>/dev/null || base64 -D) > \"$cnf\""
    return "\n".join(
        [
            "set -euo pipefail",
            "cnf=$(mktemp)",
            "trap 'rm -f \"$cnf\"' EXIT",
            "umask 077",
            decode,
            mysql,
        ]
    )


def _run_ssh(settings: Settings, remote_script: str, *, timeout: int) -> subprocess.CompletedProcess[str]:
    cmd = ssh_command(settings)
    log.debug("ssh cmd=%s", cmd)
    return subprocess.run(
        cmd,
        input=remote_script,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        start_new_session=True,
    )


def run_mysql(
    sql: str,
    *,
    settings: Settings | None = None,
    max_rows: int | None = None,
    timeout_sec: int | None = None,
) -> dict[str, Any]:
    cfg = settings or load_settings()
    missing = cfg.missing
    if missing:
        return {
            "ok": False,
            "error": (
                "Missing required settings: "
                + ", ".join(missing)
                + ". Copy .env.example to .env and fill SSH_HOST / MYSQL_USER."
            ),
        }

    timeout = timeout_sec or (cfg.mysql_connect_timeout_sec + cfg.mysql_timeout_sec + 5)
    script = _remote_mysql_script(cfg, sql)
    try:
        proc = _run_ssh(cfg, script, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"SSH/mysql timed out after {timeout}s"}
    except FileNotFoundError:
        return {"ok": False, "error": "ssh binary not found on this machine"}

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        lowered = err.lower()
        if "mysql: command not found" in lowered or "mysql: not found" in lowered:
            err += (
                " — install the mysql client on the DB host, or ensure it is on PATH "
                "for the SSH user."
            )
        return {"ok": False, "error": err, "exit_code": proc.returncode}

    parsed = parse_tsv(proc.stdout, max_rows if max_rows is not None else cfg.mysql_max_rows)
    parsed["ok"] = True
    if proc.stderr.strip():
        parsed["stderr"] = proc.stderr.strip()
    return parsed
