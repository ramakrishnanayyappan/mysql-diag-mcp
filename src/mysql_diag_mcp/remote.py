"""Bearer-token auth and HTTP serving for the streamable-http/sse transports.

Deliberately bypasses the MCP SDK's OAuth-shaped auth scaffolding
(mcp.server.auth: AuthSettings/TokenVerifier) -- that machinery requires a
full issuer_url and is built for running as an OAuth authorization/resource
server, more than a shared internal diagnostics tool needs. Instead this
wraps the plain ASGI app the SDK already exposes (FastMCP.streamable_http_app()
/ sse_app()) with a small bearer-token check.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from mysql_diag_mcp.config import Settings

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

log = logging.getLogger("mysql_diag_mcp")


def parse_tokens(raw: str) -> dict[str, str]:
    """"token1:alice,token2:bob" or bare "token1,token2" -> {token: label}."""
    tokens: dict[str, str] = {}
    if not raw:
        return tokens
    for i, part in enumerate(p.strip() for p in raw.split(",")):
        if not part:
            continue
        if ":" in part:
            token, _, label = part.partition(":")
            token, label = token.strip(), label.strip()
        else:
            token, label = part, ""
        if token:
            tokens[token] = label or f"token-{i + 1}"
    return tokens


async def _send_json_error(send, status: int, message: str) -> None:
    body = f'{{"error": "{message}"}}'.encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"www-authenticate", b"Bearer"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _bearer_token(scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name.lower() == b"authorization":
            text = value.decode("latin-1")
            if text.lower().startswith("bearer "):
                return text[7:].strip()
    return None


class BearerTokenMiddleware:
    """Reject with 401 unless Authorization: Bearer <token> matches a configured
    token. On success, attaches the resolved identity to scope["state"] under
    "mcp_diag_identity" for RequestLogMiddleware/tool handlers to read."""

    def __init__(self, app, tokens: dict[str, str]):
        self.app = app
        self.tokens = tokens

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        token = _bearer_token(scope)
        identity = self.tokens.get(token) if token else None
        if identity is None:
            await _send_json_error(send, 401, "missing or invalid bearer token")
            return

        scope.setdefault("state", {})["mcp_diag_identity"] = identity
        await self.app(scope, receive, send)


class RequestLogMiddleware:
    """Logs method, path, resolved identity, status, and duration for every
    request -- the audit trail once multiple people share one DB credential."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        status_holder: dict[str, int] = {}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        await self.app(scope, receive, send_wrapper)

        identity = scope.get("state", {}).get("mcp_diag_identity", "-")
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        log.info(
            "%s %s identity=%s status=%s duration_ms=%s",
            scope.get("method", "-"),
            scope.get("path", "-"),
            identity,
            status_holder.get("status", "-"),
            duration_ms,
        )


def build_app(mcp: "FastMCP", cfg: Settings) -> Any:
    app = mcp.sse_app() if cfg.mcp_transport == "sse" else mcp.streamable_http_app()
    app = RequestLogMiddleware(app)
    if cfg.mcp_auth_tokens:
        app = BearerTokenMiddleware(app, parse_tokens(cfg.mcp_auth_tokens))
    return app


def serve(mcp: "FastMCP", cfg: Settings) -> None:
    import uvicorn

    app = build_app(mcp, cfg)
    log.info("serving %s on %s:%s", cfg.mcp_transport, cfg.mcp_host, cfg.mcp_port)
    uvicorn.run(app, host=cfg.mcp_host, port=cfg.mcp_port, log_level="info")
