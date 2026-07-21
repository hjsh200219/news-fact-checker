---
name: distribution-options
description: 배포 형태 제약 — Chrome 확장 직접 불가, 구독 OAuth 서드파티 금지(BYOK만 합법)
type: project
created: 2026-07-21
---

이 프로젝트는 실행 가능한 앱이 아니라 Claude Code 플러그인이다. SKILL.md는 Claude(LLM 에이전트)에게 주는 실행 계약이고, 주장 추출·웹검색·판정은 전부 Claude Code가 수행한다. Bash/Python 스크립트는 로컬 보조 도구일 뿐이다.

**Chrome 확장 직접 배포 불가.** 확장은 브라우저 JS 샌드박스라 Bash/Python 실행 불가, LLM 두뇌 내장 불가. 재개발 시 유일하게 현실적인 구조는 [확장(프론트, URL 전송만) + 백엔드 서버(파이프라인 오케스트레이션 + Claude API 호출)]다. 재사용 자산: `independence.py`(순수 결정론 로직, 서버 이식/TS 포팅 가능), 파이프라인 P0–P12 설계 문서(오케스트레이션 스펙). 확장 이점: content script가 현재 탭 본문을 직접 읽어 기사 본문 확보엔 insane-search 우회 불필요(단 교차검증용 근거 수집은 서버 몫).

**구독 계정(OAuth)으로 서드파티 사용 금지.** 2026년 초 Anthropic이 서드파티 앱에서 Free/Pro/Max 구독 OAuth 사용을 금지·차단. 구독은 공식 앱(웹·데스크톱·모바일·Claude Code)에서만 허용. 서드파티 앱 요청은 별도 선불 잔액(extra usage credits)에서 차감. 유일한 합법 경로 = BYOK(사용자가 Console에서 자기 API 키 발급·입력) 또는 개발자 API 키 서버 대납(비용 개발자 부담).

**Why:** "확장으로도 배포 가능?" "사용자 구독 계정 쓰게 할 수 있나?" 는 재현될 질문이고, 답은 코드가 아니라 아키텍처·정책에서 나오므로 리포지터리만 봐선 알 수 없다.
**How to apply:** 배포 형태 재검토·유료화 논의 시 이 제약을 전제로 시작. 관련: [[health-stack]].
