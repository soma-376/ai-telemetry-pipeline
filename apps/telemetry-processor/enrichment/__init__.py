"""enrichment — normalize 이후, 저장 이전에 파생 필드를 부여하는 스테이지.

processor 컨테이너 안에서 인프로세스로 실행된다(MVP: 별도 enricher 컨테이너 없음).
행은 절대 드롭하지 않는다. provider 산출물은 annotations(enrichment_json)로만 적재하되,
org provider 만 예외로 RDS(installation_id + ts 기준 as-of 조인) 결과를
team_ids_as_of whitelist 컬럼에 승격한다(ADR 0006). 적재는 sink_clickhouse 가 담당한다.
"""
