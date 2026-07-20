"""Contract tests for the Evidence Reducer (independence.py)."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
IND = SCRIPTS / "independence.py"

_spec = importlib.util.spec_from_file_location("independence", IND)
assert _spec and _spec.loader
independence = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(independence)  # type: ignore[union-attr]


def run_cli(payload: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(IND)], input=payload,
                          capture_output=True, text=True)


class TestReducer(unittest.TestCase):
    def test_selftest_passes(self):
        r = subprocess.run([sys.executable, str(IND), "--selftest"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_ac1_support_plus_unrelated(self):
        # AC-1: 1 supporting + 1 unrelated → count 1, cannot be confirmed true.
        res = independence.reduce([
            {"url": "s", "stance": "supports", "body": "정부는 대책을 발표했다"},
            {"url": "u", "stance": "unrelated", "body": "무관한 스포츠 결과"},
        ])
        self.assertEqual(res["supporting_effective_count"], 1)
        self.assertEqual(res["unrelated_excluded"], [1])
        self.assertFalse(res["verdict_gate"]["can_be_true"])

    def test_ac2_single_refuting_primary(self):
        # AC-2: one refuting primary source → cannot confirm false.
        res = independence.reduce([
            {"url": "r", "stance": "refutes", "source_type": "primary",
             "body": "공식 자료에 따르면 수치가 다르다"},
        ])
        self.assertEqual(res["refuting_effective_count"], 1)
        self.assertFalse(res["verdict_gate"]["can_be_false"])

    def test_ac3_two_independent_supports(self):
        res = independence.reduce([
            {"url": "a", "stance": "supports", "title": "축구 대표 발표",
             "body": "대한축구협회는 국가대표 명단을 발표했다"},
            {"url": "b", "stance": "supports", "title": "반도체 수출 증가",
             "body": "산업부는 반도체 수출이 늘었다고 발표했다"},
        ])
        self.assertEqual(res["supporting_effective_count"], 2)
        self.assertTrue(res["verdict_gate"]["can_be_true"])

    def test_ac4_two_independent_refutes(self):
        res = independence.reduce([
            {"url": "a", "stance": "refutes", "body": "통계청은 실업률이 하락했다고 밝혔다"},
            {"url": "b", "stance": "refutes", "body": "한국은행은 물가가 둔화됐다고 보고했다"},
        ])
        self.assertEqual(res["refuting_effective_count"], 2)
        self.assertTrue(res["verdict_gate"]["can_be_false"])

    def test_ac5_same_reporter_diff_topic(self):
        res = independence.reduce([
            {"url": "m", "stance": "supports", "byline": "김기자", "dateline": "서울",
             "title": "물가 대책", "body": "정부는 물가 안정 대책을 발표했다 소비자물가 둔화"},
            {"url": "n", "stance": "supports", "byline": "김기자", "dateline": "서울",
             "title": "태풍 북상", "body": "태풍이 북상하면서 남부에 강풍과 폭우가 예상된다"},
        ])
        self.assertEqual(res["supporting_effective_count"], 2)

    def test_true_gate_requires_no_refuters(self):
        # 2 supports but 2 refuters present → can_be_true must be False.
        res = independence.reduce([
            {"url": "a", "stance": "supports", "body": "축구 대표 명단 발표"},
            {"url": "b", "stance": "supports", "body": "반도체 수출 증가 발표"},
            {"url": "c", "stance": "refutes", "body": "통계청은 정반대라고 밝혔다"},
            {"url": "d", "stance": "refutes", "body": "한국은행은 다른 수치를 보고했다"},
        ])
        self.assertEqual(res["supporting_effective_count"], 2)
        self.assertEqual(res["refuting_effective_count"], 2)
        self.assertFalse(res["verdict_gate"]["can_be_true"])
        self.assertTrue(res["verdict_gate"]["can_be_false"])

    def test_wire_collapse(self):
        wire = "서울=연합뉴스 정부는 오늘 물가 안정 대책을 발표했다 소비자물가 상승률이 둔화되고 있다"
        res = independence.reduce([
            {"url": "a", "stance": "supports", "body": wire},
            {"url": "b", "stance": "supports",
             "body": "연합뉴스 정부가 물가 안정 대책을 발표했다 소비자물가 상승률이 둔화되고 있다고 전했다"},
        ])
        self.assertEqual(res["supporting_effective_count"], 1)

    def test_duplicate_url_collapses(self):
        # same URL, dissimilar bodies → must be ONE effective source (no inflation).
        res = independence.reduce([
            {"url": "https://x.com/a", "stance": "supports", "body": "축구 대표 명단 발표"},
            {"url": "https://x.com/a", "stance": "supports", "body": "전혀 다른 반도체 수출 문장"},
        ])
        self.assertEqual(res["supporting_effective_count"], 1)
        self.assertFalse(res["verdict_gate"]["can_be_true"])
        self.assertEqual(res["clusters"][0]["links"][0]["reason"], "same_url")

    def test_link_audit_present(self):
        wire = "서울=연합뉴스 정부는 오늘 물가 안정 대책을 발표했다 소비자물가 상승률이 둔화되고 있다"
        res = independence.reduce([
            {"url": "a", "stance": "supports", "body": wire},
            {"url": "b", "stance": "supports",
             "body": "연합뉴스 정부가 물가 안정 대책을 발표했다 소비자물가 상승률이 둔화되고 있다고 전했다"},
        ])
        cluster = res["clusters"][0]
        self.assertTrue(cluster["links"], "link audit must record why members merged")
        self.assertIn(cluster["links"][0]["reason"], {"near_duplicate", "wire_token", "byline_dateline"})
        self.assertIn("score", cluster["links"][0])

    # -- error contract (FR-9 / AC-12) --
    def test_ac12_string_element_exit2(self):
        r = run_cli('["not-an-object"]')
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)
        err = json.loads(r.stderr)
        self.assertEqual(err["code"], "ITEM_NOT_OBJECT")
        self.assertEqual(err["index"], 0)

    def test_top_not_list_exit2(self):
        r = run_cli('{"a":1}')
        self.assertEqual(r.returncode, 2)
        self.assertEqual(json.loads(r.stderr)["code"], "TOP_NOT_LIST")

    def test_bad_stance_exit2(self):
        r = run_cli('[{"url":"x","stance":"maybe"}]')
        self.assertEqual(r.returncode, 2)
        err = json.loads(r.stderr)
        self.assertEqual(err["code"], "BAD_STANCE")
        self.assertEqual(err["field"], "stance")

    def test_missing_url_exit2(self):
        r = run_cli('[{"stance":"supports"}]')
        self.assertEqual(r.returncode, 2)
        self.assertEqual(json.loads(r.stderr)["code"], "BAD_URL")

    def test_bad_json_exit2(self):
        r = run_cli('[{')
        self.assertEqual(r.returncode, 2)
        self.assertEqual(json.loads(r.stderr)["code"], "BAD_JSON")

    def test_empty_text_exit2(self):
        # textless items cannot be assessed for independence — counting them as
        # independent clusters would inflate the verdict gate, so reject loudly.
        r = run_cli('[{"url":"x","stance":"supports"}]')
        self.assertEqual(r.returncode, 2)
        err = json.loads(r.stderr)
        self.assertEqual(err["code"], "EMPTY_TEXT")
        self.assertEqual(err["index"], 0)

    def test_whitespace_only_text_exit2(self):
        r = run_cli('[{"url":"x","stance":"supports","title":" ","body":"\\n"}]')
        self.assertEqual(r.returncode, 2)
        self.assertEqual(json.loads(r.stderr)["code"], "EMPTY_TEXT")

    def test_title_only_passes(self):
        res = independence.reduce([
            {"url": "a", "stance": "supports", "title": "축구 대표 명단 발표"},
        ])
        self.assertEqual(res["supporting_effective_count"], 1)

    def test_non_string_field_exit2(self):
        r = run_cli('[{"url":"x","stance":"supports","body":123}]')
        self.assertEqual(r.returncode, 2)
        err = json.loads(r.stderr)
        self.assertEqual(err["code"], "BAD_FIELD")
        self.assertEqual(err["field"], "body")


if __name__ == "__main__":
    unittest.main()
