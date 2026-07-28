"""P4 — 사원 존재 재확인 (PLAN §6 P4).

외부 인증은 이미 됐다고 가정하고(ASSUMPTIONS §3), 여기선 입력의 internal_employee_id 가
RDS employee 에 **존재하는지 재확인**만 한다. 결과를 `employee_verified: bool` 로 부여한다.

미등록(emp-404) 이라도 **행을 드롭하지 않는다** — verified=false 를 달고 그대로 통과(파킹 원칙).

존재 판정은 오라클(callable) 로 주입받는다 → 로컬 단위 테스트는 set 멤버십으로,
E2E 는 rds 로 백킹(`exists_via_rds`).
"""
from __future__ import annotations

from typing import Callable, List

from .model import Enriched

ExistsFn = Callable[[str], bool]


def verify_employees(items: List[Enriched], exists: ExistsFn) -> List[Enriched]:
    """각 항목에 employee_verified 부여. 입력 리스트를 in-place 갱신하고 그대로 반환(행 수 보존)."""
    for it in items:
        emp = it.record.internal_employee_id
        it.employee_verified = bool(emp is not None and exists(emp))
    return items


def exists_via_rds(conn) -> ExistsFn:
    """RDS 연결로 존재 오라클 생성. employee id 집합을 1회 프리로드(배치 조회)."""
    ids = set()
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM employee")
        for (eid,) in cur.fetchall():
            ids.add(eid)
    return lambda e: e in ids
