"""ClickHouse 적재 행 형태(`to_row`)와 배치 insert 의 현행 동작 고정.

`to_row()` 의 키 순서는 `WHITELIST_COLUMNS` 와 일치해야 한다 — JSONEachRow 라
순서가 곧바로 깨지지는 않지만, 두 목록이 어긋나면 화이트리스트가 실효를 잃는다.
"""
from __future__ import annotations

import json
import unittest

from enrichment.model import wrap
from enrichment.sink_clickhouse import TABLE, WHITELIST_COLUMNS, insert, to_row

from .factory import make_log


class ToRowTest(unittest.TestCase):
    def _item(self, **kwargs):
        return wrap([make_log(**kwargs)])[0]

    def test_row_shape_matches_whitelist(self) -> None:
        """행의 키 집합·순서가 화이트리스트 9컬럼과 같은지 검증한다."""
        row = to_row(self._item())

        self.assertEqual(list(row), WHITELIST_COLUMNS)
        self.assertEqual(len(WHITELIST_COLUMNS), 9)

    def test_envelope_mapping(self) -> None:
        """envelope 값이 어느 컬럼으로 가는지 고정한다."""
        item = self._item(
            member_id="alice@acme.test",
            installation_id="inst-0001",
            ts=1_782_900_000.5,
        )
        row = to_row(item)

        self.assertEqual(row["event_id"], item.event.envelope.record_id)
        self.assertTrue(row["event_id"].startswith("idem-"))
        self.assertEqual(row["ts"], 1_782_900_000)  # DateTime: epoch 초로 절삭
        self.assertEqual(row["tenant_id"], "acme")
        self.assertEqual(row["installation_id"], "inst-0001")
        self.assertEqual(row["signal"], "log")
        self.assertEqual(row["product"], "claude_code")
        self.assertEqual(row["team_ids_as_of"], [])

    def test_missing_values_become_empty_strings(self) -> None:
        """None 신원은 빈 문자열로 적재된다(컬럼이 non-nullable String 이라서)."""
        row = to_row(self._item(tenant_id=None, installation_id=None))

        self.assertEqual(row["tenant_id"], "")
        self.assertEqual(row["installation_id"], "")

    def test_member_id_is_not_promoted_to_a_column(self) -> None:
        """member_id 는 승격 컬럼이 아니다 — raw_json 안에만 남는다(ADR 0006)."""
        row = to_row(self._item(member_id="alice@acme.test"))

        self.assertNotIn("member_id", row)
        self.assertEqual(
            json.loads(row["raw_json"])["envelope"]["identity"]["member_id"],
            "alice@acme.test",
        )

    def test_team_ids_as_of_is_the_only_promoted_org_column(self) -> None:
        """org 승격 컬럼은 team_ids_as_of 하나뿐이다(ADR 0006)."""
        item = self._item()
        item.team_ids_as_of = ["team-a", "team-b"]

        self.assertEqual(to_row(item)["team_ids_as_of"], ["team-a", "team-b"])

    def test_raw_json_roundtrips_with_enum_values(self) -> None:
        """raw_json 이 envelope 중첩 원형을 보존하고 enum 은 값 문자열이 되는지 검증한다."""
        parsed = json.loads(to_row(self._item())["raw_json"])

        self.assertEqual(parsed["type"], "user_prompt")  # str-Enum → 값 문자열
        self.assertEqual(parsed["envelope"]["_ingest"]["signal"], "log")
        self.assertEqual(parsed["envelope"]["client"]["surface"], "cli")

    def test_empty_record_id_falls_back_to_source_record_id(self) -> None:
        """빈 record_id 는 source_record_id 로 방어한다.

        빈 키가 ReplacingMergeTree 의 전 행을 한 키로 합치는 사고를 막는 장치다.
        """
        item = self._item(source_record_id="raw-42")
        item.event.envelope.record_id = ""

        self.assertEqual(to_row(item)["event_id"], "raw-42")

    def test_enrichment_json_serializes_annotations_sorted(self) -> None:
        """provider 산출물은 enrichment_json 으로만, 키 정렬해 직렬화된다."""
        item = self._item()
        item.annotations = {"org": {"team_ids": []}, "github": {"pr": 1}}

        raw = to_row(item)["enrichment_json"]
        self.assertEqual(
            json.loads(raw), {"org": {"team_ids": []}, "github": {"pr": 1}}
        )
        # sort_keys=True 라 github 가 org 보다 앞에 온다.
        self.assertLess(raw.index("github"), raw.index("org"))


class _RecordingExecute:
    """execute() 호출 인자를 잡아두는 손수 만든 스텁."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def __call__(self, query, body=None, url=None, database=None):
        self.calls.append((query, body, url, database))
        return ""


class InsertTest(unittest.TestCase):
    def setUp(self) -> None:
        from enrichment import sink_clickhouse

        self.module = sink_clickhouse
        self.original = sink_clickhouse.execute
        self.execute = _RecordingExecute()
        sink_clickhouse.execute = self.execute

    def tearDown(self) -> None:
        self.module.execute = self.original

    def test_empty_batch_does_no_http_call(self) -> None:
        """빈 배치는 0 을 돌려주고 CH 를 아예 부르지 않는지 검증한다."""
        self.assertEqual(insert([]), 0)
        self.assertEqual(self.execute.calls, [])

    def test_sends_json_each_row_and_returns_count(self) -> None:
        """행마다 한 줄인 JSONEachRow 본문을 보내고 적재 행수를 돌려주는지 검증한다."""
        items = wrap([make_log(sequence=1), make_log(sequence=2)])

        self.assertEqual(insert(items), 2)

        query, body, _url, _database = self.execute.calls[0]
        self.assertEqual(query, f"INSERT INTO {TABLE} FORMAT JSONEachRow")
        lines = body.decode("utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(list(json.loads(lines[0])), WHITELIST_COLUMNS)

    def test_forwards_url_and_database_overrides(self) -> None:
        """url·database 재정의가 execute 까지 그대로 전달되는지 검증한다."""
        insert(
            wrap([make_log()]),
            url="http://localhost:8123",
            database="testdb",
        )

        _query, _body, url, database = self.execute.calls[0]
        self.assertEqual(url, "http://localhost:8123")
        self.assertEqual(database, "testdb")


if __name__ == "__main__":
    unittest.main()
