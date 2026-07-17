# 하네스 원칙 — news-fact-checker

이 리포지터리에 적용하는 하네스 엔지니어링 채점 원칙. 채점은 "존재 여부"가 아니라
**코드/테스트로 강제되는가**를 본다(문서만 있고 강제 없으면 감점). 채점 기준 SSOT.

## 공유 기반 원칙

- **리포지터리 = 기록 시스템.** 결정과 계약은 사람 기억이 아니라 파일로 남는다.
- **진입 문서는 map, not handbook (~100줄).** `AGENTS.md`는 목차, 상세는 링크된 문서가 SSOT.
- **아키텍처 기계적 강제.** 규칙은 문서로 말하고 코드/테스트가 강제한다. 이 리포의 강제점:
  `verdict_gate`(판정), `url_policy.py`(SSRF), `resolve_engine.sh`(공급망 핀), fake_engine 계약 테스트.
- **Search Before Building.** 새 로직 전 기존 순수함수/픽스처를 먼저 찾는다(중복 게이트 금지).
- **작업은 상태로 끝난다:** `DONE` | `DONE_WITH_CONCERNS` | `BLOCKED` | `NEEDS_CONTEXT`.

## Anthropic 하네스 원칙

- **회의적 평가 원칙 (Skeptical Evaluation).** 검증 에이전트는 자기 평가 편향을 상쇄하기 위해
  기본적으로 **"증명될 때까지 미흡"** 관점으로 채점한다(GAN-inspired evaluator). 이 리포에서:
  "테스트가 존재한다"가 아니라 "그 테스트가 실제 실패 분기를 잠그는가"를, "문서가 규칙을 적었다"가
  아니라 "그 규칙을 코드가 강제하는가"를 확인한다. 작성 패스와 검증 패스는 분리한다(같은 컨텍스트
  자기 승인 금지).
- **하네스 단순화 원칙 (Harness Simplification).** 하네스의 모든 컴포넌트는 "현재 모델이 스스로
  못하는 것"에 대한 가정을 인코딩한다. 모델이 개선되면 그 가정을 주기적으로 재검증해 불필요한
  복잡도를 제거한다. 이 리포의 명시적 가정 예: 모델은 신디케이션 붕괴/독립성 카운트를 즉흥으로
  신뢰성 있게 못 한다(→ `independence.py`), phrasing drift를 조용히 넘긴다(→ `parse_engine_status.py`).
  이 가정이 깨지면 해당 스크립트를 축소 후보로 재검토한다.
- **Phase 독립 에이전트 원칙 (Context Reset > Compaction).** 각 Phase 에이전트는 독립 컨텍스트에서
  실행한다 — 대화 요약 유지(compaction)가 아니라 완전 초기화 + 구조화된 핸드오프(context reset)다.
  context anxiety를 방지하고 깨끗한 추론 환경을 보장한다. 핸드오프 산출물: `_workspace/*.md`,
  `docs/harness/*`, tech-debt-tracker.
- **Sprint Contract 원칙.** 수정 전 평가자-수정자가 **기대 효과를 사전 합의**한다("이 변경으로 어떤
  게이트/점수가 어떻게 개선되는가"). 합의 없는 투기적 리팩터 금지. 이 리포에서 임계값
  (`TAU`/`TAU_WIRE`/`TAU_TOPIC`) 변경은 `--selftest` 벤치마크 예상 결과를 계약으로 명시한 뒤 진행.
- **채점 앵커 원칙 (Scoring Anchors).** 각 원칙의 점수대별 **구체적 예시**를 고정해 채점 기준
  드리프트를 방지한다(아래 루브릭).

## 채점 루브릭 (0–5, 앵커 포함)

각 차원 0–5. 앵커는 이 리포 기준의 구체 예시다.

### D1. 문서 / 진입 (map-not-handbook)
- **0–1:** repo-level 진입 문서 없음. SKILL.md만 존재(실행 관점).
- **2–3:** AGENTS.md 존재하나 상세를 인라인(handbook화) 또는 링크 깨짐.
- **4–5:** AGENTS.md가 ~100줄 맵, 모든 상세는 링크된 SSOT, Invariants + Health Stack 명시. ← **목표**

### D2. 아키텍처 강제
- **0–1:** 규칙이 프롬프트에만 존재, 코드 강제 없음.
- **2–3:** 일부 강제(예: 판정 게이트)만 코드화, 나머지는 문서 규칙.
- **4–5:** 판정·SSRF·공급망·상태 파싱이 모두 순수함수/스크립트로 강제 + 픽스처 회귀. ← **현재 근접**

### D3. 테스트 / 검증
- **0–1:** 테스트 없음 또는 네트워크 의존.
- **2–3:** 일부 계약 테스트, CI 없음.
- **4–5:** 네트워크-free 계약 테스트 전 분기 커버 + selftest + Linux/macOS CI + 로컬 미러. ← **현재 근접(단, TD-1 커밋 선결)**

### D4. 관측성 / 재현성
- **0–1:** 결과 재현 불가, provenance 없음.
- **2–3:** 로그는 있으나 구조화 안 됨.
- **4–5:** `NFC_STATUS` 기계 계약 + `.nfc-provenance.json`(version/commit)이 리포트로 흐름. ← **현재**

## 정량 지표

- Health Stack 게이트 통과율(8/8 목표) — [docs/QUALITY.md](../QUALITY.md).
- reducer `--selftest` 픽스처 수(현재 8), url_policy selftest 케이스 수.
- 진입 문서 줄 수(AGENTS.md ~100줄 상한).
- 강제점 수(코드로 강제되는 불변식 개수, 현재 4: 판정·SSRF·공급망·상태).
