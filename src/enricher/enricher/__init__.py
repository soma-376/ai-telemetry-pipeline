"""Enricher — Adaptor 형태 AI CLI 로그를 조직 컨텍스트로 보강해 ClickHouse에 적재한다.

이 패키지는 팀 repo(`../adaptor`)의 `normalizer`를 import 하지 않는다(결합 금지).
입력 계약(schema v4 wire 형태)은 `enricher.contract`에서 독립 재정의한다.

주의: 이 `__init__`은 무거운 선택 의존성(psycopg 등)을 import 하지 않는다.
DB 접근은 `enricher.rds` / `enricher.sink_clickhouse`에서 지연 import 한다.
"""

__version__ = "0.1.0"
