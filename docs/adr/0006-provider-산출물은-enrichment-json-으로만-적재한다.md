# 0006. provider 산출물은 enrichment_json 으로만 적재한다

## Status

Accepted

## Context

enrichment provider(`enrichment/providers/`)는 파일 하나를 추가하면 registry 에 자동 등록된다(코어 수정 0).
provider 마다 산출물을 ClickHouse 공통 컬럼으로 승격하면, provider 를 추가할 때마다
`enriched_events` 스키마 변경이 따라와 자동 등록의 이점이 사라진다.

## Decision

- provider 산출물은 공통 컬럼으로 승격하지 않고 **`enrichment_json` 으로만** 적재한다.
- **예외는 org 하나다** — `team_ids_as_of` whitelist 컬럼을 채운다.
  조직 축 집계가 모든 대시보드의 기본 축이라 컬럼 접근 비용을 감수할 가치가 있다.
- 새 provider 의 산출물을 컬럼으로 승격하려면 이 ADR 을 개정한다.

## Alternatives

### A. provider 마다 전용 컬럼을 추가한다
- 장점: 쿼리 성능·타입 안정성.
- 단점: provider 추가가 스키마 변경을 동반해 "파일 하나 추가로 끝" 이라는 구조가 무너진다.
- 탈락 이유: GitHub/Jira/AI 분석 provider 가 아직 스텁인 시점에 컬럼을 늘릴 근거가 없다.

## Consequences/Tradeoffs

### Positive
- provider 추가 비용이 파일 하나로 유지된다.
- `enriched_events` 스키마가 안정된다.

### Negative
- JSON 경로 쿼리 비용을 감수한다. 자주 조회되는 산출물이 생기면 승격을 별도 결정해야 한다.

## Follow-up

- GitHub / Jira / AI 분석 provider 가 실구현될 때, 산출물 중 승격 후보가 있는지 재검토한다.
