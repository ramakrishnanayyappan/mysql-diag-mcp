"""Guard mysql_explain so user text cannot become stacked or mutating SQL."""

from __future__ import annotations

import re

_ALLOWED_START = re.compile(r"(?is)\A\s*(select|show)\b")
_BLOCKED = re.compile(
    r"""(?is)
    \b(
        insert|update|delete|drop|alter|truncate|grant|revoke|create|replace|
        load|call|do|handler|lock\s+tables|unlock\s+tables|rename|prepare|
        execute|deallocate|shutdown|kill
    )\b
    |
    \binto\s+(outfile|dumpfile)\b
    |
    \bset\s+global\b
    |
    \bset\s+session\b
    |
    --
    |
    /\*
    |
    \bxp_
    """,
    re.VERBOSE,
)


class ExplainRejected(ValueError):
    pass


def validate_explain_sql(sql: str) -> str:
    if not sql or not sql.strip():
        raise ExplainRejected("statement is empty")

    stripped = sql.strip()
    if stripped.endswith(";"):
        stripped = stripped[:-1].rstrip()

    if ";" in stripped:
        raise ExplainRejected("stacked statements are not allowed")

    if not _ALLOWED_START.match(stripped):
        raise ExplainRejected("only a single SELECT or SHOW statement is allowed")

    if _BLOCKED.search(stripped):
        raise ExplainRejected("statement contains a blocked keyword or comment")

    return stripped
