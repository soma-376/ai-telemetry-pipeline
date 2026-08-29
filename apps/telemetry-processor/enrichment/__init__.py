"""enrichment — normalize 이후, 저장 이전에 파생 필드를 부여하는 스테이지.

processor 컨테이너 안에서 인프로세스로 실행된다(MVP: 별도 enricher 컨테이너 없음).
행은 절대 드롭하지 않는다. RDS(enrollment 스키마)를 조회하는 provider 는 org 하나다 —
order=0 으로 가장 먼저 실행돼 installation_id + ts as-of 조인으로 조직 맥락을 resolve
하는 자리다(현재는 팀 소속). 개별 integration provider(github·jira·ai_analysis —
현재 no-op 스텁)는 RDS 를 치지 않고, org 가 resolve 한 맥락을 입력 삼아 각자의
외부 API 를 부르는 자리다. provider 산출물은 annotations(enrichment_json)로만 적재하되,
org 만 예외로 조인 결과를 team_ids_as_of whitelist 컬럼에 승격한다(ADR 0006).
적재는 sink_clickhouse 가 담당한다.
"""
