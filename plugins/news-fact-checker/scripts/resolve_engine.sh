#!/usr/bin/env bash
# resolve_engine.sh — locate a usable insane-search engine, or signal DEGRADE.
#
# Resolution ladder (first that PASSES the contract smoke-test wins):
#   1. $INSANE_SEARCH_HOME (if set)         — same smoke-test; wider trust boundary, no exception
#   2. installed plugin cache (semver-highest)
#   3. installed marketplace checkout (semver-highest)
#   4. vendored clone ~/.gptaku-setup/insane-search/skills/insane-search
#   5. consent-gated pinned clone (only when NFC_CONSENT=yes) — COMMIT-pinned + atomic
#   6. none -> print "DEGRADE" and exit 3
#
# Supply-chain contract (FR-5):
#   The clone is pinned to a full-length COMMIT SHA, not just a movable tag. After
#   checkout the real HEAD is compared to the expected SHA; a mismatch aborts WITHOUT
#   installing (AC-9). The tag is only a human-readable version label.
#
# Atomic install (FR-7):
#   Clone + verify + smoke-test happen in a temp dir under the same parent as the
#   vendor dir. Only a fully-verified copy is renamed into place; on ANY failure the
#   temp dir is removed and the existing good copy is left untouched (AC-10).
#
# Consent boundary: this script CANNOT call AskUserQuestion (that is Claude-only).
# The skill asks the user, then re-invokes with NFC_CONSENT=yes to authorize the clone.
# Without NFC_CONSENT=yes, step 5 is skipped — never a silent clone+exec.
#
# Output contract: on success the LAST stdout line is the resolved engine home
#   (the `.../skills/insane-search` dir, i.e. the parent of the `engine` package).
#   All diagnostics go to stderr. Exit 0 = resolved, 3 = degrade.
set -uo pipefail

# Human-readable version label AND the immutable commit it must resolve to.
# INSANE_SEARCH_COMMIT is the deploy contract; the tag is display only.
REF="${INSANE_SEARCH_REF:-v0.8.2}"
EXPECTED_COMMIT="${INSANE_SEARCH_COMMIT:-2a578c469dc532969ed24fe698ff21d511653f97}"
CLONE_URL="https://github.com/fivetaku/insane-search"
VENDOR_PARENT="${HOME}/.gptaku-setup"
VENDOR_DIR="$VENDOR_PARENT/insane-search"
CACHE_ROOT="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/plugins"

log() { printf '%s\n' "$*" >&2; }

# Contract smoke-test: assert the FetchResult schema carries the R6 fields AND the
# engine CLI module imports. Network-free, so a version skew fails loud & fast.
smoke_test() {
  local home="$1"
  [ -f "$home/engine/__main__.py" ] || { log "  smoke: no engine/__main__.py at $home"; return 1; }
  python3 - "$home" 2>>/dev/null <<'PY'
import importlib, sys, dataclasses
home = sys.argv[1]
sys.path.insert(0, home)
try:
    from engine.fetch_chain import FetchResult
    importlib.import_module("engine.__main__")
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

write_provenance() {  # write_provenance <install_root> <commit>
  local root="$1" commit="$2" ts
  ts="$(date +%s 2>/dev/null || echo 0)"
  printf '{"version":"%s","commit":"%s","ref":"%s","installed_ts":%s}\n' \
    "$REF" "$commit" "$REF" "$ts" > "$root/.nfc-provenance.json" 2>/dev/null || true
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

# --- 5. consent-gated pinned clone (commit-pinned, atomic) ---
if [ "${NFC_CONSENT:-no}" = "yes" ]; then
  if ! command -v git >/dev/null 2>&1; then
    log "resolve: git not available — cannot clone"; echo "DEGRADE"; exit 3
  fi
  if ! printf '%s' "$EXPECTED_COMMIT" | grep -Eq '^[0-9a-f]{40}$'; then
    log "resolve: no valid pinned commit SHA (INSANE_SEARCH_COMMIT) — refusing to clone"
    echo "DEGRADE"; exit 3
  fi

  mkdir -p "$VENDOR_PARENT" 2>/dev/null || true
  TMP_DIR="$(mktemp -d "$VENDOR_PARENT/insane-search.tmp.XXXXXX")" || { log "resolve: mktemp failed"; echo "DEGRADE"; exit 3; }
  cleanup_tmp() { rm -rf "$TMP_DIR" 2>/dev/null || true; }

  log "resolve: consent granted — cloning $CLONE_URL @ $REF then verifying pin $EXPECTED_COMMIT"
  if git clone --depth 1 --branch "$REF" "$CLONE_URL" "$TMP_DIR" >&2 2>&1; then
    ACTUAL="$(git -C "$TMP_DIR" rev-parse HEAD 2>/dev/null || echo "")"
    if [ "$ACTUAL" != "$EXPECTED_COMMIT" ]; then
      log "resolve: PIN MISMATCH — expected $EXPECTED_COMMIT, got ${ACTUAL:-<none>}. Not installing; existing copy preserved."
      cleanup_tmp
    elif ! smoke_test "$TMP_DIR/skills/insane-search"; then
      log "resolve: cloned+pinned OK but smoke-test failed. Not installing; existing copy preserved."
      cleanup_tmp
    else
      write_provenance "$TMP_DIR/skills/insane-search" "$ACTUAL"
      # atomic swap: move any existing copy aside, rename temp into place, then drop old.
      OLD_BAK=""
      if [ -e "$VENDOR_DIR" ]; then
        OLD_BAK="$VENDOR_DIR.old.$$"
        mv "$VENDOR_DIR" "$OLD_BAK" 2>/dev/null || true
      fi
      if mv "$TMP_DIR" "$VENDOR_DIR" 2>/dev/null; then
        if h="$(try_home "$VENDOR_DIR/skills/insane-search")"; then
          # only drop the backup AFTER the installed copy verifies (L-1)
          [ -n "$OLD_BAK" ] && rm -rf "$OLD_BAK" 2>/dev/null || true
          log "resolve: OK installed (pinned $ACTUAL) -> $h"; printf '%s\n' "$h"; exit 0
        fi
        # post-move verify failed — restore the previous good copy.
        log "resolve: post-install smoke-test failed; restoring previous copy"
        rm -rf "$VENDOR_DIR" 2>/dev/null || true
        [ -n "$OLD_BAK" ] && mv "$OLD_BAK" "$VENDOR_DIR" 2>/dev/null || true
      else
        # rename failed — restore the previous good copy.
        [ -n "$OLD_BAK" ] && mv "$OLD_BAK" "$VENDOR_DIR" 2>/dev/null || true
        cleanup_tmp
        log "resolve: atomic install move failed; existing copy restored"
      fi
    fi
  else
    log "resolve: git clone failed; existing copy (if any) preserved"
    cleanup_tmp
  fi
else
  log "resolve: no installed copy found and NFC_CONSENT!=yes — NOT cloning (consent required)."
fi

# --- 6. degrade ---
echo "DEGRADE"
exit 3
