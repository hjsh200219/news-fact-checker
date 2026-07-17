# Layer Rules — 의존성 방향 & 아키텍처 강제

> 이 플러그인의 **허용 의존성 방향**과 그것을 지키는 이유를 규정한다.
> 레이어의 SSOT는 [ARCHITECTURE.md](../../ARCHITECTURE.md), 행동 계약의 SSOT는
> [SKILL.md](../../plugins/news-fact-checker/skills/news-fact-checker/SKILL.md).
> 이 문서는 **깨지면 안 되는 방향 규칙**을 한 곳에 모아 리뷰/에이전트가 대조할 수 있게 한다.
>
> 기술 스택: **Bash + Python3(stdlib only) + Markdown**. JS/ESLint/Node 툴링 없음 —
> "아키텍처 강제"는 [`scripts/verify-docs.sh`](../../scripts/verify-docs.sh)(문서↔리포 일치)와
> 이 문서 + 계약 테스트(`tests/`)로 수행한다. `eslint`/`import/no-restricted-paths`/`knip`은
> **N/A (no Node toolchain)**.

## 레이어 (위 → 아래, 아래로 갈수록 저수준)

```
L0 manifests (.claude-plugin/*.json)
      │
L1 command (commands/factcheck.md)  ──delegates──▶
L2 harness-contract docs (SKILL.md + references/)  ──prescribes──▶
L3 Python 계약 (independence.py · url_policy.py · parse_engine_status.py)
   + Bash 어댑터 (fetch_article.sh · resolve_engine.sh · setup.sh)  ──invokes(delegated)──▶
L4 external insane-search engine (리포 밖, 위임)
      ▲
L5 tests/ + tests/fake_engine (network-free)  ──drive──▶ L3
```

**허용 에지는 위 방향뿐이다. 역방향/우회 에지는 금지.** 즉 상위 레이어가 하위를 참조/구동하고,
하위는 상위를 알지 못한다. 문서(L2)가 스크립트(L3)를 기술하고, 스크립트가 엔진(L4)을 호출하며,
테스트(L5)가 fake 엔진으로 스크립트를 구동한다.

## 방향 규칙 (깨지면 안 됨)

각 규칙은 **무엇을 / 왜 / 어길 때 고치는 법**으로 적는다.

### R1. 프로덕션 Python은 순수 stdlib다 — 서드파티 import 금지
- **무엇:** `independence.py`, `url_policy.py`, `parse_engine_status.py`는 표준 라이브러리만
  import한다(`json`, `re`, `sys`, `ipaddress`, `socket`, `urllib`, `typing`, `__future__`).
  `pip install`이 필요한 어떤 패키지도 금지. (테스트/CI는 예외적으로 `mypy`만 추가.)
- **왜:** 이 플러그인은 런타임 의존성 0을 계약으로 삼는다. 설치 마찰과 공급망 표면을 없애고,
  네트워크 없는 CI를 stdlib만으로 재현 가능하게 유지한다. 유일한 무거운 의존성(브라우저·fetch
  스택)은 L4 엔진에 격리된다.
- **고치는 법:** 서드파티가 필요하면 (a) stdlib로 대체하거나, (b) 그 책임이 정말 L4 엔진의
  것인지 재검토한다. 계약 모듈에 새 의존성을 추가하지 않는다.

### R2. 스크립트는 사이트 도메인/셀렉터를 하드코딩하지 않는다 — 엔진에 위임
- **무엇:** L3 어댑터/계약은 특정 뉴스 사이트 도메인, CSS/XPath 셀렉터, 사이트별 fetch 분기를
  담지 않는다. 본문 취득·6-layer 검증·사이트 라우팅은 전부 L4(insane-search)의 책임이다.
- **왜:** 사이트별 로직이 어댑터에 새면 엔진과 검증·라우팅이 이중화되어 드리프트한다(경계 붕괴).
  thin 어댑터 원칙 — L3는 "어떻게 특정 사이트를 긁는가"를 몰라야 한다.
- **고치는 법:** 사이트별 처리가 필요하면 엔진 쪽 이슈로 올린다. 어댑터에는 도메인 리터럴이나
  셀렉터를 넣지 않는다. `grep`으로 어댑터에 하드코딩된 호스트/셀렉터가 없는지 확인.

