---
name: engine-pin-update
description: insane-search 엔진 commit-pin(SHA) 갱신 절차
type: reference
created: 2026-07-17
---

`resolve_engine.sh`의 `INSANE_SEARCH_COMMIT`은 full-length commit SHA로 고정된다(FR-5).
태그(`INSANE_SEARCH_REF`, 기본 `v0.8.2`)는 사람이 읽는 표시용일 뿐, 설치 게이트는 SHA 일치다.

현재 핀: `v0.8.2` → `2a578c469dc532969ed24fe698ff21d511653f97`

**갱신 절차** (엔진 버전을 올릴 때):
1. `git ls-remote https://github.com/fivetaku/insane-search refs/tags/<새태그> 'refs/tags/<새태그>^{}'`
   로 실제 커밋 SHA 확인 (annotated tag면 `^{}` deref 값을 사용).
2. `resolve_engine.sh`의 `INSANE_SEARCH_REF` 기본값과 `INSANE_SEARCH_COMMIT` 기본값을 함께 갱신.
3. 스모크 계약(FetchResult R6 필드 + `engine.__main__` import)은 `smoke_test()`가 검증하므로,
   새 버전이 계약을 깨면 loud fail한다.

**Why:** 이동 가능한 태그만 신뢰하면 태그 재지정/저장소 침해 시 같은 버전 문자열로 다른 코드를
clone·실행할 수 있다(공급망 위험). SHA 검증이 이를 막는다.
**How to apply:** 엔진 버전 bump PR에서 반드시 위 3단계를 따르고, 임의의 40-hex를 지어내지 말 것.
