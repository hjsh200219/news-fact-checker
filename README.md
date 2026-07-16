# news-fact-checker

뉴스 기사 **URL을 받아 팩트체크**하는 Claude Code 플러그인. 봇 차단(403/402/WAF) 사이트는
[insane-search](https://github.com/fivetaku/insane-search) 엔진으로 우회해 본문을 읽고, 웹검색과
**다중 독립 출처 교차검증**으로 핵심 주장을 검증해 **종합 판정(사실/거짓)** 을 한국어 리포트로 낸다.

> 보조 도구입니다(assistive, not authoritative). 중요한 판단은 원문과 1차 자료를 직접 확인하세요.

## 무엇을 하나

- **차단 우회**: WebFetch가 막히면 insane-search engine(`python3 -m engine`)으로 escalate.
  그래도 막히면 MCP Playwright로 내부 API를 찾아 재시도(R6). 통신사 공식 API/Jina 등은 engine이 담당.
- **종합 + 핵심 주장 판정**: 기사 전체 종합 판정 + 핵심 주장 3–5개 개별 검증(사실/대체로 사실/일부
  사실/오해 소지/거짓/검증 불가).
- **거짓 독립성 방지**: 연합뉴스 한 기사를 여러 매체가 재출고한 것은 `independence.py`로 **1개 유효
  출처로 붕괴**시킨 뒤 "독립 출처 ≥2"를 강제. 못 채우면 정직하게 `검증 불가`.
- **정직성**: 모든 근거에 URL, 모델지식 vs 웹검증 구분, 의견/예측은 검증 대상에서 분리, 한계 명시.

## 설치 (로컬)

```
# 1) 마켓플레이스 등록 (이 저장소 루트의 절대경로)
/plugin marketplace add /Users/hoshin/workspace/ProjectMarketing/news-fact-checker

# 2) 플러그인 설치
/plugin install news-fact-checker

# 3) 사용
/factcheck https://www.yna.co.kr/view/AKR20260625132900504
```
또는 그냥 자연어로: "이 기사 진짜야? <URL>", "fact-check this: <URL>".

## insane-search 자동 설치 (동의 기반)

첫 실행 시 스킬이 insane-search 엔진을 다음 순서로 찾는다:

1. 환경변수 `INSANE_SEARCH_HOME` (설정된 경우, 동일 스모크 테스트 통과 시)
2. 이미 설치된 플러그인 캐시 (`~/.claude/plugins/cache/*/insane-search/*`, semver 최고본)
3. 마켓플레이스 체크아웃
4. 벤더 클론 `~/.gptaku-setup/insane-search`
5. **미발견 시** — `AskUserQuestion`으로 **1회 동의**를 구한 뒤에만
   `git clone --branch v0.8.2`(핀 고정)로 설치. 동의 없이는 절대 clone+실행하지 않는다(공급망 안전).
6. 거부/설치 실패 → **축소 모드**(WebFetch/WebSearch만)로 계속하며 리포트에 도달성 저하를 명시.

각 후보는 채택 전 **계약 스모크 테스트**(엔진 FetchResult가 R6 필드를 갖는지, 네트워크 없이 검사)를
통과해야 한다. 버전 skew는 조용히 넘어가지 않고 loud fail한다.

설정:
- `INSANE_SEARCH_REF` — clone 시 고정 태그(기본 `v0.8.2`).
- `INSANE_SEARCH_HOME` — 엔진 경로 직접 지정.
- `NFC_CONSENT=yes` — clone 자동 승인(스킬이 동의를 받은 뒤 내부적으로 설정).

## 요구사항
- `python3` (엔진 어댑터 + independence.py). 없으면 축소 모드.
- `git` (clone 경로에만 필요; 이미 설치된 사본은 git 없이 동작).
- (선택) MCP Playwright 서버 — 강한 WAF의 R6 escalation에 사용. 미연결 시 정직하게 `접근불가(도구 미가용)`.
- insane-search 엔진이 첫 실 fetch 시 `curl_cffi>=0.15` 등 의존성을 자동 설치.

## 한계
- 통신사 재발행이 유일 원출처인 사안은 `검증 불가`가 될 수 있다(안전한 기본값).
- paywall/로그인 기사는 본문 일부만 취득될 수 있으며 리포트에 명시된다.
- 발행 시점 이후 상황 변동은 반영되지 않을 수 있다.
- 최신 사건은 웹 인덱싱 지연으로 확증 출처가 부족할 수 있다.

## 라이선스
MIT — [LICENSE](LICENSE).
