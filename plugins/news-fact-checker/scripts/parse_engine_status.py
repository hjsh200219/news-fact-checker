#!/usr/bin/env python3
"""parse_engine_status.py — structured status from a single engine invocation.

The insane-search engine emits human diagnostics on stderr; it is an external
dependency we do not own, so the adapter must recover a MACHINE contract from
that one call (no second `--json` fetch — that mutates engine learning state).

This module isolates and *validates* that recovery so it is unit-testable and so
a phrasing change surfaces as an explicit compatibility outcome instead of a
silently-empty verdict (M-1 / AC-11):

  * verdict is validated against a known enum; an unrecognised token → parse_ok
    False + stop_reason "status_unparsed" (explicit compat failure).
  * status_source records whether the structured `[engine] ok= verdict=` line was
    found ("engine_line") or the fields were inferred from the exit code
    ("exit_code_fallback").

Emits a single JSON object (schema_version 1) on stdout.

CLI:
  parse_engine_status.py <exit_code> <engine_home> <stderr_file>
                         [--engine-version V] [--engine-commit SHA]
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any

STATUS_SCHEMA_VERSION = 1

# lowercase verdict vocabulary the engine is known to emit (fetch-harness.md).
# NOTE: "" is deliberately NOT a known verdict — an empty verdict is only legitimate
# on an engine-fatal exit (code 2, no structured line); anywhere else it is drift.
KNOWN_VERDICTS = {
    "strong_ok", "weak_ok", "suspect_ok",
    "auth_required", "not_found", "challenge", "blocked",
    "rate_limited", "unknown",
}


def parse_status(code: int, home: str, err: str,
                 engine_version: str | None = None,
                 engine_commit: str | None = None) -> dict[str, Any]:
    ok: bool | None = None
    verdict = ""
    status_source = "exit_code_fallback"
    parse_ok = True

    m = re.search(r"\[engine\]\s+ok=(\w+)\s+verdict=(\S+)", err)
    if m:
        ok = (m.group(1).lower() == "true")
        verdict = m.group(2).lower().strip(".,)")  # engine emits lowercase
        status_source = "engine_line"
        if verdict not in KNOWN_VERDICTS:
            parse_ok = False  # out-of-vocabulary verdict → explicit compat failure
    else:
        # No structured line. Legitimate ONLY on an engine-fatal exit (code 2);
        # on a 0/1 exit a status line was expected, so its absence is drift/compat
        # failure — never silently treat empty verdict as success (M-1 / AC-11).
        ok = (code == 0)
        if code != 2:
            parse_ok = False

    grid_exhausted = bool(re.search(r"grid_exhausted\s*=\s*true", err, flags=re.I))
    sr = re.search(r"stop_reason\s*=\s*(\S+)", err)
    if sr:
        stop_reason = sr.group(1)
    elif not parse_ok:
        stop_reason = "status_unparsed"
    elif ok:
        stop_reason = "success"
    elif code == 2:
        stop_reason = "error"
    else:
        stop_reason = ""

    routes = re.findall(r"^\s*•\s+(.*)$", err, flags=re.M)
    must_mcp = bool(re.search(r"must_invoke_playwright_mcp\s*=\s*true", err, flags=re.I))

    return {
        "schema_version": STATUS_SCHEMA_VERSION,
        "exit": code,
        "ok": ok,
        "parse_ok": parse_ok,
        "status_source": status_source,
        "verdict": verdict,
        "grid_exhausted": grid_exhausted,
        "stop_reason": stop_reason,
        "untried_routes": routes,
        "must_invoke_playwright_mcp": must_mcp,
        "engine_home": home or None,
        "engine_version": engine_version or None,
        "engine_commit": engine_commit or None,
    }


def main(argv: list[str]) -> int:
    ver = com = None
    pos: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--engine-version" and i + 1 < len(argv):
            ver = argv[i + 1]; i += 2; continue
        if a == "--engine-commit" and i + 1 < len(argv):
            com = argv[i + 1]; i += 2; continue
        pos.append(a); i += 1
    if len(pos) != 3:
        print("usage: parse_engine_status.py <exit_code> <engine_home> <stderr_file> "
              "[--engine-version V] [--engine-commit SHA]", file=sys.stderr)
        return 2
    try:
        code = int(pos[0])
    except ValueError:
        print("exit_code must be an integer", file=sys.stderr)
        return 2
    home = pos[1]
    try:
        err = open(pos[2], encoding="utf-8", errors="ignore").read()
    except OSError:
        err = ""
    status = parse_status(code, home, err, engine_version=ver, engine_commit=com)
    print("NFC_STATUS " + json.dumps(status, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
