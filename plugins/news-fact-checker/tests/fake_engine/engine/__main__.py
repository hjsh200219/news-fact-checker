"""Fake `python3 -m engine <url>` for network-free adapter tests.

Behaviour is driven by env so the adapter's exit-code/verdict branching and the
status parser can be exercised without any network:

  FAKE_ENGINE_SCENARIO ∈ {
    strong_ok, weak_ok, suspect_ok, auth_required, not_found,
    blocked, rate_limited, unknown, fatal, hang, unknown_verdict, phrase_variant
  }
  FAKE_ENGINE_SLEEP   seconds to sleep before responding (for the timeout test)

stdout = body · stderr = human diagnostics + the structured `[engine]` line.
"""
from __future__ import annotations

import os
import sys
import time

BODY = "본문 시작. 정부는 오늘 정책을 발표했다. 관련 수치는 다음과 같다. 본문 끝."


def emit(ok: bool, verdict: str, *, body: str = "", exit_code: int = 0,
         must_mcp: bool = False, routes: list[str] | None = None,
         grid_exhausted: bool = False, stop_reason: str | None = None,
         phrase_variant: bool = False) -> int:
    if body:
        sys.stdout.write(body)
    # structured contract line (the parser keys on this)
    print(f"[engine] ok={'true' if ok else 'false'} verdict={verdict}", file=sys.stderr)
    if stop_reason:
        print(f"stop_reason={stop_reason}", file=sys.stderr)
    if grid_exhausted:
        print("grid_exhausted=True", file=sys.stderr)
    if must_mcp:
        # phrasing around the fields may drift between engine versions (AC-11) —
        # the structured tokens stay stable.
        if phrase_variant:
            print(">>> escalation needed: must_invoke_playwright_mcp = TRUE <<<", file=sys.stderr)
        else:
            print("must_invoke_playwright_mcp = TRUE", file=sys.stderr)
    for r in (routes or []):
        print(f"  • {r}", file=sys.stderr)
    return exit_code


def main() -> int:
    scenario = os.environ.get("FAKE_ENGINE_SCENARIO", "strong_ok")
    sleep_s = float(os.environ.get("FAKE_ENGINE_SLEEP", "0") or "0")
    if sleep_s > 0:
        time.sleep(sleep_s)

    if scenario == "strong_ok":
        return emit(True, "strong_ok", body=BODY, exit_code=0)
    if scenario == "weak_ok":
        return emit(True, "weak_ok", body=BODY, exit_code=0)
    if scenario == "suspect_ok":
        # exit 1 but body IS present — adapter must keep the body, not escalate.
        return emit(False, "suspect_ok", body=BODY, exit_code=1, must_mcp=True)
    if scenario == "auth_required":
        return emit(False, "auth_required", exit_code=1)
    if scenario == "not_found":
        return emit(False, "not_found", exit_code=1)
    if scenario == "blocked":
        return emit(False, "blocked", exit_code=1, must_mcp=True,
                    routes=["playwright: navigate + capture /api", "tls: retry impersonation"])
    if scenario == "rate_limited":
        # 429 — non-terminal; untried routes must survive to the caller (AC-13).
        return emit(False, "rate_limited", exit_code=1,
                    routes=["backoff: retry after delay", "mcp: playwright fallback"])
    if scenario == "unknown":
        return emit(False, "unknown", exit_code=1, must_mcp=True, routes=["mcp: playwright"])
    if scenario == "phrase_variant":
        return emit(False, "blocked", exit_code=1, must_mcp=True,
                    routes=["playwright: navigate"], phrase_variant=True)
    if scenario == "unknown_verdict":
        # an out-of-vocabulary verdict token → parser must flag compat failure.
        return emit(False, "teleported_away", exit_code=1)
    if scenario == "drift_no_line":
        # engine dropped its structured `[engine]` line but still exits 0 — the
        # parser must flag compat failure, NOT report empty-verdict success (H-2).
        sys.stdout.write(BODY)
        print("fetched ok (new human-only format, no machine line)", file=sys.stderr)
        return 0
    if scenario == "spaced_escalation":
        # spacing/casing drift around the escalation flag must still be detected (M-1).
        sys.stdout.write("")
        print("[engine] ok=false verdict=blocked", file=sys.stderr)
        print("must_invoke_playwright_mcp = True", file=sys.stderr)
        print("  • playwright: navigate", file=sys.stderr)
        return 1
    if scenario == "hang":
        time.sleep(30)
        return emit(True, "strong_ok", body=BODY, exit_code=0)
    if scenario == "fatal":
        print("Traceback (most recent call last):", file=sys.stderr)
        print("RuntimeError: engine exploded", file=sys.stderr)
        return 2

    return emit(True, "strong_ok", body=BODY, exit_code=0)


if __name__ == "__main__":
    sys.exit(main())
