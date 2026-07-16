---
name: news-fact-checker
description: >
  뉴스 기사 URL을 팩트체크한다. 기사를 읽어 핵심 주장을 추출하고, 웹검색 + 다중 독립
  출처 교차검증으로 각 주장을 검증한 뒤 종합 판정(사실/거짓)을 한국어 리포트로 낸다.
  봇 차단(403/402/WAF) 사이트는 insane-search 엔진으로 우회해 읽는다 — 미설치 시
  사용자 동의를 받아 자동 설치한다. 한국 언론사의 통신사 재발행(연합뉴스 등 한 기사를
  여러 매체가 재출고) 은 하나의 유효 출처로 붕괴시켜 거짓 독립성을 방지한다.
  Korean triggers: 뉴스 팩트체크, 기사 사실확인, 이 기사 진짜야, 가짜뉴스 검증,
  이 뉴스 사실이야, 팩트체크 해줘, 기사 검증. English triggers: fact-check this
  news article, verify this news, is this news true, check this article's claims.
  Trigger when the user gives a news URL and asks whether it is true / to verify it.
  Do NOT trigger for general web search or non-news URLs.
---

<!-- allowed-tools intentionally omitted so the skill inherits the full session toolset:
     the pipeline needs AskUserQuestion (P0 consent gate) and mcp__playwright__browser_*
     (R6 escalation) in addition to Bash / WebSearch / WebFetch / Read. Restricting the
     allowlist would block those plan-mandated flows. -->


# News Fact-Checker

> 뉴스 URL을 받아 **차단이 있어도 본문을 읽고**, 핵심 주장을 **다중 독립 출처로 교차검증**하여
> **종합 판정 + 주장별 판정**을 한국어 리포트로 낸다. 근거 없이는 확정하지 않는다.

경로 표기: `${SKILL_DIR}` = 이 SKILL.md가 있는 디렉터리. 스크립트는 `${SKILL_DIR}/../../scripts/`.
(플러그인 설치 시 `${CLAUDE_PLUGIN_ROOT}/scripts/`로도 접근 가능.)

## Step 0 — 최초 1회 setup (비차단)
작업 시작 전 한 번 실행: `bash "${SKILL_DIR}/../../scripts/setup.sh"`. 출력은 경고성 stderr뿐이며
차단하지 않는다. python3/git 부재 경고가 있으면 리포트 한계에 반영한다.

## 하네스 규칙 (반드시 준수 — 즉흥 판단 금지)

이 규칙들은 두 가지 실패를 막는다: ① 차단 페이지를 본문으로 오인 ② 근거 없이 사실/거짓 단정.

- **H1 — 본문 취득은 항상 어댑터 경유.** 즉흥 `curl`/수동 헤더 금지. `fetch_article.sh`(→ insane-search
  engine) 또는 WebFetch를 쓴다. 검증·사이트별 라우팅(Naver/Jina 등)을 **재구현하지 않는다** — engine이
  6-layer 검증과 라우팅을 소유한다(insane-search R3/R4 No-Site-Name). 상세: [fetch-harness.md](references/fetch-harness.md).
- **H2 — engine 실패는 종료가 아니다(R6).** engine이 exit 1 + `must_invoke_playwright_mcp`/`untried_routes`를
  주면 **직접 MCP Playwright**로 이어받는다. terminal(AUTH_REQUIRED/NOT_FOUND) 또는 소진일 때만 `접근불가`.
  **429/RATE_LIMITED는 종료 아님** — 백오프 후 계속. **WebFetch로 역폴백하지 않는다**(이미 실패한 단계).
- **H3 — 근거 없이 판정 없다.** 어떤 주장도 **독립성 붕괴 후 유효 출처 ≥2** 없이는 `사실`/`거짓`으로
  확정하지 않는다. 못 채우면 `검증불가`. 모든 출처는 URL과 함께 인용하고, **모델 내부지식 vs 웹검증**을
  구분 태깅한다. 출처 날조 절대 금지.
- **H4 — 통신사 재발행은 하나로 센다.** 연합뉴스/뉴스1/뉴시스 등 한 기사를 여러 매체가 재출고한 것은
  `independence.py`로 **1개 유효 출처로 붕괴**시킨 뒤 카운트한다. 상세: [independence.md](references/independence.md).
