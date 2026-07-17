#!/usr/bin/env bash
# verify-docs.sh — doc↔repo consistency gate (network-free, dependency-free).
#
# Checks that the repository's entry docs do not drift from the tree:
#   1. every repo-relative markdown link in AGENTS.md and ARCHITECTURE.md resolves
#   2. every script named in the AGENTS.md "Health Stack" section exists
#   3. the 3 production Python contracts (mypy targets) exist
#   4. plugins/news-fact-checker/tests/ exists and contains test_*.py
#
# Exits nonzero on any failure. No network, no third-party tools (bash + coreutils).
set -euo pipefail
shopt -s nullglob

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
cd "$REPO_ROOT"

PLUGIN="plugins/news-fact-checker"
PASS=0
FAIL=0
FAILURES=()

pass() { PASS=$((PASS + 1)); printf '  ok   %s\n' "$1"; }
fail() { FAIL=$((FAIL + 1)); FAILURES+=("$1"); printf '  FAIL %s\n' "$1"; }

# check_path <token> <source-label>  — token may contain a glob (* ?)
check_path() {
  local tok="$1" label="$2"
  case "$tok" in
    *[*?]*)
      local matches=( $tok )   # nullglob: empty if no match
      if [ "${#matches[@]}" -ge 1 ]; then
        pass "$label: $tok (${#matches[@]} match)"
      else
        fail "$label: $tok (glob matched nothing)"
      fi
      ;;
    *)
      if [ -e "$tok" ]; then
        pass "$label: $tok"
      else
        fail "$label: $tok (missing)"
      fi
      ;;
  esac
}

# ---- 1. markdown links in entry docs resolve ---------------------------------
check_links() {
  local file="$1"
  if [ ! -f "$file" ]; then
    fail "link-source: $file (missing)"
    return
  fi
  echo "[links] $file"
  local dir raw target resolved
  dir="$(dirname "$file")"
  while IFS= read -r raw; do
    [ -n "$raw" ] || continue
    target="${raw%%#*}"                 # drop #anchor fragment
    [ -n "$target" ] || continue        # pure in-page anchor
    case "$target" in
      http://*|https://*|mailto:*|tel:*|//*) continue ;;  # not repo-relative
    esac
    resolved="$dir/$target"
    if [ -e "$resolved" ]; then
      pass "link -> $target"
    else
      fail "link -> $target (from $file; resolved $resolved missing)"
    fi
  done < <(grep -oE '\]\([^)]+\)' "$file" 2>/dev/null | sed -E 's/^\]\(//; s/\)$//' | sort -u || true)
}

check_links "AGENTS.md"
check_links "ARCHITECTURE.md"

# ---- 2. scripts named in AGENTS.md "Health Stack" exist ----------------------
echo "[health-stack] AGENTS.md"
if [ -f "AGENTS.md" ]; then
  hs_tokens="$(awk '/^## Health Stack/{f=1;next} /^## /{f=0} f' AGENTS.md \
    | grep -oE "${PLUGIN}/[A-Za-z0-9_./*-]+\.(sh|py)" | sort -u || true)"
  if [ -z "$hs_tokens" ]; then
    fail "health-stack: no script paths found under '## Health Stack' in AGENTS.md"
  else
    while IFS= read -r tok; do
      [ -n "$tok" ] || continue
      check_path "$tok" "health-stack"
    done <<< "$hs_tokens"
  fi
else
  fail "health-stack: AGENTS.md missing"
fi

# ---- 3. production Python contracts (mypy targets) exist ---------------------
echo "[contracts] production Python (mypy targets)"
for py in independence.py url_policy.py parse_engine_status.py; do
  check_path "${PLUGIN}/scripts/${py}" "contract"
done

# ---- 4. tests dir exists and has test_*.py -----------------------------------
echo "[tests] contract tests present"
if [ -d "${PLUGIN}/tests" ]; then
  test_files=( "${PLUGIN}"/tests/test_*.py )
  if [ "${#test_files[@]}" -ge 1 ]; then
    pass "tests: ${PLUGIN}/tests has ${#test_files[@]} test_*.py file(s)"
  else
    fail "tests: ${PLUGIN}/tests has no test_*.py"
  fi
else
  fail "tests: ${PLUGIN}/tests directory missing"
fi

# ---- summary -----------------------------------------------------------------
echo
echo "======================================================"
if [ "$FAIL" -eq 0 ]; then
  echo "verify-docs: PASS ($PASS checks)"
  echo "======================================================"
  exit 0
else
  echo "verify-docs: FAIL ($FAIL failed, $PASS passed)"
  for f in "${FAILURES[@]}"; do
    printf '  - %s\n' "$f"
  done
  echo "======================================================"
  exit 1
fi
