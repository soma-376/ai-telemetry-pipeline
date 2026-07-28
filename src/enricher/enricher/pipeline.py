"""E2E 오케스트레이션 (PLAN §6 P8).

로드 → 사원 재확인(P4) → org as-of 엔리치(P5, org provider) → provider 적용(P6)
→ ClickHouse 적재(P7). 각 단계는 행을 드롭하지 않는다(무드롭).

RDS 백킹: exists_via_rds + make_rds_resolver(psycopg). DSN/URL 은 env 로 재정의.
  ENRICHER_PG_DSN (기본 rds.DEFAULT_DSN), ENRICHER_CH_URL (기본 sink.DEFAULT_CH_URL)
"""
from __future__ import annotations

import os
import sys
from typing import Optional, Tuple

from . import rds
from . import sink_clickhouse as sink
from .enrich_org import make_rds_resolver
from .io_jsonl import load_file
from .model import wrap
from .providers.registry import Registry
from .verify_employee import exists_via_rds, verify_employees

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DDL_PATH = os.path.join(_REPO_ROOT, "clickhouse", "schema.sql")


def run(jsonl_path: str, pg_dsn: Optional[str] = None,
        ch_url: Optional[str] = None, reset: bool = False,
        ddl_path: str = _DDL_PATH) -> Tuple[int, int]:
    """파이프라인 1회 실행. (적재 행수, 파킹 라인수) 반환."""
    ch = ch_url or sink.DEFAULT_CH_URL

    # 1) 로드
    res = load_file(jsonl_path)
    items = wrap(res.records)

    # 2~3) RDS 백킹 재확인 + org as-of 엔리치 + provider 적용
    conn = rds.connect(pg_dsn)
    try:
        verify_employees(items, exists_via_rds(conn))
        Registry().apply(items, {"org_of": make_rds_resolver(conn)})
    finally:
        conn.close()

    # 4) ClickHouse 적재(멱등: ORDER BY event_id)
    if reset:
        with open(ddl_path, "r", encoding="utf-8") as f:
            sink.apply_ddl(f.read(), ch_url=ch)
    n = sink.insert(items, ch_url=ch)
    return n, res.parked_count


def main(argv) -> int:
    positional = [a for a in argv[1:] if not a.startswith("--")]
    flags = [a for a in argv[1:] if a.startswith("--")]
    if not positional:
        sys.stderr.write("usage: python -m enricher.pipeline [--reset] <jsonl_path>\n")
        return 2
    n, parked = run(positional[0], reset=("--reset" in flags))
    sys.stdout.write("pipeline inserted=%d parked=%d\n" % (n, parked))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