### R3. 어댑터가 유일한 fetch 경로이며, 엔진 호출 전 url_policy 게이트를 통과해야 한다
- **무엇:** 모든 네트워크 취득은 `fetch_article.sh` 경유다. 즉흥 `curl`/수동 헤더/직접
  `python3 -m engine` 호출 금지. 어댑터는 요청 **전에** `url_policy.py`로 URL/SSRF 정책을
  강제하고(HTTP(S)만·userinfo/loopback/사설/link-local/메타데이터 거부), 통과한 목적지만 엔진에 넘긴다.
- **왜:** 단일 fetch 경계가 있어야 SSRF pre-flight를 우회 불가능하게 강제할 수 있다. 게이트가
  여러 곳에 흩어지면 하나만 빠뜨려도 방어가 무너진다. `unsafe_url`(exit 4)은 네트워크 요청
  없이 즉시 거부되어야 한다.
- **고치는 법:** 새 취득 경로가 필요하면 어댑터를 확장하되 반드시 `url_policy` pre-flight를 먼저
  통과시킨다. 게이트를 건너뛰거나 정책을 완화하지 않는다. (엔진 내부 redirect/DNS 재해석은
  thin 어댑터가 patch하지 않는 **위임된 한계** — ARCHITECTURE.md에 정직 고지.)

### R4. 테스트는 네트워크 없이 유지한다 — 실제 호스트 금지, fake_engine 사용
- **무엇:** `tests/`의 어떤 테스트도 실제 네트워크 호출을 하지 않는다. 엔진 상호작용은
  `tests/fake_engine`(엔진 더블)로 환경변수 시나리오를 구동한다. 실제 도메인/URL로 fetch 금지.
- **왜:** CI가 결정론적·오프라인·빠르게 재현되어야 한다. 실제 호스트에 의존하면 flaky해지고,
  외부 사이트 상태가 테스트 결과를 흔든다. 안전 게이트(reducer/url_policy) 회귀는 고정
  픽스처로만 잠글 수 있다.
- **고치는 법:** 새 실패 분기는 `fake_engine` 시나리오나 인메모리 픽스처로 재현한다. 실제
  네트워크가 등장하면 그 테스트를 fake_engine 기반으로 다시 쓴다.

### R5. 문서가 스크립트를 기술하고, 스크립트는 테스트에서 import하지 않는다
- **무엇:** 의존 방향은 docs(L2) → scripts(L3) → engine(L4), 그리고 tests(L5) → scripts(L3)
  뿐이다. 프로덕션 스크립트는 `tests/`나 `fake_engine`에서 무엇도 import하지 않는다. 또한
  Python 계약 3종은 **서로도 import하지 않는다**(각각 독립 순수함수 + CLI; 어댑터가 조립한다).
- **왜:** 테스트가 프로덕션을 구동해야지 그 반대가 되면 안 된다(순환·역방향 의존). 계약 모듈이
  서로를 끌어오면 독립 검증·독립 재사용이 깨진다. 방향이 한쪽이어야 리팩터 안전성이 유지된다.
- **고치는 법:** 공통 로직이 필요하면 테스트가 아니라 해당 계약 모듈 안으로 옮긴다. 계약끼리
  공유가 필요해 보이면 설계를 재검토한다(대개 어댑터에서 조립할 문제). `grep`으로 scripts가
  `tests`/`fake_engine`/서로를 import하지 않는지 확인.

## 강제 방법 (이 리포에서 실제로 동작하는 것)

| 규칙 | 강제 수단 |
|------|-----------|
| R1 stdlib-only | `python3 -m mypy`(CI) + 리뷰 + `grep -E '^(import|from)'` 점검 |
| R2 no hardcoded sites | 리뷰 + 어댑터 grep(도메인/셀렉터 리터럴 부재) |
| R3 어댑터 단일 fetch + url_policy 게이트 | `url_policy.py --selftest`, `tests/test_url_policy.py`, `tests/test_fetch_adapter.py` |
| R4 network-free tests | `bash plugins/news-fact-checker/tests/run.sh`(오프라인), fake_engine 더블 |
| R5 방향/무-cross-import | `grep` 점검 + 이 문서 + 리뷰 |
| 문서↔리포 일치 | [`scripts/verify-docs.sh`](../../scripts/verify-docs.sh) (CI + run.sh) |

관련 문서: [ARCHITECTURE.md](../../ARCHITECTURE.md) · [harness-setup.md](../harness/harness-setup.md) ·
[docs/SECURITY.md](../SECURITY.md) · [docs/QUALITY.md](../QUALITY.md)
