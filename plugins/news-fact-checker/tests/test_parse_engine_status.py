"""Contract tests for the engine status parser (parse_engine_status.py)."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
PES = SCRIPTS / "parse_engine_status.py"

_spec = importlib.util.spec_from_file_location("parse_engine_status", PES)
assert _spec and _spec.loader
pes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pes)  # type: ignore[union-attr]


class TestParser(unittest.TestCase):
    def test_strong_ok(self):
        s = pes.parse_status(0, "/home", "[engine] ok=true verdict=strong_ok\n")
        self.assertTrue(s["ok"])
        self.assertEqual(s["verdict"], "strong_ok")
        self.assertTrue(s["parse_ok"])
        self.assertEqual(s["status_source"], "engine_line")

    def test_suspect_ok(self):
        s = pes.parse_status(1, "/home",
                             "[engine] ok=false verdict=suspect_ok\nmust_invoke_playwright_mcp = TRUE\n")
        self.assertFalse(s["ok"])
        self.assertEqual(s["verdict"], "suspect_ok")
        self.assertTrue(s["must_invoke_playwright_mcp"])

    def test_rate_limited_routes_preserved(self):
        err = ("[engine] ok=false verdict=rate_limited\n"
               "  • backoff: retry after delay\n  • mcp: playwright fallback\n")
        s = pes.parse_status(1, "/home", err)
        self.assertEqual(s["verdict"], "rate_limited")
        self.assertEqual(len(s["untried_routes"]), 2)

    def test_terminal_verdicts(self):
        for v in ("auth_required", "not_found"):
            s = pes.parse_status(1, "/home", f"[engine] ok=false verdict={v}\n")
            self.assertEqual(s["verdict"], v)
            self.assertTrue(s["parse_ok"])

    def test_fatal_no_engine_line(self):
        s = pes.parse_status(2, "/home", "Traceback ...\nRuntimeError: boom\n")
        self.assertFalse(s["ok"])
        self.assertEqual(s["status_source"], "exit_code_fallback")
        self.assertEqual(s["stop_reason"], "error")

    def test_ac11_phrase_variant_still_parses(self):
        # same structured fields, drifted surrounding prose → must still parse.
        err = ("[engine] ok=false verdict=blocked\n"
               ">>> escalation needed: must_invoke_playwright_mcp = TRUE <<<\n"
               "  • playwright: navigate\n")
        s = pes.parse_status(1, "/home", err)
        self.assertEqual(s["verdict"], "blocked")
        self.assertTrue(s["parse_ok"])
        self.assertTrue(s["must_invoke_playwright_mcp"])

    def test_ac11_unknown_verdict_is_compat_failure(self):
        s = pes.parse_status(1, "/home", "[engine] ok=false verdict=teleported_away\n")
        self.assertFalse(s["parse_ok"])
        self.assertEqual(s["stop_reason"], "status_unparsed")

    def test_drift_no_line_exit0_is_compat_failure(self):
        # structured line dropped but exit 0 → must NOT be silent empty-verdict success.
        s = pes.parse_status(0, "/home", "fetched ok, human-only text\n")
        self.assertFalse(s["parse_ok"])
        self.assertEqual(s["verdict"], "")
        self.assertEqual(s["stop_reason"], "status_unparsed")

    def test_drift_no_line_exit1_is_compat_failure(self):
        s = pes.parse_status(1, "/home", "blocked, human-only text\n")
        self.assertFalse(s["parse_ok"])

    def test_fatal_exit2_no_line_is_not_compat_failure(self):
        # exit 2 legitimately has no structured line — that's the fatal path, not drift.
        s = pes.parse_status(2, "/home", "Traceback...\n")
        self.assertTrue(s["parse_ok"])
        self.assertEqual(s["stop_reason"], "error")

    def test_escalation_flag_spacing_casing(self):
        for line in ("must_invoke_playwright_mcp = True",
                     "must_invoke_playwright_mcp=TRUE",
                     "must_invoke_playwright_mcp  =  true"):
            s = pes.parse_status(1, "/home", f"[engine] ok=false verdict=blocked\n{line}\n")
            self.assertTrue(s["must_invoke_playwright_mcp"], line)

    def test_grid_exhausted_case_insensitive(self):
        s = pes.parse_status(1, "/home", "[engine] ok=false verdict=blocked\ngrid_exhausted=true\n")
        self.assertTrue(s["grid_exhausted"])

    def test_provenance_passthrough(self):
        s = pes.parse_status(0, "/home", "[engine] ok=true verdict=strong_ok\n",
                             engine_version="v0.8.2", engine_commit="abc123")
        self.assertEqual(s["engine_version"], "v0.8.2")
        self.assertEqual(s["engine_commit"], "abc123")

    def test_schema_fields_present(self):
        s = pes.parse_status(0, "/home", "[engine] ok=true verdict=strong_ok\n")
        for key in ("schema_version", "exit", "ok", "parse_ok", "status_source", "verdict",
                    "grid_exhausted", "stop_reason", "untried_routes",
                    "must_invoke_playwright_mcp", "engine_home",
                    "engine_version", "engine_commit"):
            self.assertIn(key, s)


if __name__ == "__main__":
    unittest.main()
