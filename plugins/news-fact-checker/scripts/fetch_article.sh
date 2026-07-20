#!/usr/bin/env bash
# fetch_article.sh — thin single-invocation adapter over the insane-search engine.
#
#   fetch_article.sh <url> [extra engine args...]
#
# Behaviour (mirrors the plan fetch-harness):
#   * Enforce the network-destination policy (url_policy.py) BEFORE any request —
#     non-HTTP(S), userinfo, and private/loopback/link-local/metadata targets are
#     refused with a structured `unsafe_url` status and NO network hit (FR-4).
#   * Resolve engine home (via $INSANE_SEARCH_HOME or resolve_engine.sh).
#   * `cd` into that home (the `engine` package parent) — else `No module named engine`.
#   * ONE default invocation under a wall-clock timeout (FR-6 / M-5): body -> stdout,
#     engine status -> stderr, exit code preserved. Never a second `--json` fetch
#     (double-fetch mutates engine learning state).
#   * Recover a MACHINE status from that single call via parse_engine_status.py, which
#     validates the verdict enum and flags phrasing drift as an explicit compat failure.
#
# Output contract to the caller (the skill):
#   * stdout  = article body (may be empty on hard failure; suppressed on timeout —
#               a truncated partial body is never emitted as content)
#   * stderr  = human diagnostics + one machine line:  NFC_STATUS <json>
#               json = {schema_version, exit, ok, parse_ok, status_source, verdict,
#                       grid_exhausted, stop_reason, untried_routes[],
#                       must_invoke_playwright_mcp, engine_home,
#                       engine_version, engine_commit}
#   * exit    = 0 ok / 1 blocked-escalatable (incl. timeout) / 2 engine-fatal /
#               3 engine unresolved (DEGRADE) / 4 unsafe_url (policy reject).
set -uo pipefail

log() { printf '%s\n' "$*" >&2; }

[ $# -ge 1 ] || { log "usage: fetch_article.sh <url> [engine args...]"; exit 2; }
URL="$1"; shift || true

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FETCH_TIMEOUT="${NFC_FETCH_TIMEOUT:-90}"

# --- provenance (best-effort; surfaced in every status for reproducibility, L-1) ---
prov_field() {  # prov_field <home> <version|commit>
  local home="$1" key="$2" pf="$1/.nfc-provenance.json"
  if [ -f "$pf" ]; then
    python3 - "$pf" "$key" <<'PY' 2>/dev/null || true
import json, sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    v = d.get(sys.argv[2])
    if v:
        print(v)
except Exception:
    pass
PY
  elif [ "$key" = "commit" ] && command -v git >/dev/null 2>&1 && git -C "$home" rev-parse --git-dir >/dev/null 2>&1; then
    git -C "$home" rev-parse HEAD 2>/dev/null || true
  fi
}

emit_status() {  # emit_status <exit> <ok> <verdict> <stop_reason> <home>
  local ex="$1" ok="$2" verdict="$3" reason="$4" home="$5"
  local ver com
  ver="$(prov_field "$home" version)"; com="$(prov_field "$home" commit)"
  python3 - "$ex" "$ok" "$verdict" "$reason" "$home" "$ver" "$com" <<'PY' >&2
import json, sys
ex, ok, verdict, reason, home, ver, com = sys.argv[1:8]
status = {
    "schema_version": 1, "exit": int(ex), "ok": ok == "true", "parse_ok": True,
    "status_source": "adapter", "verdict": verdict, "grid_exhausted": False,
    "stop_reason": reason, "untried_routes": [], "must_invoke_playwright_mcp": False,
    "engine_home": home or None, "engine_version": ver or None, "engine_commit": com or None,
}
print("NFC_STATUS " + json.dumps(status, ensure_ascii=False))
PY
}

# --- 0. network-destination policy (pre-flight, no network) ---
if ! POLICY_JSON="$(python3 "$HERE/url_policy.py" "$URL" 2>/dev/null)"; then
  POLICY_REASON="$(printf '%s' "$POLICY_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("reason",""))' 2>/dev/null || true)"
  log "fetch: url rejected by policy — ${POLICY_REASON:-unsafe_url} (no network request made)"
  emit_status 4 false unsafe_url unsafe_url ""
  exit 4
fi

