"""claude_code 로그 정규화의 golden fixture 대조.

입력(`*.otlp.jsonl`)과 기대출력(`*.normalized.jsonl`)을 함께 커밋해 두고, 현행
`normalize()` 출력이 기대출력과 한 글자도 다르지 않은지 본다. 기대값을 손으로
적지 않고 실제 실행 결과를 구워 두는 방식이라, Kotlin 이식(PROJ-74)이 같은 파일
쌍을 읽어 그대로 대조할 수 있다.

기대출력을 다시 구우려면 `scripts/regen-golden.py` 를 쓴다. diff 가 나면 정규화
동작이 바뀐 것이므로, 갱신 전에 그 변화가 의도된 것인지 먼저 따진다.
"""
from __future__ import annotations

import json
import unittest
from dataclasses import asdict
from pathlib import Path

from normalizer import normalize

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "claude_code"


def _read_documents(name: str) -> list[dict]:
    """OTLP 입력 fixture 를 문서 리스트로 읽는다(한 줄 = 한 문서)."""
    path = _FIXTURES / name
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _read_golden(name: str) -> list[dict]:
    path = _FIXTURES / name
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _normalize_documents(documents: list[dict]) -> list[dict]:
    """golden 과 같은 형태(document_index/event_index/event)로 정규화 결과를 편다."""
    rows: list[dict] = []
    for document_index, document in enumerate(documents):
        # normalize() 는 제너레이터다 — list() 로 소비해야 pair_call_ids 가 끝난다.
        for event_index, event in enumerate(normalize(document)):
            rows.append(
                {
                    "document_index": document_index,
                    "event_index": event_index,
                    "event": asdict(event),
                }
            )
    return rows


class GoldenFixtureMixin:
    """입력·기대출력 한 쌍을 대조하는 공통 검사."""

    otlp_fixture: str
    golden_fixture: str

    def setUp(self) -> None:
        self.documents = _read_documents(self.otlp_fixture)
        self.golden = _read_golden(self.golden_fixture)

    def test_matches_golden_event_by_event(self) -> None:
        """정규화 결과가 기대출력과 이벤트 단위로 정확히 일치하는지 검증한다."""
        actual = _normalize_documents(self.documents)

        self.assertEqual(len(actual), len(self.golden))
        for index, (produced, expected) in enumerate(zip(actual, self.golden)):
            with self.subTest(index=index):
                self.assertEqual(produced, expected)

    def test_record_id_is_deterministic_across_runs(self) -> None:
        """같은 문서를 두 번 태워도 record_id 가 동일한지 검증한다."""
        first = [row["event"]["envelope"]["record_id"]
                 for row in _normalize_documents(self.documents)]
        second = [row["event"]["envelope"]["record_id"]
                  for row in _normalize_documents(self.documents)]

        self.assertEqual(first, second)
        self.assertTrue(all(key.startswith("idem-") for key in first))

    def test_source_record_id_is_deterministic_across_runs(self) -> None:
        """원본 추적 해시(raw-)도 재읽기에 흔들리지 않는지 검증한다."""
        first = [row["event"]["envelope"]["_ingest"]["source_record_id"]
                 for row in _normalize_documents(self.documents)]
        second = [row["event"]["envelope"]["_ingest"]["source_record_id"]
                  for row in _normalize_documents(self.documents)]

        self.assertEqual(first, second)
        self.assertTrue(all(key.startswith("raw-") for key in first))

    def test_every_event_carries_claude_code_envelope(self) -> None:
        """모든 이벤트가 claude_code 어댑터 버전과 log 신호를 달고 나오는지 검증한다."""
        for index, row in enumerate(self.golden):
            with self.subTest(index=index):
                envelope = row["event"]["envelope"]
                self.assertEqual(envelope["client"]["product"], "claude_code")
                self.assertEqual(envelope["client"]["surface"], "cli")
                self.assertEqual(envelope["schema_version"], 1)
                self.assertEqual(envelope["_ingest"]["signal"], "log")
                self.assertEqual(envelope["_ingest"]["adapter_version"], 3)


