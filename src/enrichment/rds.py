"""RDS(Postgres) 접속 + 조회 헬퍼.

psycopg 는 **지연 import** 한다 — 이 모듈을 import 해도 psycopg 부재 환경(로컬
단위 테스트)에서 크래시하지 않는다. 실제 접속(connect)이 호출될 때만 필요하다.

DSN 은 호출 시점에 환경변수에서 읽는다(테스트/호스트 실행의 override 보장).
as-of 부서 조회: 유효구간 [valid_from, valid_to) 반열림으로 이벤트 시점 부서를 해석한다.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any, Dict, Optional

# 파이프라인은 컴포즈 네트워크에서 서비스명 postgres:5432 로 접속.
# 호스트에서 직접 접속 시 ENRICHMENT_PG_DSN 으로 재정의(예: localhost:55432).
DEFAULT_DSN = "host=postgres port=5432 dbname=enrichment user=enrichment password=enrichment"


def dsn() -> str:
    return os.environ.get("ENRICHMENT_PG_DSN", DEFAULT_DSN)


def connect(dsn_override: Optional[str] = None):
    """psycopg 연결 반환. psycopg 는 여기서만 import(지연)."""
    import psycopg  # noqa: WPS433  (지연 import 의도적)

    return psycopg.connect(dsn_override or dsn())


def fetch_employee(conn, employee_id: str) -> Optional[Dict[str, Any]]:
    """employee 조회. 없으면 None."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, company_id, email, name FROM employee WHERE id = %s",
            (employee_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {"id": row[0], "company_id": row[1], "email": row[2], "name": row[3]}


def department_as_of(conn, employee_id: str, on_date: date) -> Optional[Dict[str, Any]]:
    """이벤트 시점(on_date)에 유효한 부서를 반환. 없으면 None.

    유효구간 [valid_from, valid_to) 반열림: valid_from <= on_date < valid_to(또는 valid_to NULL).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.id, d.code, d.name, d.company_id
            FROM employee_department_assignment a
            JOIN department d ON d.id = a.department_id
            WHERE a.employee_id = %s
              AND a.valid_from <= %s
              AND (a.valid_to IS NULL OR %s < a.valid_to)
            ORDER BY a.valid_from DESC
            LIMIT 1
            """,
            (employee_id, on_date, on_date),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {"department_id": row[0], "code": row[1], "name": row[2], "company_id": row[3]}


def fetch_company(conn, company_id: str) -> Optional[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM company WHERE id = %s", (company_id,))
        row = cur.fetchone()
    if not row:
        return None
    return {"id": row[0], "name": row[1]}
