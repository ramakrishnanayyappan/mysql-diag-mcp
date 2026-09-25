"""Parse mysql --batch TSV and SHOW ENGINE INNODB STATUS dumps."""

from __future__ import annotations

import re
from typing import Any

_SECTION_HEADER = re.compile(
    r"^-{3,}\n([A-Z][A-Z0-9 /_-]*)\n-{3,}\n",
    re.MULTILINE,
)

KEEP_INNODB_SECTIONS = (
    "SEMAPHORES",
    "LATEST DETECTED DEADLOCK",
    "TRANSACTIONS",
    "FILE I/O",
    "LOG",
    "BUFFER POOL AND MEMORY",
    "ROW OPERATIONS",
)


_ESCAPES = {"0": "\0", "n": "\n", "t": "\t", "r": "\r", "\\": "\\"}


def _unescape(value: str) -> str:
    """Undo mysql --batch's backslash-escaping of NUL/tab/newline/CR/backslash.

    Without --raw, mysql escapes these so every row stays on one output line
    (see the comment in ssh.py's _remote_mysql_script for why --raw is not used).
    """
    if "\\" not in value:
        return value
    out: list[str] = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            out.append(_ESCAPES.get(value[i + 1], value[i + 1]))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def parse_tsv(text: str, max_rows: int) -> dict[str, Any]:
    lines = [line for line in text.splitlines() if line != ""]
    if not lines:
        return {"columns": [], "rows": [], "row_count": 0, "truncated": False}

    headers = [_unescape(h) for h in lines[0].split("\t")]
    width = len(headers)
    rows: list[dict[str, str]] = []
    source_count = max(0, len(lines) - 1)

    for line in lines[1:]:
        if len(rows) >= max_rows:
            break
        parts = line.split("\t")
        if len(parts) > width:
            parts = parts[: width - 1] + ["\t".join(parts[width - 1 :])]
        elif len(parts) < width:
            parts.extend([""] * (width - len(parts)))
        parts = [_unescape(p) for p in parts]
        rows.append(dict(zip(headers, parts, strict=True)))

    return {
        "columns": headers,
        "rows": rows,
        "row_count": len(rows),
        "truncated": source_count > len(rows),
        "source_row_count": source_count,
    }


def truncate_field(rows: list[dict[str, str]], field: str, limit: int) -> None:
    if limit <= 0:
        return
    for row in rows:
        value = row.get(field)
        if value and len(value) > limit:
            row[field] = value[:limit] + f"…[truncated {len(value) - limit} chars]"


def parse_innodb_status(status_blob: str, section_limit: int) -> dict[str, Any]:
    """Split InnoDB status into named sections; keep the spike-relevant ones."""
    matches = list(_SECTION_HEADER.finditer(status_blob))
    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        name = " ".join(match.group(1).split())
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(status_blob)
        body = status_blob[start:end].strip()
        if section_limit and len(body) > section_limit:
            body = body[:section_limit] + f"\n…[truncated {len(body) - section_limit} chars]"
        sections[name] = body

    kept = {name: sections[name] for name in KEEP_INNODB_SECTIONS if name in sections}
    history = None
    txn = kept.get("TRANSACTIONS") or sections.get("TRANSACTIONS", "")
    hist_match = re.search(r"History list length\s+(\d+)", txn)
    if hist_match:
        history = int(hist_match.group(1))

    return {
        "history_list_length": history,
        "sections": kept,
        "section_names": list(sections.keys()),
    }


def status_map(rows: list[dict[str, str]]) -> dict[str, str]:
    """SHOW GLOBAL STATUS / VARIABLES -> {name: value} (case-insensitive keys)."""
    out: dict[str, str] = {}
    for row in rows:
        name = row.get("Variable_name") or row.get("VARIABLE_NAME") or ""
        value = row.get("Value") or row.get("VARIABLE_VALUE") or ""
        if name:
            out[name] = value
    return out


def pick_keys(mapping: dict[str, str], keys: tuple[str, ...]) -> dict[str, str]:
    wanted = {k.lower(): k for k in keys}
    out: dict[str, str] = {}
    for name, value in mapping.items():
        canonical = wanted.get(name.lower())
        if canonical:
            out[canonical] = value
    return out


def to_number(value: str) -> int | float | None:
    try:
        if "." in value:
            return float(value)
        return int(value)
    except (TypeError, ValueError):
        return None
