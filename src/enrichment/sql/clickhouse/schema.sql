-- ClickHouse(mock) 적재 타깃 DDL. processor 가 기동 시 멱등 적용한다
-- (sink_clickhouse.ensure_schema — CREATE IF NOT EXISTS 라 재기동에 안전).
-- initdb 마운트를 쓰지 않는 이유: clickhouse 이미지의 init 임시 서버가 본 서버의
-- 포트 바인드와 레이스해 리스너 없이 뜨는 플레이크가 있다. 볼륨이 없으므로
-- down 후 up 이 곧 결정론적 리셋이다.
-- 수동 적용 폴백: clickhouse-client --multiquery < 이 파일.
-- 최소 공통 스키마: 얇은 공통 컬럼 + raw_json(Normalized 재직렬화) + enrichment_json.
-- provider별 필드를 공통 컬럼으로 승격 금지. 화이트리스트 컬럼만.
-- 엔진 ReplacingMergeTree ORDER BY event_id → 동일 event_id(=envelope.record_id,
-- 결정적 멱등키) 재적재는 멱등(FINAL 시 dedup).

CREATE TABLE IF NOT EXISTS enriched_events
(
    event_id               String,
    ts                     DateTime('UTC'),
    tenant_id              String,
    company_id             Nullable(String),
    actor_id               String,
    internal_employee_id   String,
    employee_verified      UInt8,
    signal                 String,
    product                String,
    department_code_as_of  String,
    department_name_as_of  String,
    employee_name          Nullable(String),
    raw_json               String,
    enrichment_json        String
)
ENGINE = ReplacingMergeTree
ORDER BY event_id;
