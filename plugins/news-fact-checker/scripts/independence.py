#!/usr/bin/env python3
"""independence.py — deterministic Evidence Reducer.

Korean news is dominated by wire syndication: one 연합뉴스/뉴스1/뉴시스 story is
reprinted (often with a rewritten lead/headline) by many outlets. Counting raw
"sources" then overstates independence. This reducer collapses each syndication
cluster to ONE effective source — and, critically, does so *per stance* so the
caller never counts a lone supporting source plus an unrelated one as "2".

The confirmed-verdict gate is COMPUTED HERE, not left to prose interpretation:

  can_be_true  = supporting_effective_count >= 2 AND refuting_effective_count == 0
  can_be_false = refuting_effective_count   >= 2

A single primary source may raise confidence/explanation but NEVER bypasses the
independent-source minimum (see verdict-taxonomy.md, FR-2).

Contract (pure stdlib, no external deps):
  stdin  : JSON list of items, each:
             {url, stance, title?, body?, byline?, dateline?, source_type?}
           stance ∈ {"supports","refutes","unrelated"}   (REQUIRED)
           At least one of title/body must be non-empty: textless items cannot
           be checked for syndication overlap, and counting them as independent
           would inflate the verdict gate → rejected with EMPTY_TEXT.
  stdout : JSON reducer result (schema_version 2 — see _EMPTY / collapse below)
  stderr : on bad input, a single JSON error line {error,code,index?,field?}

Exit codes:
  0  success (reducer result on stdout)
  2  user input error (bad schema / bad JSON)   — never a traceback
  1  internal error (generic; no local paths leaked to stdout)

Run `independence.py --selftest` to execute built-in fixtures (exit 0 on pass).
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any

SCHEMA_VERSION = 2

TAU = 0.85        # pure near-duplicate threshold (char-trigram Jaccard)
TAU_WIRE = 0.35   # lower bar when a shared wire token is present (rewritten leads)
TAU_TOPIC = 0.20  # minimum topic overlap required for a byline+dateline link
CHAR_K = 3        # character n-gram size (robust to Korean particles / word order)

STANCES = ("supports", "refutes", "unrelated")

# Wire-service / syndication attribution tokens. Presence signals the item is a
# reprint of an upstream agency story, not independent reporting. Restricted to
# agency identifiers and explicit syndication datelines (FR-8): the generic word
# "제공" was removed because it is not agency-specific and over-merged.
WIRE_TOKENS = [
    "연합뉴스", "연합newstv", "yonhap", "뉴스1", "news1", "뉴시스", "newsis", "=연합",
    "(서울=", "(부산=", "(대구=", "(광주=", "(대전=", "(인천=", "(세종=",
    "ap통신", "associated press", "reuters", "로이터", "afp", "블룸버그", "bloomberg",
]


class InputError(Exception):
    """User-facing schema/JSON error. Carries a stable code + optional locus."""

    def __init__(self, code: str, message: str, index: int | None = None, field: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.index = index
        self.field = field

    def as_json(self) -> str:
        payload: dict[str, Any] = {"error": self.message, "code": self.code}
        if self.index is not None:
            payload["index"] = self.index
        if self.field is not None:
            payload["field"] = self.field
        return json.dumps(payload, ensure_ascii=False)


def _norm(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _shingles(text: str, k: int = CHAR_K) -> set[str]:
    # Character n-grams over space-stripped normalized text. Char-grams are robust
    # to Korean particle attachment and word-order changes that defeat word-grams.
    t = _norm(text).replace(" ", "")
    if len(t) < k:
        return {t} if t else set()
    return {t[i:i + k] for i in range(len(t) - k + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def wire_tokens_of(item: dict) -> set[str]:
    hay = _norm(" ".join(str(item.get(f, "")) for f in ("body", "byline", "dateline", "title")))
    return {t for t in WIRE_TOKENS if t.lower() in hay}


def _byline_dateline_match(a: dict, b: dict) -> bool:
    ab, bb = _norm(a.get("byline", "")), _norm(b.get("byline", ""))
    ad, bd = _norm(a.get("dateline", "")), _norm(b.get("dateline", ""))
    return bool(ab) and ab == bb and bool(ad) and ad == bd


def _link_reason(a: dict, b: dict, sa: set[str], sb: set[str],
                 wa: set[str], wb: set[str]) -> dict | None:
    """Return an audit record {reason, score, shared_wire_tokens} if i,j link, else None."""
    # Identical URL = literally the same page → always one effective source,
    # regardless of body similarity (prevents count inflation from duplicate URLs).
    ua, ub = _norm(a.get("url", "")), _norm(b.get("url", ""))
    if ua and ua == ub:
        return {"reason": "same_url", "score": 1.0, "shared_wire_tokens": []}
    sim = round(jaccard(sa, sb), 4)
    if sim >= TAU:
        return {"reason": "near_duplicate", "score": sim, "shared_wire_tokens": []}
    shared = sorted(wa & wb)
    if shared and sim >= TAU_WIRE:                       # wire-token dominant
        return {"reason": "wire_token", "score": sim, "shared_wire_tokens": shared}
    # byline+dateline alone is NOT enough — require a topic-overlap floor so two
    # different stories by the same reporter/place stay separate (FR-8 / AC-5).
    if _byline_dateline_match(a, b) and sim >= TAU_TOPIC:
        return {"reason": "byline_dateline", "score": sim, "shared_wire_tokens": []}
    return None


def _collapse_group(items: list[dict], idx: list[int]) -> tuple[list[list[int]], list[dict]]:
    """Union-find collapse over a single-stance group. Returns (clusters, links).

    `idx` maps local positions back to the caller's original indices, so cluster
    members and link audits are always reported in original-input terms.
    """
    n = len(idx)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[max(rx, ry)] = min(rx, ry)

    grp = [items[i] for i in idx]
    shingles = [_shingles(f"{it.get('title','')} {it.get('body','')}") for it in grp]
    wires = [wire_tokens_of(it) for it in grp]

    links: list[dict] = []
    for i in range(n):
        for j in range(i + 1, n):
            rec = _link_reason(grp[i], grp[j], shingles[i], shingles[j], wires[i], wires[j])
            if rec is not None:
                union(i, j)
                links.append({"a": idx[i], "b": idx[j], **rec})

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(idx[i])
    clusters = [sorted(g) for g in groups.values()]
    clusters.sort(key=lambda c: c[0])
    return clusters, links


def _validate(items: Any) -> list[dict]:
    if not isinstance(items, list):
        raise InputError("TOP_NOT_LIST", "stdin must be a JSON list")
    out: list[dict] = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            raise InputError("ITEM_NOT_OBJECT", "item must be a JSON object", index=i)
        url = it.get("url")
        if not isinstance(url, str) or not url.strip():
            raise InputError("BAD_URL", "item.url must be a non-empty string", index=i, field="url")
        stance = it.get("stance")
        if not isinstance(stance, str) or stance not in STANCES:
            raise InputError("BAD_STANCE",
                             "item.stance must be one of supports|refutes|unrelated",
                             index=i, field="stance")
        for f in ("title", "body", "byline", "dateline", "source_type"):
            if f in it and not isinstance(it[f], str):
                raise InputError("BAD_FIELD", "field must be a string", index=i, field=f)
        if not ((it.get("title") or "").strip() or (it.get("body") or "").strip()):
            raise InputError("EMPTY_TEXT",
                             "item must carry a non-empty title or body "
                             "(textless evidence cannot be assessed for independence)",
                             index=i)
        out.append(it)
    return out


def reduce(items_raw: Any) -> dict:
    items = _validate(items_raw)

    unrelated = [i for i, it in enumerate(items) if it["stance"] == "unrelated"]
    sup_idx = [i for i, it in enumerate(items) if it["stance"] == "supports"]
    ref_idx = [i for i, it in enumerate(items) if it["stance"] == "refutes"]

    sup_clusters, sup_links = _collapse_group(items, sup_idx)
    ref_clusters, ref_links = _collapse_group(items, ref_idx)

    def detail(clusters: list[list[int]], stance: str, links: list[dict]) -> list[dict]:
        out = []
        for c in clusters:
            member_set = set(c)
            out.append({
                "stance": stance,
                "members": c,
                "source_types": [items[m].get("source_type", "") for m in c],
                "urls": [items[m]["url"] for m in c],
                "links": [lk for lk in links
                          if lk["a"] in member_set and lk["b"] in member_set],
            })
        return out

    sup_count = len(sup_clusters)
    ref_count = len(ref_clusters)

    return {
        "schema_version": SCHEMA_VERSION,
        "supporting_clusters": sup_clusters,
        "refuting_clusters": ref_clusters,
        "supporting_effective_count": sup_count,
        "refuting_effective_count": ref_count,
        "unrelated_excluded": unrelated,
        "clusters": detail(sup_clusters, "supports", sup_links)
                    + detail(ref_clusters, "refutes", ref_links),
        "verdict_gate": {
            "can_be_true": sup_count >= 2 and ref_count == 0,
            "can_be_false": ref_count >= 2,
        },
    }


# --------------------------------------------------------------------------- #
def _selftest() -> int:
    # F1: one 연합뉴스 wire story + 3 supporting reprints → 1 supporting cluster.
    wire_body = ("서울=연합뉴스 정부는 오늘 물가 안정 대책을 발표했다 소비자물가 상승률이 "
                 "둔화되고 있다고 밝혔다 관계 부처는 추가 대책을 검토 중이다")
    reprints = [
        {"url": "a", "stance": "supports", "title": "정부 물가 대책 발표", "body": wire_body,
         "byline": "", "dateline": "서울"},
        {"url": "b", "stance": "supports", "title": "물가 안정 대책 나왔다", "dateline": "서울",
         "body": ("연합뉴스 보도 정부가 물가 안정 대책을 발표했다고 오늘 전했다 소비자물가 "
                  "상승률이 둔화되고 있다고 밝혔다 관계 부처는 추가 대책을 검토 중이다")},
        {"url": "c", "stance": "supports", "title": "정부, 추가 물가대책 검토", "dateline": "서울",
         "body": ("정부는 오늘 물가 안정 대책을 발표했다 소비자물가 상승률이 둔화되고 있다고 "
                  "연합뉴스에 밝혔다 관계 부처는 추가 대책을 검토 중이라고 전했다")},
        {"url": "d", "stance": "supports", "title": "물가 대책 발표 소식", "dateline": "서울",
         "body": ("오늘 정부는 물가 안정 대책을 발표했다 소비자물가 상승률 둔화 관계 부처 추가 "
                  "대책 검토 중 서울=연합뉴스")},
    ]
    r1 = reduce(reprints)
    assert r1["supporting_effective_count"] == 1, f"F1 expected 1, got {r1}"
    assert r1["verdict_gate"]["can_be_true"] is False, f"F1 gate: {r1['verdict_gate']}"

    # F2: two genuinely independent supporting stories → 2 clusters → can_be_true.
    indep = [
        {"url": "x", "stance": "supports", "title": "국내 축구 국가대표 명단 발표",
         "byline": "김기자", "dateline": "서울",
         "body": "대한축구협회는 다음 달 평가전을 위한 국가대표 명단을 발표했다 새 감독의 첫 선발이다"},
        {"url": "y", "stance": "supports", "title": "반도체 수출 지난달 증가",
         "byline": "이기자", "dateline": "세종",
         "body": "산업통상자원부는 지난달 반도체 수출이 전년 대비 크게 늘었다고 발표했다 메모리 가격 회복이 배경이다"},
    ]
    r2 = reduce(indep)
    assert r2["supporting_effective_count"] == 2, f"F2 expected 2, got {r2}"
    assert r2["verdict_gate"]["can_be_true"] is True, f"F2 gate: {r2['verdict_gate']}"

    # F3: same-wire but different-topic supporting stories must NOT collapse.
    same_wire_diff_topic = [
        {"url": "p", "stance": "supports", "title": "물가 대책", "dateline": "서울",
         "body": "서울=연합뉴스 정부는 물가 안정 대책을 발표했다 소비자물가 상승률 둔화"},
        {"url": "q", "stance": "supports", "title": "태풍 북상", "dateline": "부산",
         "body": "부산=연합뉴스 태풍이 북상하면서 남부 지방에 강풍과 폭우가 예상된다"},
    ]
    r3 = reduce(same_wire_diff_topic)
    assert r3["supporting_effective_count"] == 2, f"F3 expected 2, got {r3}"

    # F4: same byline+dateline but different topic → distinct clusters (AC-5).
    same_reporter_diff_topic = [
        {"url": "m", "stance": "supports", "byline": "김기자", "dateline": "서울",
         "title": "물가 대책 발표", "body": "정부는 물가 안정 대책을 발표했다 소비자물가 상승률 둔화"},
        {"url": "n", "stance": "supports", "byline": "김기자", "dateline": "서울",
         "title": "태풍 북상 경보", "body": "태풍이 북상하면서 남부 지방에 강풍과 폭우가 예상된다"},
    ]
    r4 = reduce(same_reporter_diff_topic)
    assert r4["supporting_effective_count"] == 2, f"F4 expected 2, got {r4}"

    # F5: 1 support + 1 unrelated → supporting_effective_count 1, cannot be true (AC-1).
    sup_plus_unrelated = [
        {"url": "s", "stance": "supports", "title": "가", "body": "정부는 물가 안정 대책을 발표했다"},
        {"url": "u", "stance": "unrelated", "title": "나", "body": "전혀 무관한 스포츠 경기 결과"},
    ]
    r5 = reduce(sup_plus_unrelated)
    assert r5["supporting_effective_count"] == 1, f"F5 expected 1, got {r5}"
    assert r5["unrelated_excluded"] == [1], f"F5 excluded: {r5['unrelated_excluded']}"
    assert r5["verdict_gate"]["can_be_true"] is False, f"F5 gate: {r5['verdict_gate']}"

    # F6: single refuting primary → cannot be false (AC-2).
    one_refute = [{"url": "r", "stance": "refutes", "source_type": "primary",
                   "title": "반박", "body": "공식 자료에 따르면 그 수치는 사실과 다르다"}]
    r6 = reduce(one_refute)
    assert r6["refuting_effective_count"] == 1, f"F6 expected 1, got {r6}"
    assert r6["verdict_gate"]["can_be_false"] is False, f"F6 gate: {r6['verdict_gate']}"

    # F7: two independent refuting sources → can_be_false (AC-4).
    two_refute = [
        {"url": "r1", "stance": "refutes", "title": "반박1",
         "body": "통계청 자료에 따르면 실제 실업률은 기사와 정반대로 하락했다"},
        {"url": "r2", "stance": "refutes", "title": "반박2",
         "body": "한국은행 보고서는 물가 상승률이 기사 주장과 달리 둔화됐다고 밝혔다"},
    ]
    r7 = reduce(two_refute)
    assert r7["refuting_effective_count"] == 2, f"F7 expected 2, got {r7}"
    assert r7["verdict_gate"]["can_be_false"] is True, f"F7 gate: {r7['verdict_gate']}"

    # F8: transitive bridge must not over-merge. A~B share wire+topic; B~C share
    # byline+dateline but C is a different topic → C stays separate from {A,B}.
    bridge = [
        {"url": "A", "stance": "supports", "byline": "박기자", "dateline": "서울",
         "title": "물가 대책", "body": "서울=연합뉴스 정부는 물가 안정 대책을 발표했다 소비자물가 상승률 둔화"},
        {"url": "B", "stance": "supports", "byline": "박기자", "dateline": "서울",
         "title": "물가 대책 상보", "body": "연합뉴스 정부는 오늘 물가 안정 대책을 발표했다 소비자물가 상승률 둔화 추가"},
        {"url": "C", "stance": "supports", "byline": "박기자", "dateline": "서울",
         "title": "프로야구 개막", "body": "프로야구가 이번 주말 개막한다 각 구단은 우승을 노린다"},
    ]
    r8 = reduce(bridge)
    assert r8["supporting_effective_count"] == 2, f"F8 expected 2, got {r8}"

    # F9: textless item (no title/body) → EMPTY_TEXT. Counting textless items as
    # independent would open the gate on evidence nobody can cross-check.
    try:
        reduce([{"url": "t1", "stance": "supports"},
                {"url": "t2", "stance": "supports"}])
        raise AssertionError("F9 expected InputError EMPTY_TEXT")
    except InputError as e:
        assert e.code == "EMPTY_TEXT", f"F9 code: {e.code}"
        assert e.index == 0, f"F9 index: {e.index}"

    print("independence.py selftest: OK (9 fixtures)")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return _selftest()
    raw = sys.stdin.read()
    try:
        items_raw = json.loads(raw) if raw.strip() else []
    except json.JSONDecodeError as e:
        print(InputError("BAD_JSON", f"invalid JSON: {e.msg}").as_json(), file=sys.stderr)
        return 2
    try:
        result = reduce(items_raw)
    except InputError as e:
        print(e.as_json(), file=sys.stderr)
        return 2
    except Exception:  # never leak local paths/tracebacks to the caller's report
        print(json.dumps({"error": "internal reducer error", "code": "INTERNAL"},
                         ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
