"""ClickHouse 적재 sink — HTTP 인터페이스(stdlib urllib)로 배치 insert (PLAN §6 P7).

무거운 클라이언트 도입 금지 → urllib 만 사용(3.9/3.11 공통 stdlib).
raw_json 은 원본 이벤트 **verbatim**(Record.raw_line). provider별 필드는 공통 컬럼으로
승격하지 않고 enrichment_json 으로만 적재(최소 공통 스키마).
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from .model import Enriched

DEFAULT_CH_URL = os.environ.get("ENRICHER_CH_URL", "http://localhost:8123")
DEFAULT_DB = os.environ.get("ENRICHER_CH_DB", "default")
TABLE = "enriched_events"

# 적재 컬럼 화이트리스트(PLAN §6 P7). 이 순서/집합을 초과하지 않는다.
WHITELIST_COLUMNS = [
    "event_id", "ts", "tenant_id", "company_id", "actor_id",
    "internal_employee_id", "employee_verified", "signal", "product",
    "department_code_as_of", "department_name_as_of", "employee_name",
    "raw_json", "enrichment_json",
]


def execute(query: str, body: Optional[bytes] = None,
            ch_url: str = DEFAULT_CH_URL, database: str = DEFAULT_DB) -> str:
    """CH HTTP 로 쿼리 실행. SELECT/DDL 은 body=None, INSERT 는 body=행 바이트."""
    params = {"query": query, "database": database}
    url = ch_url + "/?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def apply_ddl(ddl_sql: str, ch_url: str = DEFAULT_CH_URL, database: str = DEFAULT_DB) -> None:
    """세미콜론으로 구분된 DDL 을 문장별로 실행(DROP; CREATE)."""
    for stmt in ddl_sql.split(";"):
        s = stmt.strip()
        if not s:
            continue
        execute(s, ch_url=ch_url, database=database)


def to_row(it: Enriched) -> Dict[str, Any]:
    """Enriched → 화이트리스트 컬럼 dict. raw_json 은 원본 verbatim."""
    rec = it.record
    ts = rec.timestamp
    return {
        "event_id": rec.event_id,
        "ts": int(ts) if ts is not None else 0,          # DateTime: epoch 초
        "tenant_id": rec.tenant_id or "",
        "company_id": it.company_id,                       # Nullable → None 허용
        "actor_id": rec.actor_id or "",
        "internal_employee_id": rec.internal_employee_id or "",
        "employee_verified": 1 if it.employee_verified else 0,
        "signal": rec.signal or "",
        "product": rec.product or "",
        "department_code_as_of": it.department_code_as_of or "",
        "department_name_as_of": it.department_name_as_of or "",
        "employee_name": it.employee_name,                 # Nullable → None 허용
        # 원본 verbatim. raw_line 이 없으면 계약 재직렬화로 폴백.
        "raw_json": rec.raw_line if rec.raw_line is not None
        else json.dumps(rec.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        "enrichment_json": json.dumps(it.annotations, sort_keys=True,
                                      separators=(",", ":"), ensure_ascii=False),
    }


def insert(items: List[Enriched], ch_url: str = DEFAULT_CH_URL,
           database: str = DEFAULT_DB) -> int:
    """배치 insert(JSONEachRow). 적재 행수 반환."""
    if not items:
        return 0
    lines = [json.dumps(to_row(it), ensure_ascii=False) for it in items]
    body = ("\n".join(lines) + "\n").encode("utf-8")
    query = "INSERT INTO %s FORMAT JSONEachRow" % TABLE
    execute(query, body=body, ch_url=ch_url, database=database)
    return len(items)


def count(ch_url: str = DEFAULT_CH_URL, database: str = DEFAULT_DB) -> int:
    """dedup 후 행수(FINAL)."""
    out = execute("SELECT count() FROM %s FINAL" % TABLE, ch_url=ch_url, database=database)
    return int(out.strip())
