from __future__ import annotations

import json
import unittest

from enrichment.model import wrap
from enrichment.sink_clickhouse import WHITELIST_COLUMNS, to_row

from .factory import make_log


class ToRowTest(unittest.TestCase):
    def _item(self, **kwargs):
        return wrap([make_log(**kwargs)])[0]

    def test_row_shape_matches_whitelist(self) -> None:
        row = to_row(self._item(user_id="alice@acme.test"))
        self.assertEqual(list(row), WHITELIST_COLUMNS)

    def test_envelope_mapping(self) -> None:
        it = self._item(user_id="alice@acme.test", ts=1_782_900_000.5)
        it.employee_verified = True
        it.internal_employee_id = "emp-001"
        it.company_id = "acme"
        row = to_row(it)
        self.assertEqual(row["event_id"], it.event.envelope.record_id)
        self.assertTrue(row["event_id"].startswith("idem-"))
        self.assertEqual(row["ts"], 1_782_900_000)  # epoch 초 정수
        self.assertEqual(row["tenant_id"], "acme")
        self.assertEqual(row["actor_id"], "alice@acme.test")
        self.assertEqual(row["internal_employee_id"], "emp-001")
        self.assertEqual(row["employee_verified"], 1)
        self.assertEqual(row["signal"], "log")
        self.assertEqual(row["product"], "claude_code")

    def test_unverified_defaults(self) -> None:
        # 검증 전(None)도 UInt8 컬럼에 안전하게 0 으로 적재된다.
        row = to_row(self._item(user_id=None, tenant_id=None))
        self.assertEqual(row["employee_verified"], 0)
        self.assertEqual(row["actor_id"], "")
        self.assertEqual(row["tenant_id"], "")
        self.assertEqual(row["internal_employee_id"], "")
        self.assertIsNone(row["company_id"])

    def test_raw_json_roundtrips_with_enum_values(self) -> None:
        row = to_row(self._item(user_id="alice@acme.test"))
        parsed = json.loads(row["raw_json"])
        self.assertEqual(parsed["type"], "user_prompt")  # str-Enum → 값 문자열
        self.assertEqual(parsed["envelope"]["_ingest"]["signal"], "log")
        self.assertEqual(
            parsed["envelope"]["identity"]["user_id"], "alice@acme.test"
        )

    def test_empty_record_id_falls_back_to_source_record_id(self) -> None:
        it = self._item(user_id="x", source_record_id="raw-42")
        it.event.envelope.record_id = ""
        self.assertEqual(to_row(it)["event_id"], "raw-42")

    def test_enrichment_json_serializes_annotations(self) -> None:
        it = self._item(user_id="x")
        it.annotations = {"org": {}, "github": {"pr": 1}}
        self.assertEqual(
            json.loads(to_row(it)["enrichment_json"]),
            {"org": {}, "github": {"pr": 1}},
        )


if __name__ == "__main__":
    unittest.main()
