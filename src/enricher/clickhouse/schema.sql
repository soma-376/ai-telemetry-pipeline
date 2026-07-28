-- ClickHouse 적재 타깃 (PLAN §6 P7).
-- 최소 공통 스키마(PLAN §8): 얇은 공통 컬럼 + raw_json(원본 verbatim) + enrichment_json.
-- provider별 필드를 공통 컬럼으로 승격 금지. 화이트리스트 컬럼만.
-- 엔진 ReplacingMergeTree ORDER BY event_id → 동일 event_id 재적재는 멱등(FINAL 시 dedup).
-- verify.sh/e2e.sh 가 매 실행 idempotent 리셋(DROP+CREATE)한다.

DROP TABLE IF EXISTS enriched_events;

CREATE TABLE enriched_events
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
