-- ClickHouse(mock) 적재 타깃 DDL. processor 가 기동 시 멱등 적용한다
-- (sink_clickhouse.ensure_schema — CREATE IF NOT EXISTS 라 재기동에 안전).
-- initdb 마운트를 쓰지 않는 이유: clickhouse 이미지의 init 임시 서버가 본 서버의
-- 포트 바인드와 레이스해 리스너 없이 뜨는 플레이크가 있다. 볼륨이 없으므로
-- down 후 up 이 곧 결정론적 리셋이다.
-- 수동 적용 폴백: clickhouse-client --multiquery < 이 파일.
--
-- 슬림 공통 스키마: 검증 조인 키(installation_id) + 얇은 공통 컬럼 + raw_json(Normalized
-- 재직렬화) + enrichment_json(provider 주석). org 승격 컬럼은 team_ids_as_of 하나뿐이다
-- (ADR 0006) — org provider 가 ingest 시점에 enrollment 스키마를 as-of 조인해 채운다.
-- 엔진 ReplacingMergeTree ORDER BY event_id → 동일 event_id(=envelope.record_id,
-- 결정적 멱등키) 재적재는 멱등(FINAL 시 dedup).

CREATE TABLE IF NOT EXISTS enriched_events
(
    event_id         String,
    ts               DateTime('UTC'),
    tenant_id        String,
    installation_id  String,
    signal           String,
    product          String,
    team_ids_as_of   Array(String),
    raw_json         String,
    enrichment_json  String
)
ENGINE = ReplacingMergeTree
ORDER BY event_id;