- **H5 — 예산 준수.** 주장당 WebSearch ≤ 4회, 본문 fetch ≤ 2회, 파이프라인 전역 ≤ 40 step. 예산 소진 시
  남은 주장은 정직히 `검증불가(예산)`로 처리하고 리포트에 명시한다.
- **H6 — 보조 도구.** 이 리포트는 assistive이며 최종 권위가 아니다. 불확실성은 숨기지 않는다.

## 파이프라인 (P0 → P12)

각 단계 상세·통과조건은 [pipeline.md](references/pipeline.md), 판정 라벨은
[verdict-taxonomy.md](references/verdict-taxonomy.md), 리포트 형식은
[report-template.md](references/report-template.md)를 따른다.

- **P0 — 의존성 해석 (1회).** `bash "${SKILL_DIR}/../../scripts/resolve_engine.sh"` 실행.
  - 마지막 stdout 줄이 engine home 경로면 → 이후 `INSANE_SEARCH_HOME`으로 export해 재사용.
  - `DEGRADE`(exit 3)면 → insane-search 미설치. **AskUserQuestion**으로 1회 동의를 구한다
    (옵션: `자동 설치(pinned v0.8.2 clone)` / `설치 없이 진행(축소 모드)`).
    - 동의 → `NFC_CONSENT=yes bash resolve_engine.sh` 재실행. 성공하면 export.
    - 거부/실패 → **capability-reduced 모드**: WebFetch/WebSearch만 사용. 리포트 상단에 도달성 저하 배너.
- **P1 — Intake.** URL 정규화·검증.
- **P2a — pre-fetch 라우팅 (URL/HEAD 신호만).** 동영상 → `yt-dlp` 자막, SNS 포스트 → 포스트 JSON,
  `*.pdf` → PDF 경로. (paywall/언어/홈페이지 여부는 여기서 판단 불가 — P5에서.)
- **P3 — 본문 취득.** [fetch-harness.md](references/fetch-harness.md)의 exit 0/1/2 분기를 그대로 따른다.
  **SUSPECT_OK(exit 1이지만 body 있음)는 body를 사용**하되 신뢰도를 낮추고 표기(escalate 금지).
- **P4 — 메타데이터.** 제목/발행일/매체/기자/데이트라인 추출.
- **P5 — post-fetch 콘텐츠 분류.** 본문+메타 기준: paywalled(본문 길이+구독 마커 휴리스틱)/비한국어/
  홈페이지-vs-기사. 기사가 아니면 유형 명시된 `검증불가`로 **조기 종료**.
- **P6 — 핵심 주장 추출 (3–5개).** 검증가치 높은 사실 주장 위주.
- **P7 — 주장 적격성 필터.** `empirical(검증가능 사실) / opinion(의견) / prediction(예측) / normative(당위)`.
  **empirical만 검증**. 나머지는 `검증 대상 아님(의견/예측)` 버킷. 1차 출처 우선, 시점 유효성 기록.
- **P8 — 근거 수집 (예산 H5).** 주장별 WebSearch + `fetch_article.sh`로 확증 출처 취득(공식발표/공공데이터/
  타 언론사/1차 자료). 차단된 확증 출처도 engine으로 시도.
- **P9 — 독립성 붕괴 + stance.** 수집 출처를 `[{url,title,body,byline,dateline}]` JSON으로 만들어
  `python3 "${SKILL_DIR}/../../scripts/independence.py"`에 stdin으로 넣어 클러스터 붕괴. 각 출처의 stance
  (supports/refutes/unrelated) 분류 — unrelated 제외. **붕괴·필터 후 유효 출처 ≥2**를 강제.
- **P10 — 주장 판정.** 6라벨. 신뢰도는 유효 출처 수·stance 일치·SUSPECT_OK 여부를 반영.
- **P11 — 종합 판정 합성.** 주장별 판정을 종합해 기사 전체 판정 + 신뢰도(상/중/하) + 근거 요약.
- **P12 — 리포트 렌더.** [report-template.md](references/report-template.md) 스키마로 한국어 출력.

## 완료 조건
- 종합 판정 + 핵심 주장별 판정표 + 근거(모든 출처 URL) + 검증 대상 아님 버킷 + 한계·주의 포함.
- 확정 판정한 주장은 **붕괴 후 유효 출처 ≥2**. 미달은 `검증불가`.
- 취득 경로(WebFetch/engine/MCP-Playwright/축소모드)와 SUSPECT_OK/paywall/축소모드를 리포트에 명시.
