"""ClickHouse 적재 sink — HTTP 인터페이스(stdlib urllib)로 배치 insert.

무거운 클라이언트 도입 금지 → urllib 만 사용. raw_json 은 Normalized 이벤트의
재직렬화(event_to_json — envelope 중첩 원형 보존). provider별 필드는 공통 컬럼으로
승격하지 않고 enrichment_json 으로만 적재(최소 공통 스키마).

접속 URL/DB 는 호출 시점에 환경변수에서 읽는다(테스트/호스트 실행의 override 보장).
CH 오류는 전부 BackendUnavailable 로 분류한다(→ 리시버가 503, collector 재시도) —
4xx 를 영구 오류로 돌려보내면 collector 가 배치를 폐기하므로, 유실 없는 쪽으로 치우친다.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from normalizer.common.serialization import event_to_json

from .errors import BackendUnavailable
from .model import Enriched

# 파이프라인은 컴포즈 네트워크에서 서비스명 clickhouse:8123 로 접속.
# 호스트에서 직접 접속 시 ENRICHMENT_CH_URL 로 재정의(예: http://localhost:8123).
DEFAULT_CH_URL = "http://clickhouse:8123"
DEFAULT_DB = "default"
TABLE = "enriched_events"
DDL_PATH = Path(__file__).resolve().parent / "sql" / "clickhouse" / "schema.sql"

# 적재 컬럼 화이트리스트. 이 순서/집합을 초과하지 않는다.
WHITELIST_COLUMNS = [
    "event_id", "ts", "tenant_id", "company_id", "actor_id",
    "internal_employee_id", "employee_verified", "signal", "product",
    "department_code_as_of", "department_name_as_of", "employee_name",
    "raw_json", "enrichment_json",
]


def ch_url() -> str:
    return os.environ.get("ENRICHMENT_CH_URL", DEFAULT_CH_URL)


def ch_db() -> str:
    return os.environ.get("ENRICHMENT_CH_DB", DEFAULT_DB)


def execute(query: str, body: Optional[bytes] = None,
            url: Optional[str] = None, database: Optional[str] = None) -> str:
    """CH HTTP 로 쿼리 실행. SELECT/DDL 은 body=None, INSERT 는 body=행 바이트."""
    params = {"query": query, "database": database or ch_db()}
    full_url = (url or ch_url()) + "/?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full_url, data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise BackendUnavailable(f"clickhouse {exc.code}: {detail}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise BackendUnavailable(f"clickhouse unreachable: {exc}") from exc


def apply_ddl(ddl_sql: str, url: Optional[str] = None,
              database: Optional[str] = None) -> None:
    """세미콜론으로 구분된 DDL 을 문장별로 실행."""
    for stmt in ddl_sql.split(";"):
        s = stmt.strip()
        if not s:
            continue
        execute(s, url=url, database=database)


def ensure_schema(url: Optional[str] = None, database: Optional[str] = None) -> None:
    """멱등 DDL(CREATE IF NOT EXISTS) 적용 — processor 기동 시 호출."""
    apply_ddl(DDL_PATH.read_text(encoding="utf-8"), url=url, database=database)


def to_row(it: Enriched) -> Dict[str, Any]:
    """Enriched → 화이트리스트 컬럼 dict."""
    ts = it.timestamp
    return {
        "event_id": it.event_id,
        "ts": int(ts) if ts is not None else 0,            # DateTime: epoch 초
        "tenant_id": it.tenant_id or "",
        "company_id": it.company_id,                       # Nullable → None 허용
        "actor_id": it.user_id or "",
        "internal_employee_id": it.internal_employee_id or "",
        "employee_verified": 1 if it.employee_verified else 0,
        "signal": it.signal or "",
        "product": it.product or "",
        "department_code_as_of": it.department_code_as_of or "",
        "department_name_as_of": it.department_name_as_of or "",
        "employee_name": it.employee_name,                 # Nullable → None 허용
        "raw_json": event_to_json(it.event),
        "enrichment_json": json.dumps(it.annotations, sort_keys=True,
                                      separators=(",", ":"), ensure_ascii=False),
    }


def insert(items: List[Enriched], url: Optional[str] = None,
           database: Optional[str] = None) -> int:
    """배치 insert(JSONEachRow). 적재 행수 반환. 멱등: ORDER BY event_id(Replacing)."""
    if not items:
        return 0
    lines = [json.dumps(to_row(it), ensure_ascii=False) for it in items]
    body = ("\n".join(lines) + "\n").encode("utf-8")
    query = "INSERT INTO %s FORMAT JSONEachRow" % TABLE
    execute(query, body=body, url=url, database=database)
    return len(items)


def count(url: Optional[str] = None, database: Optional[str] = None) -> int:
    """dedup 후 행수(FINAL)."""
    out = execute("SELECT count() FROM %s FINAL" % TABLE, url=url, database=database)
    return int(out.strip())
