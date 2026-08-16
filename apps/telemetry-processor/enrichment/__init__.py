"""enrichment — normalize 이후, 저장 이전에 provider 주석을 부여하는 스테이지.

processor 컨테이너 안에서 인프로세스로 실행된다(MVP: 별도 enricher 컨테이너 없음).
provider 주석(P6)만 적용하며 행은 절대 드롭하지 않는다. 사원/부서 등 org 해석은
ingest 에서 승격하지 않고 조회 계층(installation_id + ts 기준 as-of 조인)으로 옮겼다.
적재는 sink_clickhouse 가 담당한다.
"""
