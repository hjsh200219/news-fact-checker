# 파이프라인 상세 (P0 → P12)

각 단계: 입력 → 행동 → 통과조건. SKILL.md의 하네스 규칙(H1–H6)을 전제로 한다.

## P0 — 의존성 해석 (1회)
- 행동: `resolve_engine.sh` 실행. 성공 시 마지막 stdout 줄 = engine home → `export INSANE_SEARCH_HOME=...`.
  `DEGRADE`(exit 3) → AskUserQuestion 동의 게이트 → 동의 시 `NFC_CONSENT=yes` 재실행, 거부 시 축소 모드.
- 통과: engine home 확보(정상) 또는 축소 모드 플래그 설정.

## P1 — Intake
- 행동: URL 정규화(트래킹 파라미터 제거는 하되 경로 보존), 스킴 검증.
- 통과: 유효한 http(s) URL.

## P2a — pre-fetch 라우팅 (URL/HEAD 신호만)
- 행동: 확장자/도메인 패턴으로만 분기. 동영상 플랫폼 → `yt-dlp --dump-json`/자막, SNS 포스트 → 포스트 JSON,
  `*.pdf` → PDF 추출 경로. **본문을 봐야 알 수 있는 것(paywall/언어/기사여부)은 여기서 하지 않는다.**
- 통과: 라우팅 결정(대부분 "일반 기사 → P3").

## P3 — 본문 취득
- 행동: [fetch-harness.md](fetch-harness.md)의 exit 0/1/2 분기. SUSPECT_OK는 본문 사용+신뢰도 하향.
  차단 시 R6 MCP escalation. 축소 모드면 WebFetch만.
- 통과: 본문 확보(취득 경로 기록) 또는 정직한 `접근불가(사유)`.

## P4 — 메타데이터
- 행동: 제목, 발행일(가능하면 수정일도), 매체명, 기자명, 데이트라인 추출. OGP/JSON-LD 활용.
- 통과: 최소 제목+매체+발행일.

## P5 — post-fetch 콘텐츠 분류
- 행동: paywall 휴리스틱(본문 length가 비정상적으로 짧음 + "구독"/"로그인"/"subscribe" 마커),
  언어 감지(비한국어면 그에 맞게 처리하거나 한계 명시), 홈페이지-vs-기사(단일 기사 구조 여부).
- 통과: "검증 가능한 단일 기사"면 계속. 아니면 유형 명시 `검증불가` 조기 종료.

## P6 — 핵심 주장 추출 (3–5개)
- 행동: 기사에서 검증가치 높은 **사실 주장** 3–5개 선별. 제목·리드·수치·인용·인과 주장 우선.
- 통과: 3–5개 주장 목록(각 주장은 원문 근거 문장과 함께).

## P7 — 주장 적격성 필터
- 행동: [verdict-taxonomy.md](verdict-taxonomy.md)의 적격성 라벨 부여. empirical만 검증 대상,
  나머지는 `검증 대상 아님` 버킷. 예측의 근거로 쓰인 현재 사실은 별도 empirical 주장으로 분리.
- 통과: 검증 대상 주장 확정 + 제외 버킷 기록.

## P8 — 근거 수집 (예산 H5: 주장당 WebSearch ≤4, fetch ≤2, 전역 ≤40)
- 행동: 주장별로 WebSearch(사건명/고유명사/수치 조합) → 확증 후보 URL 확보 → `fetch_article.sh`로 본문
  취득. 1차 자료(당사자 공식 발표/원문/공공데이터) 우선 탐색. 차단된 확증 출처도 engine으로 시도.
- 통과: 주장별 확증 후보 출처 집합. 예산 소진 시 남은 주장 `검증불가(예산)`.

## P9 — 독립성 붕괴 + stance
- 행동: 주장별 수집 출처를 `[{url,title,body,byline,dateline}]`로 `independence.py`에 넣어 붕괴
  → `effective_count`. 각 출처 stance(supports/refutes/unrelated) 분류, unrelated 제외.
- 통과: 주장별 **붕괴 후 유효 출처 수** + stance 확정.

## P10 — 주장 판정
- 행동: [verdict-taxonomy.md](verdict-taxonomy.md) 6라벨 부여. 유효 출처 <2면 `검증불가`. 신뢰도 산정.
- 통과: 주장별 판정 + 신뢰도 + 인용 출처.

## P11 — 종합 판정 합성
- 행동: 주장별 판정 종합 → 기사 전체 판정 + 신뢰도(상/중/하) + 1줄 근거 요약.
- 통과: 종합 판정 확정.

## P12 — 리포트 렌더
- 행동: [report-template.md](report-template.md) 스키마로 한국어 리포트 출력.
- 통과: 모든 섹션 채워짐(출처 URL 전부 포함, 한계·주의 명시, assistive 면책).