class RealCaptureGoldenTest(GoldenFixtureMixin, unittest.TestCase):
    """수집된 실 캡처(`data/claude_code/logs.jsonl` 사본) 대조."""

    otlp_fixture = "logs_real.otlp.jsonl"
    golden_fixture = "logs_real.normalized.jsonl"

    def test_capture_shape_is_pinned(self) -> None:
        """캡처가 48문서 × 3레코드 = 144 이벤트라는 사실을 고정한다."""
        self.assertEqual(len(self.documents), 48)
        self.assertEqual(len(self.golden), 144)

    def test_capture_contains_only_user_prompt(self) -> None:
        """이 캡처는 user_prompt 한 종류뿐이다 — 커버리지 한계를 테스트로 못박는다."""
        types = {row["event"]["type"] for row in self.golden}
        self.assertEqual(types, {"user_prompt"})

    def test_prompt_length_is_none_for_every_record(self) -> None:
        """캡처의 payload.prompt.length 는 어댑터가 읽는 키가 아니라 전부 None 이다.

        어댑터는 `payload.length` / `prompt_length` 를 읽는데 캡처는
        `payload.prompt.length` 를 싣는다. 현행 동작이므로 그대로 고정한다.
        """
        lengths = {row["event"]["payload"]["length"] for row in self.golden}
        self.assertEqual(lengths, {None})

    def test_144_records_collapse_into_6_record_ids(self) -> None:
        """캡처가 서로 다른 record_id 를 6개만 만든다는 현행 사실을 고정한다.

        같은 (tenant, product, session, sequence, ts, type, discriminator) 를
        가진 레코드가 반복되기 때문이다. ReplacingMergeTree 는 이들을 한 행으로
        합치므로 이 캡처를 그대로 적재하면 144건이 6건이 된다.
        """
        record_ids = {row["event"]["envelope"]["record_id"] for row in self.golden}
        self.assertEqual(len(record_ids), 6)


class SyntheticCoverageGoldenTest(GoldenFixtureMixin, unittest.TestCase):
    """실 캡처가 덮지 못하는 claude_code 로그 이벤트를 채우는 합성 입력 대조."""

    otlp_fixture = "logs_synthetic.otlp.jsonl"
    golden_fixture = "logs_synthetic.normalized.jsonl"

    def test_covers_every_normalized_log_kind(self) -> None:
        """docs/normalizer.md 의 claude_code 로그 9종이 내는 LogKind 전부를 덮는지 검증한다."""
        types = {row["event"]["type"] for row in self.golden}
        self.assertEqual(
            types,
            {
                "llm_call",       # api_request, api_error
                "llm_response",   # assistant_response, api_refusal
                "tool_call",      # tool_result
                "tool_decision",  # tool_decision
                "lifecycle",      # mcp_server_connection, compaction
                "user_prompt",    # user_prompt
            },
        )

    def test_every_record_id_is_distinct(self) -> None:
        """합성 입력은 레코드마다 다른 record_id 를 만든다(실 캡처와 대비)."""
        record_ids = [row["event"]["envelope"]["record_id"] for row in self.golden]
        self.assertEqual(len(record_ids), len(set(record_ids)))

    def test_unsupported_and_foreign_events_are_dropped(self) -> None:
        """어댑터가 모르는 claude_code 이벤트와 제품 밖 이벤트는 전달되지 않는지 검증한다.

        경계 문서(index 4)에는 레코드가 5건 들어 있지만 정규화되어 나오는 것은
        user_prompt 3건뿐이다 — `claude_code.some_future_event` 는 어댑터가
        None 을 반환해서, `some_other_tool.user_prompt` 는 어느 어댑터에도
        매칭되지 않아서 각각 버려진다.
        """
        boundary = [row for row in self.golden if row["document_index"] == 4]
        self.assertEqual(len(boundary), 3)
        self.assertTrue(all(row["event"]["type"] == "user_prompt" for row in boundary))

    def test_missing_session_falls_back_to_unknown(self) -> None:
        """session.id 가 없으면 "(unknown)" 으로 떨어지는 현행 동작을 고정한다."""
        sessions = {
            row["event"]["envelope"]["session_id"]
            for row in self.golden
            if row["document_index"] == 4
        }
        self.assertIn("(unknown)", sessions)

    def test_iso_timestamp_attribute_wins_over_time_unix_nano(self) -> None:
        """event.timestamp(ISO8601)가 있으면 timeUnixNano 대신 그 값을 쓰는지 검증한다."""
        matched = [
            row for row in self.golden
            if row["event"]["sequence"] == 53
        ]
        self.assertEqual(len(matched), 1)
        # 2026-03-04T05:06:07Z
        self.assertEqual(matched[0]["event"]["envelope"]["timestamp"], 1772600767.0)

    def test_missing_tenant_still_produces_a_record_id(self) -> None:
        """tenant.id 가 없어도 폴백 키로 record_id 가 만들어지는지 검증한다."""
        anonymous = [
            row for row in self.golden
            if row["event"]["envelope"]["identity"]["tenant_id"] is None
        ]
        self.assertEqual(len(anonymous), 1)
        self.assertTrue(
            anonymous[0]["event"]["envelope"]["record_id"].startswith("idem-")
        )


if __name__ == "__main__":
    unittest.main()
