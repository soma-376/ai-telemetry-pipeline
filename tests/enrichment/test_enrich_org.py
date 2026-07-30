from __future__ import annotations

import unittest
from datetime import datetime, date, timezone

from enrichment.enrich_org import UNASSIGNED, enrich_org, make_memory_resolver
from enrichment.model import wrap

from .factory import make_log

# sql/rds/seed.sql 미러 — emp-002 는 2026-06-01 에 backend → platform 이동.
EMPLOYEES = {
    "emp-001": {"company_id": "acme", "name": "Alice"},
    "emp-002": {"company_id": "acme", "name": "Bob"},
    "emp-003": {"company_id": "globex", "name": "Carol"},
}
ASSIGNMENTS = [
    {"employee_id": "emp-001", "code": "platform", "name": "Platform",
     "valid_from": date(2020, 1, 1), "valid_to": None},
    {"employee_id": "emp-002", "code": "backend", "name": "Backend",
     "valid_from": date(2020, 1, 1), "valid_to": date(2026, 6, 1)},
    {"employee_id": "emp-002", "code": "platform", "name": "Platform",
     "valid_from": date(2026, 6, 1), "valid_to": None},
    {"employee_id": "emp-003", "code": "data", "name": "Data",
     "valid_from": date(2020, 1, 1), "valid_to": None},
]


def _ts(y: int, m: int, d: int, hour: int = 12) -> float:
    return datetime(y, m, d, hour, tzinfo=timezone.utc).timestamp()


def _item(employee_id: str | None, ts: float):
    it = wrap([make_log(user_id=employee_id, ts=ts)])[0]
    it.internal_employee_id = employee_id  # P4(resolve) 결과를 흉내 낸다.
    return it


class EnrichOrgAsOfTest(unittest.TestCase):
    def setUp(self) -> None:
        self.org_of = make_memory_resolver(EMPLOYEES, ASSIGNMENTS)

    def test_day_before_move_is_old_department(self) -> None:
        it = _item("emp-002", _ts(2026, 5, 31))
        enrich_org([it], self.org_of)
        self.assertEqual(it.department_code_as_of, "backend")
        self.assertEqual(it.company_id, "acme")
        self.assertEqual(it.employee_name, "Bob")

    def test_move_day_and_after_is_new_department(self) -> None:
        for ts in (_ts(2026, 6, 1, hour=0), _ts(2026, 6, 15)):
            it = _item("emp-002", ts)
            enrich_org([it], self.org_of)
            self.assertEqual(it.department_code_as_of, "platform")

    def test_unregistered_gets_unassigned(self) -> None:
        it = _item("emp-404", _ts(2026, 7, 1))
        enrich_org([it], self.org_of)
        self.assertIsNone(it.company_id)
        self.assertEqual(it.department_code_as_of, UNASSIGNED)
        self.assertEqual(it.department_name_as_of, UNASSIGNED)
        self.assertIsNone(it.employee_name)

    def test_registered_before_any_assignment(self) -> None:
        # ts=0.0(1970) — 등록 사원이지만 그 시점 배치가 없다 → 회사는 남고 부서만 미배치.
        it = _item("emp-001", 0.0)
        enrich_org([it], self.org_of)
        self.assertEqual(it.company_id, "acme")
        self.assertEqual(it.department_code_as_of, UNASSIGNED)

    def test_unresolved_employee_id_is_safe(self) -> None:
        # P4 가 해석하지 못한 항목(None)은 미등록 경로로 처리되고 행은 유지된다.
        items = [_item(None, _ts(2026, 7, 1))]
        out = enrich_org(items, self.org_of)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].department_code_as_of, UNASSIGNED)


if __name__ == "__main__":
    unittest.main()
