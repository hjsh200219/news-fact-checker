"""Contract tests for resolve_engine.sh commit-pinning + atomic install.

A stub `git` (no network) simulates clone/rev-parse so we can drive the pin-check
and atomic-swap branches deterministically (AC-9, AC-10, success).
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
RESOLVE = SCRIPTS / "resolve_engine.sh"
FAKE_ENGINE_SRC = ROOT / "tests" / "fake_engine" / "engine"

PIN = "a" * 40  # test pin (valid 40-hex); overrides the baked-in default via env

STUB_GIT = textwrap.dedent('''\
    #!/usr/bin/env python3
    import os, sys, shutil, pathlib
    args = sys.argv[1:]
    if args and args[0] == "-C":
        args = args[2:]
    cmd = args[0] if args else ""
    if cmd == "clone":
        dest = args[-1]
        eng = pathlib.Path(dest) / "skills" / "insane-search" / "engine"
        eng.mkdir(parents=True, exist_ok=True)
        (pathlib.Path(dest) / ".git").mkdir(exist_ok=True)
        if os.environ.get("STUB_ENGINE_GOOD", "1") == "1":
            src = os.environ["STUB_GOOD_ENGINE_SRC"]
            shutil.rmtree(eng)
            shutil.copytree(src, eng)
        else:
            (eng / "__init__.py").write_text("")
            (eng / "__main__.py").write_text("print('hi')\\n")
            (eng / "fetch_chain.py").write_text(
                "from dataclasses import dataclass\\n"
                "@dataclass\\nclass FetchResult:\\n    body: str = ''\\n")
        sys.exit(0)
    if cmd == "rev-parse":
        if "--git-dir" in args:
            print(".git"); sys.exit(0)
        if "HEAD" in args:
            print(os.environ.get("STUB_GIT_SHA", "0" * 40)); sys.exit(0)
        sys.exit(0)
    sys.exit(0)
''')


class TestResolveEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="nfc_resolve_test."))
        self.bindir = self.tmp / "bin"
        self.bindir.mkdir()
        git = self.bindir / "git"
        git.write_text(STUB_GIT)
        git.chmod(git.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        self.home = self.tmp / "home"
        self.vendor = self.home / ".gptaku-setup" / "insane-search"
        # existing BROKEN vendor copy (fails smoke) + sentinel we watch for preservation.
        broken_eng = self.vendor / "skills" / "insane-search" / "engine"
        broken_eng.mkdir(parents=True)
        (broken_eng / "__init__.py").write_text("")
        (broken_eng / "__main__.py").write_text("print('old')\n")
        (broken_eng / "fetch_chain.py").write_text(
            "from dataclasses import dataclass\n@dataclass\nclass FetchResult:\n    body: str = ''\n")
        self.sentinel = self.vendor / "SENTINEL"
        self.sentinel.write_text("keep-me")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _env(self, **overrides):
        env = dict(os.environ)
        env.pop("INSANE_SEARCH_HOME", None)
        env["PATH"] = f"{self.bindir}:{env['PATH']}"
        env["HOME"] = str(self.home)
        env["CLAUDE_CONFIG_DIR"] = str(self.home / ".claude")  # empty → cache/marketplace skip
        env["NFC_CONSENT"] = "yes"
        env["INSANE_SEARCH_COMMIT"] = PIN
        env["STUB_GOOD_ENGINE_SRC"] = str(FAKE_ENGINE_SRC)
        env.update(overrides)
        return env

    def run_resolve(self, env):
        return subprocess.run(["bash", str(RESOLVE)], capture_output=True, text=True, env=env)

    def _no_temp_leftovers(self):
        parent = self.home / ".gptaku-setup"
        leftovers = list(parent.glob("insane-search.tmp.*")) + list(parent.glob("insane-search.old.*"))
        self.assertEqual(leftovers, [], f"temp/old dirs leaked: {leftovers}")

    def test_ac9_pin_mismatch_preserves_existing(self):
        env = self._env(STUB_GIT_SHA="b" * 40)  # wrong SHA
        proc = self.run_resolve(env)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertIn("DEGRADE", proc.stdout)
        self.assertTrue(self.sentinel.exists(), "existing copy must be preserved on pin mismatch")
        self._no_temp_leftovers()

    def test_ac10_smoke_fail_preserves_existing(self):
        env = self._env(STUB_GIT_SHA=PIN, STUB_ENGINE_GOOD="0")  # right SHA, broken tree
        proc = self.run_resolve(env)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertTrue(self.sentinel.exists(), "existing copy must be preserved on smoke fail")
        self._no_temp_leftovers()

    def test_success_installs_and_writes_provenance(self):
        env = self._env(STUB_GIT_SHA=PIN, STUB_ENGINE_GOOD="1")
        proc = self.run_resolve(env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        home = proc.stdout.strip().splitlines()[-1]
        self.assertTrue(home.endswith("skills/insane-search"), home)
        self.assertTrue(Path(home, "engine", "__main__.py").exists())
        prov = Path(home, ".nfc-provenance.json")
        self.assertTrue(prov.exists(), "provenance must be written on install")
        self.assertIn(PIN, prov.read_text())
        self._no_temp_leftovers()

    def test_missing_pin_refuses_to_clone(self):
        env = self._env(STUB_GIT_SHA=PIN, INSANE_SEARCH_COMMIT="not-a-sha")
        proc = self.run_resolve(env)
        self.assertEqual(proc.returncode, 3)
        self.assertTrue(self.sentinel.exists())

    def test_no_consent_no_clone(self):
        env = self._env(STUB_GIT_SHA=PIN)
        env["NFC_CONSENT"] = "no"
        proc = self.run_resolve(env)
        self.assertEqual(proc.returncode, 3)
        self.assertIn("DEGRADE", proc.stdout)
        self.assertTrue(self.sentinel.exists())


if __name__ == "__main__":
    unittest.main()
