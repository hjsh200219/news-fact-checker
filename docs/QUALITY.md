# QUALITY.md — news-fact-checker 품질 게이트

이 리포지터리의 품질 기준. **순수 stdlib Python + Bash + Markdown 플러그인** — 런타임 의존성
없음(테스트/CI는 `mypy`만 추가). ESLint·번들러·커버리지 러너·DB 마이그레이션류는 N/A.

모든 게이트는 **네트워크 없이** 돈다. 로컬 미러는 한 줄:

```bash
bash plugins/news-fact-checker/tests/run.sh
```

CI(`.github/workflows/ci.yml`)가 같은 게이트를 Linux·macOS에서 강제한다.

## 게이트 목록

| # | 게이트 | 명령 | 잠그는 것 |
|--:|--------|------|-----------|
| 1 | Shell 문법 | `bash -n plugins/news-fact-checker/scripts/*.sh` | 어댑터/리졸버/셋업 파싱 오류 |
| 2 | Python 컴파일 | `python3 -m py_compile <scripts>/*.py <tests>/fake_engine/engine/*.py` | 문법 오류(프로덕션 + fake_engine fixture) |
| 3 | 타입 체크 | `python3 -m mypy --ignore-missing-imports <3 scripts>` | 프로덕션 Python 3종의 타입 계약 |
| 4 | 계약 테스트 | `python3 -m unittest discover -s <tests> -p 'test_*.py'` | 아래 "테스트가 잠그는 것" |
| 5 | Reducer selftest | `python3 <scripts>/independence.py --selftest` | 8 픽스처 붕괴/독립성 회귀 |
| 6 | URL policy selftest | `python3 <scripts>/url_policy.py --selftest` | 스킴/IP-리터럴/DNS 해석 정책 회귀 |
| 7 | 매니페스트 검증 | `python3 -m json.tool <marketplace.json / plugin.json>` | JSON schema-shape |
| 8 | 플러그인 검증 | `claude plugin validate .` · `claude plugin validate plugins/news-fact-checker` | 마켓플레이스 + 플러그인 매니페스트 |

> `<scripts>` = `plugins/news-fact-checker/scripts`, `<tests>` = `plugins/news-fact-checker/tests`.
> 타입 체크 대상 3종: `independence.py`, `url_policy.py`, `parse_engine_status.py`.
> selftest 6은 `run.sh`에 포함(CI는 5를 별도 스텝으로 실행 — url_policy selftest는 유닛 테스트가 커버).

## 테스트가 잠그는 것 (네트워크-free 계약)

`tests/`는 fake `engine`(env 시나리오로 구동되는 fixture)으로 실 네트워크 없이 실패 분기를 고정한다:

- **`test_independence.py`** — reducer stance 게이트: `unrelated` 카운트 전 제거, stance별 붕괴,
  `supporting/refuting_effective_count`, `verdict_gate`(can_be_true/can_be_false), 클러스터 링크 사유/유사도.
  입력 오류 계약(`TOP_NOT_LIST`/필드 누락/`BAD_JSON` → exit 2, traceback 없음).
- **`test_url_policy.py`** — 목적지 정책: 스킴 거부, userinfo, loopback/private/link-local/reserved/multicast,
  메타데이터(169.254.169.254), IPv4-mapped IPv6, DNS로 사설 해석되는 공개 호스트, 공개 호스트 통과.
- **`test_parse_engine_status.py`** — engine 상태 파싱: verdict enum 검증, phrasing drift → `parse_ok:false` +
  `stop_reason:status_unparsed`(조용한 빈 verdict 금지), `engine_line` vs `exit_code_fallback`.
- **`test_fetch_adapter.py`** — 어댑터 exit 계약: 0/1/2/3/4, `suspect_ok`(본문 사용+신뢰도↓),
  `rate_limited`(비종료), `timeout`(비종료), `unsafe_url`(네트워크 없음).
- **`test_resolve_engine.py`** — 리졸버: commit-pin 불일치 시 미설치·기존 사본 보존, smoke-test 실패 보존,
  원자적 설치(temp→swap), 동의 없으면 clone 안 함.
- **`test_agent_scenarios.py`** + **`AGENT_SCENARIOS.md`** — 유닛으로 못 잡는 행동(AC-6/7/8/13) 수동 시나리오
  + 인젝션 하네스 규칙(원격 본문 지시문 불복종) 검증.

## 규율

- **결정론.** 확정 판정 게이트·URL 정책·상태 파싱은 순수함수 + 픽스처로 잠근다. 임계값 변경
  (`TAU`/`TAU_WIRE`/`TAU_TOPIC`/`CHAR_K`)은 반드시 `--selftest` 벤치마크 결과와 함께 리뷰한다.
- **stdlib only.** 제품 코드에 신규 런타임 의존성 추가 금지. 필요하면 먼저 tech-debt로 올린다.
- **명시적 실패 > 조용한 성공.** engine phrasing drift, 빈 verdict, 스키마 오류는 loud fail로 승격.
- **사이트 하드코딩 금지.** 검증·라우팅은 engine에 위임(재구현 금지).
- **새 실패 분기는 fixture부터.** 네트워크에 의존하는 테스트를 추가하지 않는다 — fake_engine을 확장한다.

## 완료 조건

작업은 상태로 끝난다: `DONE` | `DONE_WITH_CONCERNS` | `BLOCKED` | `NEEDS_CONTEXT`.
`DONE`은 위 8개 게이트가 모두 통과할 때만. TODO 플레이스홀더·`skip`/`only` 테스트·스텁은 blocker다.
