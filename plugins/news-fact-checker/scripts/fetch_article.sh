#!/usr/bin/env bash
# fetch_article.sh — thin single-invocation adapter over the insane-search engine.
#
#   fetch_article.sh <url> [extra engine args...]
#
# Behaviour (mirrors the plan fetch-harness):
#   * Resolve engine home (via $INSANE_SEARCH_HOME or resolve_engine.sh).
#   * `cd` into that home (the `engine` package parent) — else `No module named engine`.
#   * ONE default invocation: body -> stdout, engine status -> stderr, exit code preserved.
#     Never a second `--json` fetch (double-fetch mutates engine learning state).
#   * The engine already prints the R6 failure block to stderr on exit 1, so status is
#     parsed from that single call's stderr — no extra network hit.
#
# Output contract to the caller (the skill):
#   * stdout  = article body (may be empty on hard failure)
#   * stderr  = human diagnostics + one machine line:  NFC_STATUS <json>
#               json = {exit, ok, verdict, grid_exhausted, stop_reason,
#                       untried_routes[], must_invoke_playwright_mcp, engine_home}
#   * exit    = engine exit code (0 ok / 1 blocked-escalatable / 2 engine-fatal),
#               or 3 when the engine could not be resolved (DEGRADE).
set -uo pipefail

log() { printf '%s\n' "$*" >&2; }

[ $# -ge 1 ] || { log "usage: fetch_article.sh <url> [engine args...]"; exit 2; }
URL="$1"; shift || true

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- resolve engine home ---
HOME_DIR="${INSANE_SEARCH_HOME:-}"
if [ -z "$HOME_DIR" ] || [ ! -f "$HOME_DIR/engine/__main__.py" ]; then
  HOME_DIR="$(bash "$HERE/resolve_engine.sh" | tail -n1)"
fi
if [ -z "$HOME_DIR" ] || [ "$HOME_DIR" = "DEGRADE" ] || [ ! -f "$HOME_DIR/engine/__main__.py" ]; then
  log "fetch: engine unavailable (DEGRADE) — caller should use capability-reduced mode"
  printf 'NFC_STATUS {"exit":3,"ok":false,"verdict":"","grid_exhausted":false,"stop_reason":"engine_unavailable","untried_routes":[],"must_invoke_playwright_mcp":false,"engine_home":null}\n' >&2
  exit 3
fi

# --- single invocation (CWD = engine package parent) ---
ERRFILE="$(mktemp -t nfc_engine_err.XXXXXX)"
trap 'rm -f "$ERRFILE"' EXIT

# Note: the script does not run under `set -e`; capturing CODE and preserving it
# through to `exit $CODE` must never be aborted by a nonzero status parser or cat.
( cd "$HOME_DIR" && python3 -m engine "$URL" "$@" ) 2>"$ERRFILE"
CODE=$?

# stream the engine's own stderr to our stderr for visibility
cat "$ERRFILE" >&2 || true

# --- parse status from the single call's stderr (no second fetch) ---
{ python3 - "$CODE" "$HOME_DIR" "$ERRFILE" <<'PY' >&2
import sys, json, re
code = int(sys.argv[1]); home = sys.argv[2]
err = open(sys.argv[3], encoding="utf-8", errors="ignore").read()

ok = None; verdict = ""
m = re.search(r"\[engine\]\s+ok=(\w+)\s+verdict=(\S+)", err)
if m:
    ok = (m.group(1).lower() == "true")
    verdict = m.group(2).lower()   # engine emits lowercase (weak_ok, suspect_ok); normalize
if ok is None:
    ok = (code == 0)

grid_exhausted = bool(re.search(r"grid_exhausted=True", err))
sr = re.search(r"stop_reason=(\S+)", err)
stop_reason = sr.group(1) if sr else ("success" if ok else ("error" if code == 2 else ""))
routes = re.findall(r"^\s*•\s+(.*)$", err, flags=re.M)
must_mcp = ("must_invoke_playwright_mcp = TRUE" in err)

status = {
    "exit": code, "ok": ok, "verdict": verdict,
    "grid_exhausted": grid_exhausted, "stop_reason": stop_reason,
    "untried_routes": routes, "must_invoke_playwright_mcp": must_mcp,
    "engine_home": home,
}
print("NFC_STATUS " + json.dumps(status, ensure_ascii=False))
PY
} || true

exit $CODE
