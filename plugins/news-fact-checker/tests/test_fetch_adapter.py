"""Contract tests for fetch_article.sh driven by the fake engine (no network)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FETCH = SCRIPTS / "fetch_article.sh"
FAKE_HOME = ROOT / "tests" / "fake_engine"

# public IP literal → passes url_policy without any DNS lookup (offline-safe).
PUBLIC_URL = "http://8.8.8.8/article"

STATUS_RE = re.compile(r"NFC_STATUS (\{.*\})")


def run_fetch(url=PUBLIC_URL, scenario=None, extra_env=None, args=()):
    env = dict(os.environ)
    env["INSANE_SEARCH_HOME"] = str(FAKE_HOME)
    if scenario:
        env["FAKE_ENGINE_SCENARIO"] = scenario
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(["bash", str(FETCH), url, *args],
                          capture_output=True, text=True, env=env)
    m = STATUS_RE.search(proc.stderr)
    status = json.loads(m.group(1)) if m else None
    return proc, status


class TestFetchAdapter(unittest.TestCase):
    def test_strong_ok_exit0_body(self):
        proc, st = run_fetch(scenario="strong_ok")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("본문", proc.stdout)
        self.assertTrue(st["ok"])
        self.assertEqual(st["verdict"], "strong_ok")

    def test_weak_ok_exit0(self):
        proc, st = run_fetch(scenario="weak_ok")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(st["verdict"], "weak_ok")

    def test_suspect_ok_keeps_body_exit1(self):
        proc, st = run_fetch(scenario="suspect_ok")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("본문", proc.stdout)  # body preserved despite ok=false
        self.assertEqual(st["verdict"], "suspect_ok")

    def test_auth_required_terminal(self):
        proc, st = run_fetch(scenario="auth_required")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(st["verdict"], "auth_required")

    def test_not_found_terminal(self):
        _, st = run_fetch(scenario="not_found")
        self.assertEqual(st["verdict"], "not_found")

    def test_blocked_has_routes_and_mcp(self):
        _, st = run_fetch(scenario="blocked")
        self.assertEqual(st["verdict"], "blocked")
        self.assertTrue(st["must_invoke_playwright_mcp"])
        self.assertTrue(st["untried_routes"])

    def test_ac13_rate_limited_nonterminal_routes(self):
        proc, st = run_fetch(scenario="rate_limited")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(st["verdict"], "rate_limited")
        self.assertTrue(st["untried_routes"], "escalation info must be preserved")

    def test_unknown_verdict_compat_failure(self):
        _, st = run_fetch(scenario="unknown_verdict")
        self.assertFalse(st["parse_ok"])
        self.assertEqual(st["stop_reason"], "status_unparsed")

    def test_ac11_phrase_variant(self):
        _, st = run_fetch(scenario="phrase_variant")
        self.assertEqual(st["verdict"], "blocked")
        self.assertTrue(st["parse_ok"])
        self.assertTrue(st["must_invoke_playwright_mcp"])

    def test_drift_no_line_compat_failure(self):
        proc, st = run_fetch(scenario="drift_no_line")
        self.assertEqual(proc.returncode, 0)  # engine exit preserved
        self.assertFalse(st["parse_ok"])       # but flagged as compat failure
        self.assertEqual(st["stop_reason"], "status_unparsed")

    def test_spaced_escalation_detected(self):
        _, st = run_fetch(scenario="spaced_escalation")
        self.assertTrue(st["must_invoke_playwright_mcp"])
        self.assertTrue(st["untried_routes"])

    def test_fatal_exit2(self):
        proc, st = run_fetch(scenario="fatal")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(st["stop_reason"], "error")

    # AC-7 — url policy gate at the adapter boundary
    def test_ac7_unsafe_url_file(self):
        proc, st = run_fetch(url="file:///etc/passwd")
        self.assertEqual(proc.returncode, 4)
        self.assertEqual(st["stop_reason"], "unsafe_url")

    def test_ac7_unsafe_url_loopback(self):
        proc, st = run_fetch(url="http://127.0.0.1/x")
        self.assertEqual(proc.returncode, 4)
        self.assertEqual(st["verdict"], "unsafe_url")

    def test_ac7_unsafe_url_metadata(self):
        proc, st = run_fetch(url="http://169.254.169.254/latest/meta-data/")
        self.assertEqual(proc.returncode, 4)

    # M-5 — wall-clock timeout is explicit and non-terminal
    def test_timeout_nonterminal(self):
        proc, st = run_fetch(scenario="hang", extra_env={"NFC_FETCH_TIMEOUT": "1"})
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(st["stop_reason"], "timeout")

    def test_timeout_suppresses_partial_body(self):
        # engine flushed a partial body before wedging — a truncated article must
        # never reach the caller as content.
        proc, st = run_fetch(scenario="hang_after_body",
                             extra_env={"NFC_FETCH_TIMEOUT": "1"})
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(st["stop_reason"], "timeout")
        self.assertEqual(proc.stdout, "")

    # FR-6 — structured status carries the full schema
    def test_status_schema_complete(self):
        _, st = run_fetch(scenario="strong_ok")
        for key in ("schema_version", "exit", "ok", "verdict", "grid_exhausted",
                    "stop_reason", "untried_routes", "must_invoke_playwright_mcp",
                    "engine_version", "engine_commit"):
            self.assertIn(key, st)


if __name__ == "__main__":
    unittest.main()
