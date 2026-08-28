# 0004. call_id 를 조인 키로 쓴다

## Status

Accepted

## Context

툴 사용 신호(tool_call ↔ tool_decision)를 잇는 상관 키가 필요하다. 수락률 KPI 가 이 조인에 걸려 있다.
그런데 벤더 사정이 다르다 — Claude Code 만 `tool_use_id` 를 주고, Codex 는 대응 키가 없다.
키가 없다고 Codex 를 조인에서 제외하면 수락률 지표가 벤더 반쪽짜리가 된다.

## Decision

- **`call_id` 를 툴 신호의 조인 키로 쓴다.** Claude Code 는 `tool_use_id` 를 그대로 옮긴다.
- Codex 는 어댑터가 `call_id` 를 **합성**하고 `call_id_synthesized=True` 를 함께 남긴다.
  `_pair_call_ids()` 가 세션 내 "같은 도구명의 직전 미결 승인" 휴리스틱으로
  tool_decision ↔ tool_call 을 짝짓는다.

## Alternatives

### A. 벤더 키가 있는 경우에만 조인한다
- 장점: 오결합이 없다.
- 단점: Codex 수락률이 아예 산출되지 않는다.
- 탈락 이유: KPI 커버리지가 반쪽이 된다.

### B. 타임스탬프 근접만으로 짝짓는다
- 장점: 합성 키 관리가 없다.
- 단점: 병렬 도구 호출에서 쉽게 어긋나고, 어긋남을 식별할 표식도 없다.
- 탈락 이유: 휴리스틱을 쓰더라도 합성 여부(`call_id_synthesized`)가 데이터에 남아야 한다.

## Consequences/Tradeoffs

### Positive
- 벤더 불문 같은 키로 툴 신호가 이어져 수락률 KPI 가 성립한다.

### Negative
- 합성 키는 휴리스틱이라 오결합이 가능하다.
  - 완화책: `call_id_synthesized=True` 로 합성 건을 식별할 수 있어, 지표 소비자가 신뢰 구간을 가를 수 있다.

## Follow-up

- Codex 실데이터로 휴리스틱 오결합률을 확인한다 (diagnostics 집계 활용).
