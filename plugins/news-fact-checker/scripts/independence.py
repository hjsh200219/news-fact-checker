#!/usr/bin/env python3
"""independence.py — collapse wire-syndication clusters into effective sources.

Korean news is dominated by wire syndication: one 연합뉴스/뉴스1/뉴시스 story is
reprinted (often with a rewritten lead/headline) by many outlets. Counting raw
"sources" then overstates independence. This script collapses each syndication
cluster to ONE effective source before the caller enforces ">=2 independent".

Contract (pure stdlib, no external deps):
  stdin  : JSON list of {url, title, body, byline, dateline}
  stdout : JSON {"clusters": [[idx, ...], ...], "effective_count": N}

Collapse rule (wire-token DOMINANT — because rewritten leads push full-text
similarity below a pure near-duplicate threshold):
  link i,j  if  (share a wire token AND jaccard >= TAU_WIRE)      # wire-assisted
            or  (byline match AND dateline match)                  # same reporter/place
            or  (jaccard >= TAU)                                   # pure near-duplicate
Connected components = clusters; effective_count = number of clusters.

Run `independence.py --selftest` to execute built-in fixtures (exit 0 on pass).
"""
from __future__ import annotations

import json
import re
import sys

TAU = 0.85        # pure near-duplicate threshold (char-trigram Jaccard)
TAU_WIRE = 0.35   # lower bar when a shared wire token is present (rewritten leads)
CHAR_K = 3        # character n-gram size (robust to Korean particles / word order)

# Wire-service / syndication attribution tokens. Presence signals the item is a
# reprint of an upstream agency story, not independent reporting.
WIRE_TOKENS = [
    "연합뉴스", "연합newstv", "yonhap", "뉴스1", "news1", "뉴시스", "newsis",
    "(서울=", "(부산=", "(대구=", "(광주=", "(대전=", "제공", "=연합",
    "ap통신", "associated press", "reuters", "로이터", "afp", "블룸버그", "bloomberg",
]


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


def _linked(a: dict, b: dict, sa: set[str], sb: set[str], wa: set[str], wb: set[str]) -> bool:
    sim = jaccard(sa, sb)
    if sim >= TAU:
        return True
    if _byline_dateline_match(a, b):
        return True
    if (wa & wb) and sim >= TAU_WIRE:      # wire-token dominant
        return True
    return False


def collapse(items: list[dict]) -> dict:
    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[max(rx, ry)] = min(rx, ry)

    shingles = [_shingles(f"{it.get('title','')} {it.get('body','')}") for it in items]
    wires = [wire_tokens_of(it) for it in items]

    for i in range(n):
        for j in range(i + 1, n):
            if _linked(items[i], items[j], shingles[i], shingles[j], wires[i], wires[j]):
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    clusters = [sorted(g) for g in groups.values()]
    clusters.sort(key=lambda c: c[0])
    return {"clusters": clusters, "effective_count": len(clusters)}


# --------------------------------------------------------------------------- #
def _selftest() -> int:
    # Fixture 1: one 연합뉴스 wire story + 3 reprints with rewritten leads → 1 cluster.
    wire_body = ("서울=연합뉴스 정부는 오늘 물가 안정 대책을 발표했다 소비자물가 상승률이 "
                 "둔화되고 있다고 밝혔다 관계 부처는 추가 대책을 검토 중이다")
    reprints = [
        {"url": "a", "title": "정부 물가 대책 발표", "body": wire_body,
         "byline": "", "dateline": "서울"},
        {"url": "b", "title": "물가 안정 대책 나왔다", "byline": "", "dateline": "서울",
         "body": ("연합뉴스 보도 정부가 물가 안정 대책을 발표했다고 오늘 전했다 소비자물가 "
                  "상승률이 둔화되고 있다고 밝혔다 관계 부처는 추가 대책을 검토 중이다")},
        {"url": "c", "title": "정부, 추가 물가대책 검토", "byline": "", "dateline": "서울",
         "body": ("정부는 오늘 물가 안정 대책을 발표했다 소비자물가 상승률이 둔화되고 있다고 "
                  "연합뉴스에 밝혔다 관계 부처는 추가 대책을 검토 중이라고 제공했다")},
        {"url": "d", "title": "물가 대책 발표 소식", "byline": "", "dateline": "서울",
         "body": ("오늘 정부는 물가 안정 대책을 발표했다 소비자물가 상승률 둔화 관계 부처 추가 "
                  "대책 검토 중 서울=연합뉴스")},
    ]
    r1 = collapse(reprints)
    assert r1["effective_count"] == 1, f"fixture1 expected 1, got {r1}"

    # Fixture 2: two genuinely independent stories on different topics → 2 clusters.
    indep = [
        {"url": "x", "title": "국내 축구 국가대표 명단 발표", "byline": "김기자", "dateline": "서울",
         "body": "대한축구협회는 다음 달 평가전을 위한 국가대표 명단을 발표했다 새 감독의 첫 선발이다"},
        {"url": "y", "title": "반도체 수출 지난달 증가", "byline": "이기자", "dateline": "세종",
         "body": "산업통상자원부는 지난달 반도체 수출이 전년 대비 크게 늘었다고 발표했다 메모리 가격 회복이 배경이다"},
    ]
    r2 = collapse(indep)
    assert r2["effective_count"] == 2, f"fixture2 expected 2, got {r2}"

    # Fixture 3: two same-wire but different-topic stories must NOT collapse.
    same_wire_diff_topic = [
        {"url": "p", "title": "물가 대책", "byline": "", "dateline": "서울",
         "body": "서울=연합뉴스 정부는 물가 안정 대책을 발표했다 소비자물가 상승률 둔화"},
        {"url": "q", "title": "태풍 북상", "byline": "", "dateline": "부산",
         "body": "부산=연합뉴스 태풍이 북상하면서 남부 지방에 강풍과 폭우가 예상된다"},
    ]
    r3 = collapse(same_wire_diff_topic)
    assert r3["effective_count"] == 2, f"fixture3 expected 2, got {r3}"

    print("independence.py selftest: OK (3 fixtures)")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return _selftest()
    raw = sys.stdin.read()
    items = json.loads(raw) if raw.strip() else []
    if not isinstance(items, list):
        print("stdin must be a JSON list", file=sys.stderr)
        return 2
    print(json.dumps(collapse(items), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
