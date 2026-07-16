#!/usr/bin/env bash
# resolve_engine.sh — locate a usable insane-search engine, or signal DEGRADE.
#
# Resolution ladder (first that PASSES the contract smoke-test wins):
#   1. $INSANE_SEARCH_HOME (if set)         — same smoke-test; wider trust boundary, no exception
#   2. installed plugin cache (semver-highest)
#   3. installed marketplace checkout (semver-highest)
#   4. vendored clone ~/.gptaku-setup/insane-search/skills/insane-search
#   5. consent-gated pinned clone (only when NFC_CONSENT=yes)
#   6. none -> print "DEGRADE" and exit 3
#
# Consent boundary: this script CANNOT call AskUserQuestion (that is Claude-only).
# The skill asks the user, then re-invokes with NFC_CONSENT=yes to authorize the clone.
# Without NFC_CONSENT=yes, step 5 is skipped — never a silent clone+exec.
#
# Output contract: on success the LAST stdout line is the resolved engine home
#   (the `.../skills/insane-search` dir, i.e. the parent of the `engine` package).
#   All diagnostics go to stderr. Exit 0 = resolved, 3 = degrade.
set -uo pipefail

REF="${INSANE_SEARCH_REF:-v0.8.2}"
CLONE_URL="https://github.com/fivetaku/insane-search"
VENDOR_DIR="${HOME}/.gptaku-setup/insane-search"
CACHE_ROOT="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins"

log() { printf '%s\n' "$*" >&2; }

# Contract smoke-test: assert the FetchResult schema carries the R6 fields.
# Network-free (introspects the dataclass), so a version skew fails loud & fast.
smoke_test() {
  local home="$1"
  [ -f "$home/engine/__main__.py" ] || { log "  smoke: no engine/__main__.py at $home"; return 1; }
  python3 - "$home" 2>>/dev/null <<'PY'
import sys, dataclasses
home = sys.argv[1]
sys.path.insert(0, home)
try:
    from engine.fetch_chain import FetchResult
except Exception as e:
    print("SMOKE_FAIL import %s: %s" % (type(e).__name__, e), file=sys.stderr)
    sys.exit(1)
required = {"verdict", "grid_exhausted", "stop_reason", "untried_routes", "must_invoke_playwright_mcp"}
have = {f.name for f in dataclasses.fields(FetchResult)}
missing = required - have
if missing:
    print("SMOKE_FAIL missing R6 fields: %s" % ",".join(sorted(missing)), file=sys.stderr)
    sys.exit(1)
sys.exit(0)
PY
}

# Given a base dir that may contain versioned subdirs, echo the semver-highest
# `.../skills/insane-search` path that passes the smoke-test, else nothing.
pick_semver_home() {
  local glob="$1"
  # Collect candidate homes, sort by embedded version using `sort -V` (semver-aware:
  # 0.10.0 > 0.8.2), newest first. `sort -V` beats lexical string sort.
  local candidates
  candidates="$(compgen -G "$glob" 2>/dev/null || true)"
  [ -n "$candidates" ] || return 1
  # Sort paths by version-aware ordering, highest last -> reverse to try highest first.
  local home
  while IFS= read -r home; do
    [ -n "$home" ] || continue
    if smoke_test "$home"; then
      printf '%s\n' "$home"
      return 0
    else
      log "  skip (smoke fail): $home"
    fi
  done < <(printf '%s\n' "$candidates" | sort -V -r)
  return 1
}

try_home() {  # single explicit dir
  local home="$1"
  [ -d "$home" ] || return 1
  if smoke_test "$home"; then printf '%s\n' "$home"; return 0; fi
  return 1
}

# --- 1. $INSANE_SEARCH_HOME (same smoke-test; provenance note) ---
if [ -n "${INSANE_SEARCH_HOME:-}" ]; then
  log "resolve: trying \$INSANE_SEARCH_HOME=$INSANE_SEARCH_HOME (env-provided path — smoke-tested like any other)"
  if h="$(try_home "$INSANE_SEARCH_HOME")"; then log "resolve: OK env path"; printf '%s\n' "$h"; exit 0; fi
  log "resolve: \$INSANE_SEARCH_HOME failed smoke-test; continuing ladder"
fi

# --- 2. installed plugin cache (semver-highest) ---
log "resolve: scanning plugin cache…"
if h="$(pick_semver_home "$CACHE_ROOT/cache/*/insane-search/*/skills/insane-search")"; then
  log "resolve: OK cache -> $h"; printf '%s\n' "$h"; exit 0
fi

# --- 3. installed marketplace checkout (semver-highest / plain) ---
log "resolve: scanning marketplace checkouts…"
if h="$(pick_semver_home "$CACHE_ROOT/marketplaces/*/plugins/insane-search/skills/insane-search")"; then
  log "resolve: OK marketplace -> $h"; printf '%s\n' "$h"; exit 0
fi

# --- 4. vendored clone ---
if h="$(try_home "$VENDOR_DIR/skills/insane-search")"; then
  log "resolve: OK vendored -> $h"; printf '%s\n' "$h"; exit 0
fi

# --- 5. consent-gated pinned clone ---
if [ "${NFC_CONSENT:-no}" = "yes" ]; then
  if ! command -v git >/dev/null 2>&1; then
    log "resolve: git not available — cannot clone"; echo "DEGRADE"; exit 3
  fi
  log "resolve: consent granted — cloning $CLONE_URL @ $REF (pinned) -> $VENDOR_DIR"
  rm -rf "$VENDOR_DIR" 2>/dev/null || true
  mkdir -p "$(dirname "$VENDOR_DIR")"
  if git clone --depth 1 --branch "$REF" "$CLONE_URL" "$VENDOR_DIR" >&2 2>&1; then
    if h="$(try_home "$VENDOR_DIR/skills/insane-search")"; then
      log "resolve: OK cloned -> $h"; printf '%s\n' "$h"; exit 0
    fi
    log "resolve: cloned but smoke-test failed"
  else
    log "resolve: git clone failed"
  fi
else
  log "resolve: no installed copy found and NFC_CONSENT!=yes — NOT cloning (consent required)."
fi

# --- 6. degrade ---
echo "DEGRADE"
exit 3
