# 0002. 토큰 합산은 billable 로만 한다

## Status

Accepted

## Context

벤더마다 토큰 카운터의 의미가 다르다. `reasoning`(Codex 의 reasoning_output, Gemini 의 thoughts)과
`tool`(Gemini)은 `output` 의 **부분집합일 수 있어**, 카운터를 전부 더하면 같은 토큰을 두 번 센다.
비용·사용량 대시보드가 이 합산 위에 서므로, 합산 규칙이 정해져 있지 않으면
벤더를 추가할 때마다 이중계산이 조용히 섞여 들어온다.

## Decision

- 토큰 합산은 **`Tokens.billable`(input + output + cache_read + cache_create)로만** 한다.
- `reasoning` · `tool` 등 벤더 부가 카운터는 참고 필드로만 두고 합산에 넣지 않는다.
- `total_reported` 는 벤더가 보고한 총량의 **검산 전용**이며 집계에 쓰지 않는다.

## Alternatives

### A. 벤더가 주는 카운터를 전부 합산한다
- 장점: 구현이 단순하다.
- 단점: 부분집합 관계인 카운터가 섞여 이중계산이 된다.
- 탈락 이유: 비용 지표의 신뢰를 깨뜨린다.

### B. 벤더별 합산 규칙을 따로 둔다
- 장점: 벤더 의미론에 정확히 맞출 수 있다.
- 단점: 벤더가 늘 때마다 규칙이 늘고, 규칙 간 비교 가능성이 사라진다.
- 탈락 이유: billable 한 정의로 벤더 간 비교 일관성을 유지하는 편이 낫다.

## Consequences/Tradeoffs

### Positive
- 벤더 간 사용량·비용 비교가 한 기준 위에서 성립한다.
- 이중계산이 스키마 수준에서 차단된다.

### Negative
- 벤더가 새 카운터를 추가하면 billable 정의(부분집합 여부)를 재검토해야 한다.
  - 완화책: diagnostics 의 `unmapped_fields` 집계로 새 카운터 유입을 감지한다.

## Follow-up

- `normalizer/pricing.py` 의 단가는 자리표시자다 — 실제 가격표로 갱신한다.
