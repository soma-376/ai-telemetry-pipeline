from __future__ import annotations

import unittest

from enrichment.model import wrap
from enrichment.resolve_employee import resolve_employees, resolver_via_memory

from .factory import make_log


class ResolveEmployeesTest(unittest.TestCase):
    MAPPING = {
        # user_id 가 developer.id 형태든 developer.email 형태든 매칭된다.
        "emp-001": "emp-001",
        "alice@acme.test": "emp-001",
    }

    def test_resolves_by_id(self) -> None:
        items = wrap([make_log(user_id="emp-001")])
        resolve_employees(items, resolver_via_memory(self.MAPPING))
        self.assertEqual(items[0].internal_employee_id, "emp-001")
        self.assertTrue(items[0].employee_verified)

    def test_resolves_by_email(self) -> None:
        items = wrap([make_log(user_id="alice@acme.test")])
        resolve_employees(items, resolver_via_memory(self.MAPPING))
        self.assertEqual(items[0].internal_employee_id, "emp-001")
        self.assertTrue(items[0].employee_verified)

    def test_unregistered_kept_unverified(self) -> None:
        items = wrap([make_log(user_id="dave@nowhere.test")])
        resolve_employees(items, resolver_via_memory(self.MAPPING))
        self.assertIsNone(items[0].internal_employee_id)
        self.assertFalse(items[0].employee_verified)

    def test_missing_user_id_is_safe(self) -> None:
        items = wrap([make_log(user_id=None)])
        resolve_employees(items, resolver_via_memory(self.MAPPING))
        self.assertIsNone(items[0].internal_employee_id)
        self.assertFalse(items[0].employee_verified)

    def test_preserves_row_count(self) -> None:
        items = wrap([make_log(user_id=u, sequence=i)
                      for i, u in enumerate(["emp-001", None, "nope"])])
        out = resolve_employees(items, resolver_via_memory(self.MAPPING))
        self.assertEqual(len(out), 3)


if __name__ == "__main__":
    unittest.main()
