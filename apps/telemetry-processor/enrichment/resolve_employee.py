"""P4 — 신원 해석 + 재확인.

adapter 의 정본 신원(Identity.user_id — 온보딩 때 심은 developer.email 또는
developer.id)을 RDS employee 에 매칭해 internal_employee_id 를 해석하고,
존재 여부를 employee_verified 로 부여한다.

미등록이라도 **행을 드롭하지 않는다** — verified=false 를 달고 그대로 통과(파킹 원칙).

해석은 오라클(callable)로 주입받는다 → 로컬 단위 테스트는 dict 매핑으로,
E2E 는 RDS 로 백킹(resolver_via_rds).
"""
from __future__ import annotations

from typing import Callable, Optional

from .model import Enriched

ResolveFn = Callable[[str], Optional[str]]  # user_id → employee.id | None


def resolve_employees(items: list[Enriched], resolve: ResolveFn) -> list[Enriched]:
    """각 항목에 internal_employee_id/employee_verified 부여. in-place, 행 수 보존."""
    for it in items:
        uid = it.user_id
        emp = resolve(uid) if uid else None
        it.internal_employee_id = emp
        it.employee_verified = emp is not None
    return items


def resolver_via_rds(conn) -> ResolveFn:
    """RDS 연결로 해석 오라클 생성. user_id 가 developer.id 든 developer.email 이든
    매칭되도록 id/email → id 매핑을 1회 프리로드한다(배치 조회)."""
    mapping: dict[str, str] = {}
    with conn.cursor() as cur:
        cur.execute("SELECT id, email FROM employee")
        for eid, email in cur.fetchall():
            mapping[eid] = eid
            if email:
                mapping[email] = eid
    return mapping.get


def resolver_via_memory(mapping: dict[str, str]) -> ResolveFn:
    """단위 테스트용: {user_id: employee.id} 매핑을 그대로 오라클로 쓴다."""
    return mapping.get
