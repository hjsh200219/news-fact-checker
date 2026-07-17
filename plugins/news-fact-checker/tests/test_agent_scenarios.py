"""Lock the doc-level invariants the agent scenarios depend on (FR-3 / AC-6).

The behavioural assertions live in AGENT_SCENARIOS.md; here we ensure the harness
rules that MAKE those behaviours safe stay present in the skill docs and that the
adversarial fixture remains a real injection case.
"""
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "news-fact-checker" / "SKILL.md"
FETCH_HARNESS = ROOT / "skills" / "news-fact-checker" / "references" / "fetch-harness.md"
FIXTURE = ROOT / "tests" / "fixtures" / "prompt_injection_article.md"


class TestAgentScenarioInvariants(unittest.TestCase):
    def test_skill_has_untrusted_content_rule(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("H0", text, "top-level untrusted-content rule (H0) must exist")
        self.assertIn("불신 데이터", text)
        # the rule must explicitly refuse the dangerous instruction classes.
        for needle in ("명령", "파일", "설치", "판정"):
            self.assertIn(needle, text)

    def test_fetch_harness_has_trust_boundary(self):
        text = FETCH_HARNESS.read_text(encoding="utf-8")
        self.assertIn("신뢰 경계", text)
        self.assertIn("불신 데이터", text)

    def test_injection_fixture_is_adversarial(self):
        text = FIXTURE.read_text(encoding="utf-8")
        # these markers are what the agent must IGNORE — keep them in the fixture.
        for marker in ("id_rsa", "169.254.169.254", "pip install", "SYSTEM OVERRIDE"):
            self.assertIn(marker, text, f"fixture lost its injection marker: {marker}")

    def test_skill_gate_is_reducer_driven(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("supporting_effective_count", text)
        self.assertIn("refuting_effective_count", text)


if __name__ == "__main__":
    unittest.main()
