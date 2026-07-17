# ARCHITECTURE.md — news-fact-checker

도메인 맵, 레이어 구조, 의존성 방향, 신뢰/강제 경계, 상태 계약을 기술한다.
행동 계약의 SSOT는 [SKILL.md](plugins/news-fact-checker/skills/news-fact-checker/SKILL.md);
이 문서는 **왜 그런 구조인가**를 설명한다.

## 도메인 한 줄 요약

공개 뉴스 URL → (차단 우회) 본문 취득 → 핵심 주장 추출 → 다중 독립 출처 교차검증
→ 결정론적 게이트로 확정 판정 → 한국어 리포트. 두 축의 안전을 코드로 강제한다:
**거짓 독립성 방지**(reducer)와 **네트워크/인젝션 신뢰 경계**(url_policy + H0).

## 레이어 (위 → 아래, 아래로 갈수록 저수준)

| 레이어 | 위치 | 책임 |
|--------|------|------|
| L0 매니페스트 | `.claude-plugin/marketplace.json`, `plugins/*/.claude-plugin/plugin.json` | 마켓플레이스·플러그인 등록 메타데이터(JSON) |
| L1 진입/명령 | `plugins/*/commands/factcheck.md` | `/factcheck <url>` 슬래시 커맨드 → 스킬로 위임 |
| L2 하네스 계약(문서) | `skills/news-fact-checker/SKILL.md` + `references/` | **행동을 규정하는 최상위 계약.** H0–H6 규칙, P0–P12 파이프라인, 판정 taxonomy, 리포트 스키마 |
| L3 로직(스크립트) | `plugins/*/scripts/` | Python 순수함수 계약 + Bash 어댑터. 문서가 기술한 게이트를 결정론적으로 **강제** |
| L4 외부 엔진(위임) | insane-search (`python3 -m engine`, 리포 밖) | 본문 취득·6-layer 검증·사이트 라우팅 소유. 동의 기반 설치 |
| L5 테스트/픽스처 | `plugins/*/tests/` | 네트워크 없는 계약 테스트 + `fake_engine` fixture + 인젝션 fixture |
| L6 CI | `.github/workflows/ci.yml` | 위 계층을 Linux/macOS에서 게이트 |

### L3 스크립트 구성

- **Python 계약(순수함수, stdlib only)**
  - `independence.py` (363) — Evidence Reducer. stance별 신디케이션 클러스터 붕괴 → `verdict_gate`. `--selftest` 8 픽스처.
  - `url_policy.py` (180) — fetch 경계의 네트워크 목적지 정책(SSRF pre-flight). `classify_url()` + `--selftest`.
  - `parse_engine_status.py` (130) — engine stderr → 기계 status. verdict enum 검증, phrasing drift를 명시적 호환 실패로 승격.
- **Bash 어댑터**
  - `fetch_article.sh` (151) — thin 단일 호출 어댑터. url_policy pre-flight → engine home cd → `python3 -m engine` (wall-clock timeout) → parse_engine_status.
  - `resolve_engine.sh` (184) — engine 해석 ladder(env→cache→marketplace→vendor→consent clone→DEGRADE). commit-pin + atomic install.
  - `setup.sh` (19) — 최초 1회 비차단 사전 점검(python3/git 존재 경고).

## 의존성 방향 (허용 에지)

```
manifests (L0)
   ▲
command factcheck.md (L1)  ──delegates──▶  SKILL.md + references (L2)
                                              │ prescribes
                                              ▼
                              scripts (L3)
                                fetch_article.sh ──uses──▶ url_policy.py        (pre-flight)
                                fetch_article.sh ──uses──▶ resolve_engine.sh    (engine home)
                                fetch_article.sh ──uses──▶ parse_engine_status.py (status)
                                (independence.py: 스킬이 stdin으로 직접 구동, 순수함수)
                                              │ invokes (delegated)
                                              ▼
                              insane-search engine (L4, 리포 밖)
                                              ▲
                              tests + fake_engine (L5) ──drive──▶ scripts
                              ci.yml (L6) ──gate──▶ L3/L5
```

