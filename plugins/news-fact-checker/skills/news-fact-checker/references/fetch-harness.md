# fetch-harness — engine 어댑터 규율 (thin adapter)

본문 취득은 **얇은 어댑터**다. 검증·사이트 라우팅을 재구현하지 않고 insane-search engine에
위임한다(engine이 6-layer 검증 + SUSPECT_OK 비종료 상태 + Naver/Jina 등 라우팅을 소유,
No-Site-Name R3/R4). 여기 규칙은 exit code/verdict를 해석해 다음 행동을 정하는 것뿐이다.

## 호출 방식 (단일 호출)
```bash
bash "${SKILL_DIR}/../../scripts/fetch_article.sh" "<URL>" [--no-playwright]
```
- **CWD**: `fetch_article.sh`가 자동으로 engine home(`.../skills/insane-search`)으로 `cd` 후
  `python3 -m engine`을 돈다. 직접 engine을 부를 경우 반드시 그 디렉터리에서(또는 PYTHONPATH에
  포함) 실행 — 아니면 `No module named engine`.
- **단일 호출 원칙**: 성공 경로에서 `--json`을 **다시 부르지 않는다**. `--json`은 body를 생략하며,
  2차 호출은 engine 학습 상태를 변형시켜 결과가 발산할 수 있다. 실패 시 R6 필드는 **첫 호출의
  stderr**(engine이 출력한 `⛔ NOT EXHAUSTED` 블록)에서 이미 파싱된다.
- 출력: stdout = 본문, stderr = 진단 + 한 줄 `NFC_STATUS {json}`
  (`{exit, ok, verdict, grid_exhausted, stop_reason, untried_routes[], must_invoke_playwright_mcp, engine_home}`).

## exit code + verdict 분기 (우선순위 순)

> **verdict 표기는 소문자.** engine과 `NFC_STATUS`는 소문자로 낸다(`weak_ok`, `suspect_ok`,
> `auth_required`, `not_found`, `challenge`, `blocked`, `rate_limited`, `unknown`). 아래 분기는 모두 소문자 기준.

### exit 0 (`ok=true`) — verdict ∈ {STRONG_OK, WEAK_OK}
→ **본문 사용.** 끝. (`--json` 호출 금지.)

### exit 1 (`ok=false`) — 본문은 여전히 stdout에 실려 있음
`NFC_STATUS`의 verdict로 분기. **아래 순서대로**, 먼저 맞는 것 적용:

1. **verdict == `suspect_ok` 이고 body 비어있지 않음 → 본문 사용, 신뢰도 하향 + 리포트 표기, escalate/접근불가 선언 안 함.**
   (이 분기가 `must_invoke_playwright_mcp=True`보다 **우선**한다. SUSPECT_OK는 engine이 소프트-취득한
   본문이 이미 있는데도 `ok=False`로 돌려주는 케이스 — 대개 한국 뉴스 WAF의 `_abck` 센서 미해결.
   여기서 MCP로 재차 태우면 예산만 낭비하고 이미 있는 본문을 버린다.)
2. **verdict ∈ {`auth_required`, `not_found`} → terminal → `접근불가(사유)`.** 더 시도하지 않는다.
3. **verdict ∈ {`challenge`, `blocked`, `rate_limited`, `unknown`} → non-terminal.**
   `must_invoke_playwright_mcp == true` 또는 `untried_routes` 비어있지 않음 → **R6 MCP escalation**:
   - `mcp__playwright__browser_navigate` → 페이지 로드
   - `mcp__playwright__browser_network_requests` → 내부 `/api`·`/graphql`·`.json` 엔드포인트 탐지
   - 그 엔드포인트를 `fetch_article.sh`(= engine)로 **재호출** (API 레이어는 WAF가 얕음), 또는
   - `mcp__playwright__browser_snapshot`으로 렌더된 HTML 회수
   - **`rate_limited`(429)는 종료 아님** — 백오프 후 재시도/다른 TLS/MCP로 우회. 조기 `접근불가` 금지.
4. **`grid_exhausted == true` 이고 남은 route 없음 → `접근불가(소진)`.**

### exit 2 — engine fatal (FetchResult/JSON 없음)
`NFC_STATUS.stop_reason == "error"`. engine 자체 예외. exit 1(차단)과 **구분**한다:
→ 재시도 1회 후에도 exit 2면 engine-failure로 처리 → capability-reduced 모드 또는 명확한 에러 보고.

### exit 3 — engine 미해석 (DEGRADE)
resolve 실패. capability-reduced 모드(WebFetch/WebSearch만)로 진행 + 리포트 배너.

## MCP preflight
R6 escalation(Tier2)이 필요한데 MCP Playwright 서버가 **연결되어 있지 않으면**("configured ≠ connected"),
가짜 성공을 만들지 말고 정직하게 `접근불가(도구 미가용)`으로 표기한다.

## 금지
- 즉흥 `curl`/수동 헤더 조합.
- 성공 경로에서 `--json` 2차 호출(double-fetch).
- engine 실패 후 WebFetch로 역폴백(진입 단계에서 이미 실패 → 순환 no-op).
- 사이트 도메인/셀렉터 하드코딩(engine에 위임).
- `untried_routes`/`must_invoke_playwright_mcp`가 남았는데 `접근불가` 선언.
