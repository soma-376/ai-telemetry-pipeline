from __future__ import annotations

import unittest
from datetime import date

from enrichment.enrich import enrich_with
from enrichment.enrich_org import make_memory_resolver
from enrichment.providers.registry import Registry
from enrichment.resolve_employee import resolver_via_memory

from .factory import make_log


class RegistryDiscoveryTest(unittest.TestCase):
    def test_org_is_first_and_stubs_are_discovered(self) -> None:
        names = Registry().names()
        self.assertEqual(names[0], "org")  # order=0 이 먼저
        self.assertLessEqual({"org", "github", "jira", "ai_analysis"}, set(names))


class EnrichWithFlowTest(unittest.TestCase):
    def test_full_flow_annotations_and_columns(self) -> None:
        events = [
            make_log(user_id="alice@acme.test", sequence=1),
            make_log(user_id="dave@nowhere.test", sequence=2),
        ]
        items = enrich_with(
            events,
            resolver_via_memory({"alice@acme.test": "emp-001"}),
            make_memory_resolver(
                {"emp-001": {"company_id": "acme", "name": "Alice"}},
                [{"employee_id": "emp-001", "code": "platform", "name": "Platform",
                  "valid_from": date(2020, 1, 1), "valid_to": None}],
            ),
        )
        self.assertEqual(len(items), 2)  # 행 수 불변

        names = set(Registry().names())
        for it in items:
            self.assertEqual(set(it.annotations), names)

        alice, dave = items
        self.assertTrue(alice.employee_verified)
        self.assertEqual(alice.internal_employee_id, "emp-001")
        self.assertEqual(alice.company_id, "acme")
        self.assertEqual(alice.department_code_as_of, "platform")
        self.assertFalse(dave.employee_verified)
        self.assertIsNone(dave.company_id)

    def test_empty_batch(self) -> None:
        self.assertEqual(
            enrich_with([], resolver_via_memory({}), make_memory_resolver({}, [])),
            [],
        )


if __name__ == "__main__":
    unittest.main()
