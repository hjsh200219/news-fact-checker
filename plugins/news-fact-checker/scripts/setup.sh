#!/usr/bin/env bash
# setup.sh — idempotent, non-blocking environment check for news-fact-checker.
# Run once on first use. Never blocks; prints advisories to stderr.
set -uo pipefail

MARKER_DIR="${HOME}/.gptaku-setup"
MARKER="$MARKER_DIR/news-fact-checker.json"
mkdir -p "$MARKER_DIR" 2>/dev/null || true

warn() { printf '%s\n' "$*" >&2; }

command -v python3 >/dev/null 2>&1 || warn "[news-fact-checker] python3 not found — required for the engine adapter and independence.py."
command -v git >/dev/null 2>&1     || warn "[news-fact-checker] git not found — auto-install of insane-search (clone path) will be unavailable; installed copies still work."

if [ ! -f "$MARKER" ]; then
  ts="$(date +%s 2>/dev/null || echo 0)"
  printf '{"setup":true,"plugin":"news-fact-checker","ts":%s}\n' "$ts" > "$MARKER" 2>/dev/null || true
fi
exit 0
