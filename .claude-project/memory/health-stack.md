---
name: health-stack
description: 검증 명령 모음 (순수 stdlib, mypy 별도 설치)
type: project
created: 2026-07-17
---

이 리포의 health stack (AGENTS.md와 동일 SSOT). 모두 네트워크 없이 실행된다:

```bash
bash scripts/verify-docs.sh                                    # 문서↔코드 정합 (27 checks)
bash -n plugins/news-fact-checker/scripts/*.sh                 # shell 문법
python3 -m py_compile plugins/news-fact-checker/scripts/*.py   # py 컴파일
python3 -m mypy --ignore-missing-imports \                     # 타입 (mypy 별도 설치 필요)
  plugins/news-fact-checker/scripts/{independence,url_policy,parse_engine_status}.py
bash plugins/news-fact-checker/tests/run.sh                    # 위 전부 + 71 계약 테스트
claude plugin validate . && claude plugin validate plugins/news-fact-checker
```

**Why:** 프로덕션 Python은 순수 stdlib(PRD 비목표: 새 런타임 의존성 금지)라 리포에 의존성 파일이
없다. `mypy`는 개발 도구로 별도 설치해야 하며 CI(`.github/workflows/ci.yml`)가 `pip install mypy`로
설치한다. `tests/run.sh` 하나가 로컬 게이트 전체를 미러한다.
**How to apply:** 코드 변경 후 `bash plugins/news-fact-checker/tests/run.sh` 한 번으로 대부분 확인.
새 실패 분기는 `tests/`에 네트워크 없는 계약 테스트로 추가(실제 호스트 금지, `fake_engine` 사용).
