"""P5 — 회사/부서/사원 as-of 매핑 (DOMAIN §이력 규칙).

각 이벤트에 company/department/employee 를 부여한다. **부서는 이벤트 timestamp 기준(as-of)**
assignment 로 해석한다 — 현재 부서로 과거를 덮어쓰지 않는다(소급 변경 금지).
미등록 사원(RDS 부재)은 부서 `(unassigned)`, company/employee_name 은 None.

org 해석은 오라클(callable) 주입: `org_of(employee_id, on_date) -> Optional[dict]`.
  - None            : 미등록(사원이 RDS 에 없음)
  - dict            : {company_id, employee_name, department_code, department_name}
                      (department_* 는 해당 시점 배치 없으면 None)
로컬 순수 테스트는 `make_memory_resolver`, E2E 는 `make_rds_resolver` 로 백킹.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .model import Enriched

UNASSIGNED = "(unassigned)"

OrgOf = Callable[[str, date], Optional[Dict[str, Any]]]


def event_date(ts: Optional[float]) -> Optional[date]:
    """이벤트 timestamp(epoch, UTC) → 날짜. as-of 조인 키."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).date()


def enrich_org_item(item: Enriched, org_of: OrgOf) -> Enriched:
    """단일 항목에 company/department/employee 부여(as-of). in-place. (P6 org provider 재사용)

    조회 키는 P4(resolve_employee)가 해석해 둔 internal_employee_id — 미해석(None)이면
    미등록 경로로 처리한다.
    """
    emp = item.internal_employee_id
    on = event_date(item.timestamp)
    info = org_of(emp, on) if (emp is not None and on is not None) else None
    if info is None:
        item.company_id = None
        item.department_code_as_of = UNASSIGNED
        item.department_name_as_of = UNASSIGNED
        item.employee_name = None
    else:
        item.company_id = info.get("company_id")
        item.employee_name = info.get("employee_name")
        item.department_code_as_of = info.get("department_code") or UNASSIGNED
        item.department_name_as_of = info.get("department_name") or UNASSIGNED
    return item


def enrich_org(items: List[Enriched], org_of: OrgOf) -> List[Enriched]:
    """각 항목에 company/department/employee 부여(as-of). in-place, 행 수 보존."""
    for it in items:
        enrich_org_item(it, org_of)
    return items


def make_memory_resolver(employees: Dict[str, Dict[str, Any]],
                         assignments: List[Dict[str, Any]]) -> OrgOf:
    """in-memory as-of 해석기(RDS 반열림 구간 로직을 미러링).

    employees:   {emp_id: {"company_id":..., "name":...}}
    assignments: [{"employee_id","code","name","valid_from":date,"valid_to":date|None}, ...]
    """
    def org_of(emp: str, on: date) -> Optional[Dict[str, Any]]:
        e = employees.get(emp)
        if e is None:
            return None
        best = None
        for a in assignments:
            if a["employee_id"] != emp:
                continue
            if a["valid_from"] <= on and (a["valid_to"] is None or on < a["valid_to"]):
                if best is None or a["valid_from"] > best["valid_from"]:
                    best = a
        info = {
            "company_id": e["company_id"],
            "employee_name": e["name"],
            "department_code": best["code"] if best else None,
            "department_name": best["name"] if best else None,
        }
        return info

    return org_of


def make_rds_resolver(conn) -> OrgOf:
    """RDS 연결로 as-of 해석기 생성(E2E)."""
    from .rds import department_as_of, fetch_employee

    def org_of(emp: str, on: date) -> Optional[Dict[str, Any]]:
        e = fetch_employee(conn, emp)
        if e is None:
            return None
        d = department_as_of(conn, emp, on)
        return {
            "company_id": e["company_id"],
            "employee_name": e["name"],
            "department_code": d["code"] if d else None,
            "department_name": d["name"] if d else None,
        }

    return org_of
