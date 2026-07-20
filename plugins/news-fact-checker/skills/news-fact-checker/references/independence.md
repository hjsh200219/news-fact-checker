# Evidence Reducer (independence.py)

## 왜
한국 뉴스는 **통신사 신디케이션**이 지배적이다. 연합뉴스/뉴스1/뉴시스 한 기사가 리드·제목을
바꿔 20개 매체에 재출고된다. 원시 "출처 수"로 세면 **거짓 독립성**이 생긴다 — 사실상 1개 출처를
20개로 착각. 그래서 "독립 출처 ≥2"를 강제하기 **전에** 신디케이션 클러스터를 1개 유효 출처로 붕괴한다.

또한 붕괴는 **stance별로** 수행한다. 지지 1개와 무관 1개가 서로 다른 클러스터라고 해서 원시
`effective_count=2`가 되어 단일 지지로 `사실`을 확정하는 오판을 막기 위함이다(H-1 수정).

## 사용
각 출처의 stance(supports/refutes/unrelated)를 **먼저** 판정한 뒤, 다음 형식의 JSON 리스트를
stdin으로 넣는다:
```bash
echo '[{"url":"...","stance":"supports","title":"...","body":"...",
        "byline":"...","dateline":"...","source_type":"outlet"}, ...]' \
  | python3 "${SKILL_DIR}/../../scripts/independence.py"
```
- `url`, `stance`는 **필수**. `stance` ∈ `supports | refutes | unrelated`.
- `title`/`body`/`byline`/`dateline`/`source_type`는 선택(문자열). 단 **`title`/`body` 중
  최소 하나는 비어있지 않아야** 한다 — 텍스트 없는 항목은 신디케이션 중복을 검사할 수 없고,
  독립 출처로 세면 게이트가 인플레이션되므로 `EMPTY_TEXT`(exit 2)로 거부한다.

## 출력 (schema_version 2)
```json
{
  "schema_version": 2,
  "supporting_clusters": [[0,2],[3]],
  "refuting_clusters": [],
  "supporting_effective_count": 2,
  "refuting_effective_count": 0,
  "unrelated_excluded": [4],
  "clusters": [
    {"stance":"supports","members":[0,2],"source_types":["primary","outlet"],
     "urls":["...","..."],
     "links":[{"a":0,"b":2,"reason":"wire_token","score":0.41,"shared_wire_tokens":["연합뉴스"]}]}
  ],
  "verdict_gate": {"can_be_true": true, "can_be_false": false}
}
```
- `supporting_effective_count` / `refuting_effective_count`: stance별 **유효(독립) 출처 수**.
- `verdict_gate.can_be_true` = `supporting_effective_count ≥ 2` **그리고** `refuting_effective_count == 0`.
- `verdict_gate.can_be_false` = `refuting_effective_count ≥ 2`.
- `clusters[].links`: 각 병합의 **사유(reason)·유사도(score)·공유 wire 토큰**을 남겨 감사 가능(FR-8).
- `unrelated_excluded`: 카운트에서 제외된 무관 출처의 입력 인덱스.

**확정 판정은 이 `verdict_gate`를 그대로 따른다.** 프롬프트 해석으로 게이트를 우회하지 않는다.

## 붕괴 규칙 (stance 그룹 내부, wire-token dominant)
두 출처를 링크(같은 클러스터)하는 조건 — 하나라도 참이면 링크:
1. **문자-trigram 유사도 ≥ 0.85** (`TAU`) — 순수 근접 중복(그대로 복붙). → reason `near_duplicate`
2. **공유 wire 토큰 있음 AND 유사도 ≥ 0.35** (`TAU_WIRE`) — 신디케이션(리드 rewrite로 유사도가
   순수 중복 임계값보다 낮아지므로 wire 토큰이 있으면 문턱을 낮춘다). **지배적 신호.** → reason `wire_token`
3. **byline 일치 AND dateline 일치 AND 유사도 ≥ 0.20** (`TAU_TOPIC`) — 같은 기자·데이트라인이라도
   **주제가 겹칠 때만** 링크. 같은 기자의 서로 다른 기사(물가 vs 태풍)는 유사도가 낮아 분리된다
   (M-3/AC-5 수정). → reason `byline_dateline`

연결 요소(union-find)가 클러스터. 각 stance 그룹에서 독립적으로 계산.

## 신호 설명
- **wire 토큰**: `연합뉴스`, `뉴스1`, `뉴시스`, `=연합`, `(서울=` 등 데이트라인-통신사 표기, `AP`,
  `Reuters`, `로이터`, `AFP`, `블룸버그` 등(스크립트 `WIRE_TOKENS`). 통신사 식별자·명시적 신디케이션
  표기로만 제한하며, 고유성이 낮은 일반 단어(`제공`)는 제거했다(FR-8).
- **문자 n-gram(k=3)**: 공백 제거 정규화 텍스트의 문자 트라이그램 Jaccard. 한국어 조사 결합·어순
  변화에 강함(단어 n-gram은 rewrite에 취약해 부적합).
- **주제 게이팅**: 모든 링크 규칙이 유사도 문턱을 갖는다 — 같은 통신사/같은 기자라도 주제가 다르면
  붕괴하지 않는다.

## stance는 입력이다
과거에는 stance가 스크립트 밖의 별도 단계였다. 이제 reducer가 stance를 **입력으로 받아**
`unrelated`를 카운트 전에 제거하고 supports/refutes를 각각 붕괴한다. stance 판정 자체(어느 출처가
주장을 지지/반박/무관하는지)는 여전히 모델의 몫이며, 근거 인플레이션을 막기 위해 키워드만 걸린
무관 출처는 `unrelated`로 표시한다.

## 입력·오류 계약 (FR-9)
- 최상위가 리스트가 아니면 → exit 2, `{"code":"TOP_NOT_LIST"}`.
- 항목이 object가 아니거나 `url`/`stance` 누락·오형, 선택 필드가 문자열이 아니면 → exit 2,
  `{"code": "...", "index": i, "field": "..."}` (짧은 오류 코드, **traceback 없음**).
- `title`/`body` 모두 비어있으면(공백 포함) → exit 2, `{"code":"EMPTY_TEXT","index":i}`.
- 잘못된 JSON → exit 2, `{"code":"BAD_JSON"}`. 내부 예외 → exit 1, 로컬 경로 비노출.

## 임계값 튜닝
`TAU`(0.85), `TAU_WIRE`(0.35), `TAU_TOPIC`(0.20), `CHAR_K`(3)은 스크립트 상단 상수.
`--selftest`가 9개 픽스처(신디케이션 붕괴 / 독립 지지 2건 / 같은-wire-다른-주제 비붕괴 /
같은-기자-다른-주제 비붕괴 / 지지+무관 / 단일 반박 / 독립 반박 2건 / transitive bridge 비병합 /
textless 항목 거부)로 회귀를 지킨다. 임계값 변경은 이 고정 벤치마크 결과와 함께 리뷰한다.