규칙:
- **문서가 스크립트를 기술하고, 스크립트가 엔진을 호출하고, 테스트가 fake 엔진으로 스크립트를 구동한다.** 역방향 없음.
- Python 계약 3종은 서로 import하지 않는다(각각 독립 순수함수 + CLI). 어댑터가 셋을 조립한다.
- L3는 사이트 도메인/셀렉터를 **하드코딩하지 않는다** — 검증·라우팅은 L4에 위임.
- 신규 런타임 의존성 금지(stdlib only). L4 엔진만 첫 실 fetch 시 자체 의존성 설치.

## 신뢰 / 강제 경계

| 경계 | 강제 위치 | 성격 |
|------|-----------|------|
| **SSRF pre-flight** (요청 前) | `url_policy.py` (fetch_article.sh 내부) | 어댑터가 넘기는 **최초 목적지**를 네트워크 없이 검사. 강제 가능. |
| **redirect/DNS 재해석** (요청 中) | insane-search engine 요청 계층 | thin 어댑터가 patch하지 않음 → **engine에 위임된 한계**(rebinding류). 정직 고지. |
| **H0 인젝션 경계** | SKILL.md H0 + fetch-harness.md + `tests/fixtures/` | 원격 본문·stderr·근거 페이지 = 불신 데이터. `NFC_STATUS`만 기계 신호로 신뢰. |
| **확정 판정 게이트** | `independence.py::verdict_gate` | stance별 붕괴 후 유효 출처 ≥2에서만 확정. 프롬프트 우회 불가. |
| **공급망 핀** | `resolve_engine.sh` | 40자 SHA = 배포 계약, 태그 = 표시용. HEAD 불일치/smoke 실패 시 미설치. |

상세 위협 모델은 [docs/SECURITY.md](docs/SECURITY.md).

## 상태 계약 (NFC_STATUS)

`fetch_article.sh`는 stdout=본문, stderr에 한 줄 `NFC_STATUS <json>`을 낸다. 필드:

```
schema_version, exit, ok, parse_ok, status_source, verdict, grid_exhausted,
stop_reason, untried_routes[], must_invoke_playwright_mcp,
engine_home, engine_version, engine_commit
```

- `verdict`(소문자 enum): `strong_ok`·`weak_ok`·`suspect_ok`·`auth_required`·`not_found`·`challenge`·`blocked`·`rate_limited`·`unknown`.
- `parse_ok`: engine phrasing drift/미인식 verdict → `false` + `stop_reason=status_unparsed` (조용한 빈 verdict 금지).
- `status_source`: `engine_line`(구조화 라인 발견) | `exit_code_fallback` | `adapter`.
- `engine_version`/`engine_commit`: `.nfc-provenance.json`에서 흐르는 재현성 provenance(L-1).

### 어댑터 exit code

| exit | 의미 | 후속 행동 |
|-----:|------|-----------|
| 0 | ok (verdict ∈ strong_ok/weak_ok) | 본문 사용, 종료 (`--json` 재호출 금지) |
| 1 | blocked-escalatable (timeout 포함, 비종료) | verdict 분기 — suspect_ok는 본문 사용/신뢰도↓, terminal(auth_required/not_found)은 접근불가, 그 외 R6 MCP escalation |
| 2 | engine-fatal (FetchResult/JSON 없음, `stop_reason=error`) | 재시도 1회 후 engine-failure → 축소 모드/명확한 에러 |
| 3 | engine 미해석 (DEGRADE) | capability-reduced 모드(WebFetch/WebSearch만) + 리포트 배너 |
| 4 | unsafe_url (정책 거부, `stop_reason=unsafe_url`) | **네트워크 요청 없음.** 재시도·우회 금지. 원문이면 `검증불가(안전하지 않은 URL)` |

분기 우선순위·규율은 [references/fetch-harness.md](plugins/news-fact-checker/skills/news-fact-checker/references/fetch-harness.md).