# --- resolve engine home ---
HOME_DIR="${INSANE_SEARCH_HOME:-}"
if [ -z "$HOME_DIR" ] || [ ! -f "$HOME_DIR/engine/__main__.py" ]; then
  HOME_DIR="$(bash "$HERE/resolve_engine.sh" | tail -n1)"
fi
if [ -z "$HOME_DIR" ] || [ "$HOME_DIR" = "DEGRADE" ] || [ ! -f "$HOME_DIR/engine/__main__.py" ]; then
  log "fetch: engine unavailable (DEGRADE) — caller should use capability-reduced mode"
  emit_status 3 false "" engine_unavailable ""
  exit 3
fi

# --- single invocation under a wall-clock timeout (CWD = engine package parent) ---
ERRFILE="$(mktemp -t nfc_engine_err.XXXXXX)"
BODYFILE="$(mktemp -t nfc_engine_body.XXXXXX)"
MARKER="$(mktemp -t nfc_engine_to.XXXXXX)"; rm -f "$MARKER"
trap 'rm -f "$ERRFILE" "$BODYFILE" "$MARKER"' EXIT

run_engine() {
  # Prefer coreutils timeout with process-group kill (--kill-after escalates to
  # SIGKILL so the engine's grandchildren — playwright/chromium, curl — are reaped).
  # Fall back to a setsid+watchdog that TERM/KILLs the whole process group.
  if command -v timeout >/dev/null 2>&1; then
    ( cd "$HOME_DIR" && timeout --kill-after=5 "$FETCH_TIMEOUT" python3 -m engine "$URL" "$@" ) >"$BODYFILE" 2>"$ERRFILE"
    return $?
  fi
  if command -v gtimeout >/dev/null 2>&1; then
    ( cd "$HOME_DIR" && gtimeout --kill-after=5 "$FETCH_TIMEOUT" python3 -m engine "$URL" "$@" ) >"$BODYFILE" 2>"$ERRFILE"
    return $?
  fi
  # Pure-bash watchdog. setsid makes the engine a process-group leader so we can
  # signal the whole tree; the marker is written BEFORE the kill to avoid a race.
  local setsid_bin=""
  command -v setsid >/dev/null 2>&1 && setsid_bin="setsid"
  ( cd "$HOME_DIR" && exec $setsid_bin python3 -m engine "$URL" "$@" ) >"$BODYFILE" 2>"$ERRFILE" &
  local pid=$!
  (
    sleep "$FETCH_TIMEOUT"
    : >"$MARKER"
    if [ -n "$setsid_bin" ]; then kill -TERM "-$pid" 2>/dev/null; else kill -TERM "$pid" 2>/dev/null; fi
    sleep 2
    if [ -n "$setsid_bin" ]; then kill -KILL "-$pid" 2>/dev/null; else kill -KILL "$pid" 2>/dev/null; fi
  ) &
  local wd=$!
  wait "$pid" 2>/dev/null; local rc=$?
  kill "$wd" 2>/dev/null; wait "$wd" 2>/dev/null || true
  [ -f "$MARKER" ] && return 124
  return $rc
}

run_engine "$@"
CODE=$?

# stream the engine's own stderr to our diagnostics channel
cat "$ERRFILE" >&2 || true

# --- timeout: explicit, non-terminal (M-5). Caller may escalate (R6). ---
# 124 = GNU/coreutils timeout; 137 = SIGKILL after --kill-after; 143 = SIGTERM
# (busybox timeout / bash watchdog). A written marker is authoritative.
# Checked BEFORE streaming the body: a killed engine may have flushed a partial
# body, and a truncated article must never reach the caller as content.
if [ "$CODE" -eq 124 ] || [ "$CODE" -eq 137 ] || [ "$CODE" -eq 143 ] || [ -f "$MARKER" ]; then
  log "fetch: engine exceeded ${FETCH_TIMEOUT}s budget — reporting timeout (non-terminal, partial body suppressed)"
  emit_status 1 false "" timeout "$HOME_DIR"
  exit 1
fi

cat "$BODYFILE" || true

# --- parse status from the single call's stderr (no second fetch) ---
VER="$(prov_field "$HOME_DIR" version)"; COM="$(prov_field "$HOME_DIR" commit)"
python3 "$HERE/parse_engine_status.py" "$CODE" "$HOME_DIR" "$ERRFILE" \
  --engine-version "${VER:-}" --engine-commit "${COM:-}" >&2 || true

exit $CODE
