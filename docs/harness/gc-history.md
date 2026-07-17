# GC 이력 — news-fact-checker

`/sh:harness-gc` 실행 이력과 성숙도 추이를 기록한다. 실행마다 한 행 추가한다.
(이 표는 GC 실행 항목 전용 — `scripts/gc.sh` 자동 로그와 스키마를 섞지 않는다.)

## 실행 이력

| 날짜 | 커밋 | 종합 등급 | D1 | D2 | D3 | D4 | 주요 조치 | 상태 |
|------|------|:--------:|:--:|:--:|:--:|:--:|-----------|------|
| 2026-07-17 | (미커밋) | L3+ (3.7 → 커밋 시 4.0 L4) | 4.0 | 4.0 | 3.0 | 4.0 | 문서 신선도 100%, 아키텍처 준수 ~96%, correctness smell 0. 즉시수정 2건(레지스트리 setup.sh 추가, gc-history 초기화). | DONE_WITH_CONCERNS |

### 2026-07-17 (Run #1, baseline)
- 모드: full
- 문서 신선도: 100% (43/43 링크)
- 아키텍처 준수율: ~96% (11/11 in-scope PASS, low doc nit 1)
- 품질 등급: Python A- / Bash B+ / skills A- / tests B+ / docs A- (평균 A-/B+)
- 하네스 성숙도: L3+ (3.7점) — D1 4.0 / D2 4.0 / D3 3.0 / D4 4.0
- 약점 원칙: P7 GC자동화 (5 🔴), P6 test-gating (7), P8 observability (7), P4 convention (7)
- Knip strict: N/A (Node 소스 없음)
- 발견 이슈: 즉시수정 2건 적용, 수동/사용자 검토 2건(TD-1 커밋, P7 인프라)
- 반복 드리프트: 없음 (baseline)
- 예방 스크립트: 기존 `scripts/verify-docs.sh` 유지(27 checks, CI+run.sh 연결)
- 하네스 메타 검증: 해당 없음 (3회 미만)

## 성숙도 추이

```
Run #1 (2026-07-17, baseline): L3+ 3.7  [D1 4.0 · D2 4.0 · D3 3.0 · D4 4.0]
  · D3(3.0)의 병목은 TD-1(구현물 미커밋) — 커밋 시 D3→4.0, 종합 4.0 L4 확정.
  · P7(5)은 비-Node 리포 특성상 상한이 낮음(knip/husky N/A). CI+verify-docs가 대체.
```

## 참고

- 등급 정의·차원 가중치: [maturity-framework.md](maturity-framework.md)
- 채점 원칙: [principles.md](principles.md)
- 개선 액션: [fix-catalog.md](fix-catalog.md)
- 현재 부채: [../exec-plans/tech-debt-tracker.md](../exec-plans/tech-debt-tracker.md)
