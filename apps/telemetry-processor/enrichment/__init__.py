"""enrichment — normalize 이후, 저장 이전에 조직 정보를 부여하는 스테이지.

processor 컨테이너 안에서 인프로세스로 실행된다(MVP: 별도 enricher 컨테이너 없음).
P4(신원 해석) → P5(org as-of 매핑) → P6(provider 주석) 순으로 적용하며,
행은 절대 드롭하지 않는다. 적재는 sink_clickhouse 가 담당한다.
"""
