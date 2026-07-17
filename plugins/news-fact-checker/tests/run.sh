#!/usr/bin/env bash
# run.sh — local mirror of the CI gate (network-free).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN="$(cd "$HERE/.." && pwd)"
REPO_ROOT="$(cd "$PLUGIN/../.." && pwd)"

echo "== docs consistency (verify-docs) =="
bash "$REPO_ROOT/scripts/verify-docs.sh"

echo "== shell syntax =="
bash -n "$PLUGIN"/scripts/*.sh

echo "== py compile =="
python3 -m py_compile "$PLUGIN"/scripts/*.py "$PLUGIN"/tests/fake_engine/engine/*.py

echo "== reducer selftest =="
python3 "$PLUGIN/scripts/independence.py" --selftest

echo "== url_policy selftest =="
python3 "$PLUGIN/scripts/url_policy.py" --selftest

echo "== unit tests =="
python3 -m unittest discover -s "$PLUGIN/tests" -p 'test_*.py' "$@"

echo "== OK =="
