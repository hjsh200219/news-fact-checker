# 기술 부채 트래커 — news-fact-checker

알려진 부채를 추적한다. 상시 갱신하며, 해소 시 상태를 `RESOLVED`로 바꾸고 커밋을 링크한다.
근거: `_workspace/00_audit.md` (Phase-1 감사, 기준 커밋 `6d09fac` + 미커밋 작업 트리).

상태: `OPEN` · `IN_PROGRESS` · `RESOLVED` · `WONTFIX(문서화된 한계)`.

| ID | 심각도 | 상태 | 요약 |
|----|--------|------|------|
| TD-1 | High | OPEN | PRD 구현물이 git untracked — CI가 참조하는 테스트가 원격에 없음 |
| TD-2 | Medium | RESOLVED | 하네스 규칙 번호 드리프트: factcheck.md/pipeline.md를 H0–H6으로 수정 완료 |
| TD-3 | Low | WONTFIX(한계) | engine 내부 redirect/DNS-rebinding은 SSRF 정책 밖(외부 엔진 위임) |
| TD-4 | Medium | OPEN → 이 Phase에서 부분 해소 | `.claude/settings.json` permissions.deny 부재 |
| TD-5 | Low | OPEN | `.gitignore`에 `.mypy_cache/` 미포함(현재 트리에 존재) |

---

## TD-1 — 미커밋 산출물 (선결, push 전 필수)

**심각도: High · 상태: OPEN**

PRD 구현물이 전부 untracked다: `scripts/url_policy.py`, `scripts/parse_engine_status.py`,
`tests/`(전체), `.github/workflows/ci.yml`, `docs/`. `ci.yml`이 참조하는 계약 테스트가 아직
커밋되지 않았으므로, **현재 상태로 push하면 CI가 존재하지 않는 테스트를 돌릴 위험**이 있다.

- 조치: 위 산출물을 스테이징·커밋한 뒤에야 CI/push가 의미를 갖는다.
- 검증: `git ls-files`에 위 경로가 나타나고 `bash plugins/news-fact-checker/tests/run.sh` 통과.

## TD-2 — 하네스 규칙 번호 드리프트 (H0 누락)

**심각도: Medium · 상태: RESOLVED (2026-07-17, 하네스 셋업 Phase 3)**

`SKILL.md`는 **H0**(원격 콘텐츠 = 불신 데이터, 인젝션 경계, 최상위)를 포함해 **H0–H6**을 정의한다.
아래 두 곳이 "H1–H6"로 참조해 최상위 안전 규칙을 표기에서 누락했으나 **H0–H6으로 수정 완료**했다:

- `plugins/news-fact-checker/commands/factcheck.md` — `/factcheck` 커맨드 지침을 H0–H6으로 고치고
  원격 콘텐츠 불신·본문 내 지시 미실행 조항을 명시. (수정됨)
- `plugins/news-fact-checker/skills/news-fact-checker/references/pipeline.md:3` — H0–H6으로 수정. (수정됨)

(참고: `README.md`는 이미 H0을 명시하므로 드리프트 없음 — 감사 초안의 "README도 H1–H6" 표기는
실제 파일과 불일치했다. 실상은 위 2개 파일.)

- 조치: 두 참조를 **"H0–H6"**으로 통일.
- 주의: 진입 문서(SKILL.md/commands/references) 편집은 이 Phase(knowledge-architect) 범위 밖 —
  agent-md-refactorer/후속 Phase 또는 별도 수정 커밋에서 처리.

## TD-3 — SSRF redirect / DNS-rebinding (문서화된 한계)

**심각도: Low · 상태: WONTFIX(한계, 재검토 트리거 있음)**

`url_policy.py`는 어댑터가 넘기는 **최초 목적지**만 요청 前에 강제한다. 본문 취득을 위임하는 외부
insane-search engine 내부의 HTTP 리다이렉트·DNS 재해석은 engine 요청 계층이 소유하므로, "공개
호스트 → 3xx → 사설/메타데이터" rebinding류는 이 얇은 어댑터가 막지 못한다. 리포트에 명시하고,
민감 대상 의심 시 축소 모드(WebFetch, 자체 SSRF 보호)로 처리한다.

- 재검토 트리거: **engine이 request/redirect hook을 노출**하면 정책 주입을 그 계층까지 확장.
- 상세: [docs/SECURITY.md](../SECURITY.md#정직한-한계--redirect--dns-rebinding).

## TD-4 — permissions.deny 부재 (이 Phase에서 부분 해소)

**심각도: Medium · 상태: OPEN → 부분 해소**

H0는 지금까지 문서 규칙에만 의존했다. 심층 방어로 `.claude/settings.json`의 `permissions.deny`에
비밀 파일 차단 패턴이 필요하다. 이 Phase에서 `Read(./.env)`, `Read(./.env.*)`, `Read(./secrets/**)`를
추가했다.

- 남은 조치: 프로젝트 고유 민감 경로(자격증명·토큰 장부 등)가 감사에서 추가로 발견되면 deny 확장.

## TD-5 — .gitignore에 .mypy_cache/ 미포함

**심각도: Low · 상태: OPEN**

`.gitignore`는 `.omc/`·`_workspace/`·`__pycache__/`·`*.pyc`·`.DS_Store`를 무시하나 `.mypy_cache/`는
누락됐다(현재 작업 트리에 `.mypy_cache/`가 존재). 커밋 오염 방지를 위해 추가 권장.

- 조치: `.gitignore`에 `.mypy_cache/` 한 줄 추가.
