from __future__ import annotations

import unittest
from types import SimpleNamespace

from diagnostics import DiagnosticEvent, Diagnostics, Observation


class RecordingReporter:
    def __init__(self) -> None:
        self.events: list[DiagnosticEvent] = []

    def report(self, event: DiagnosticEvent) -> None:
        self.events.append(event)


def _observation(**overrides) -> Observation:
    values = {
        "adapter": "codex",
        "signal": "log",
        "event_name": "codex.test",
        "source_record_id": "raw-test",
        "normalized_event": object(),
    }
    values.update(overrides)
    return Observation(**values)


class DiagnosticsEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.reporter = RecordingReporter()
        self.diagnostics = Diagnostics(self.reporter)

    def test_unknown_event_is_gatekeeper(self) -> None:
        """unknown 이벤트는 후속 mapping, invariant, unmapped 검사를 차단하는지 검증한다."""
        self.diagnostics.inspect(
            _observation(
                normalized_event=None,
                source_values={"unused": "value"},
                mapping_results={"payload.model": None},
                mapping_reasons={"payload.model": "source_key_missing"},
            )
        )

        self.assertEqual(len(self.reporter.events), 1)
        event = self.reporter.events[0]
        self.assertEqual(event.issue_type, "unknown_event")
        self.assertEqual(event.message, "normalization_not_supported")

    def test_reports_every_mapping_miss_with_its_reason(self) -> None:
        """실패한 모든 대상 필드가 각자의 mapping miss 원인과 함께 보고되는지 검증한다."""
        self.diagnostics.inspect(
            _observation(
                mapping_results={
                    "payload.model": None,
                    "payload.tokens.input": None,
                    "payload.tokens.output": 10,
                },
                mapping_reasons={
                    "payload.model": "source_key_missing",
                    "payload.tokens.input": "source_value_null",
                },
            )
        )

        events = {
            event.target_field: event.message
            for event in self.reporter.events
        }
        self.assertEqual(
            events,
            {
                "payload.model": "source_key_missing",
                "payload.tokens.input": "source_value_null",
            },
        )

    def test_reports_unmapped_keys_and_excludes_routing_key(self) -> None:
        """읽지 않은 소스 키를 찾되 라우팅용 event.name은 제외하는지 검증한다."""
        self.diagnostics.inspect(
            _observation(
                source_values={
                    "event.name": "codex.test",
                    "used": 1,
                    "unused": 2,
                },
                accessed_keys=frozenset({"used"}),
            )
        )

        self.assertEqual(len(self.reporter.events), 1)
        event = self.reporter.events[0]
        self.assertEqual(event.issue_type, "unmapped_fields")
        self.assertEqual(event.keys, ("unused",))

    def test_reports_invalid_timestamp_invariant(self) -> None:
        """0 이하의 timestamp가 invalid_timestamp invariant로 보고되는지 검증한다."""
        event = SimpleNamespace(
            envelope=SimpleNamespace(timestamp=0, session_id="session-1"),
            type=SimpleNamespace(value="llm_call"),
            payload=SimpleNamespace(tokens=None, decision=None),
        )

        self.diagnostics.inspect(_observation(normalized_event=event))

        self.assertEqual(len(self.reporter.events), 1)
        diagnostic = self.reporter.events[0]
        self.assertEqual(diagnostic.issue_type, "invariant_failure")
        self.assertEqual(diagnostic.target_field, "envelope.timestamp")
        self.assertEqual(diagnostic.message, "invalid_timestamp")

    def test_session_mapping_miss_suppresses_unknown_session_invariant(
        self,
    ) -> None:
        """세션 소스 누락은 mapping miss로만 기록해 동일 원인의 중복 진단을 막는지 검증한다."""
        event = SimpleNamespace(
            envelope=SimpleNamespace(
                timestamp=1,
                session_id="(unknown)",
            ),
            type=SimpleNamespace(value="llm_call"),
            payload=SimpleNamespace(tokens=None, decision=None),
        )

        self.diagnostics.inspect(
            _observation(
                normalized_event=event,
                mapping_results={"envelope.session_id": None},
                mapping_reasons={
                    "envelope.session_id": "source_key_missing",
                },
            )
        )

        self.assertEqual(len(self.reporter.events), 1)
        diagnostic = self.reporter.events[0]
        self.assertEqual(diagnostic.issue_type, "mapping_miss")
        self.assertEqual(diagnostic.target_field, "envelope.session_id")

    def test_mapped_unknown_session_reports_invariant(self) -> None:
        """세션 매핑은 성공했지만 값이 unknown이면 invariant로 보고되는지 검증한다."""
        event = SimpleNamespace(
            envelope=SimpleNamespace(
                timestamp=1,
                session_id="(unknown)",
            ),
            type=SimpleNamespace(value="llm_call"),
            payload=SimpleNamespace(tokens=None, decision=None),
        )

        self.diagnostics.inspect(
            _observation(
                normalized_event=event,
                mapping_results={
                    "envelope.session_id": "(unknown)",
                },
            )
        )

        self.assertEqual(len(self.reporter.events), 1)
        diagnostic = self.reporter.events[0]
        self.assertEqual(diagnostic.issue_type, "invariant_failure")
        self.assertEqual(diagnostic.target_field, "envelope.session_id")
        self.assertEqual(diagnostic.message, "unknown_session")

    def test_token_reconciliation_three_value_contract(self) -> None:
        """토큰 검산은 False만 실패이며 None과 True는 invariant를 만들지 않는지 검증한다."""
        cases = (
            (False, True),
            (None, False),
            (True, False),
        )

        for reconciliation, should_report in cases:
            with self.subTest(reconciliation=reconciliation):
                reporter = RecordingReporter()
                diagnostics = Diagnostics(reporter)
                tokens = SimpleNamespace(
                    reconciles=lambda value=reconciliation: value
                )
                event = SimpleNamespace(
                    envelope=SimpleNamespace(
                        timestamp=1,
                        session_id="session-1",
                    ),
                    type=SimpleNamespace(value="llm_call"),
                    payload=SimpleNamespace(
                        tokens=tokens,
                        decision=None,
                    ),
                )

                diagnostics.inspect(
                    _observation(normalized_event=event)
                )

                token_failures = [
                    diagnostic
                    for diagnostic in reporter.events
                    if diagnostic.target_field
                    == "payload.tokens.total_reported"
                ]
                self.assertEqual(
                    len(token_failures),
                    1 if should_report else 0,
                )

    def test_clean_observation_reports_no_findings(self) -> None:
        """정상적인 관찰 데이터에서는 어떤 진단 결과도 생성되지 않는지 검증한다."""
        event = SimpleNamespace(
            envelope=SimpleNamespace(
                timestamp=1,
                session_id="session-1",
            ),
            type=SimpleNamespace(value="llm_call"),
            payload=SimpleNamespace(tokens=None, decision=None),
        )

        self.diagnostics.inspect(_observation(normalized_event=event))

        self.assertEqual(self.reporter.events, [])

    def test_reports_unsupported_event_payload(self) -> None:
        """지원되지 않는 event type이 payload invariant로 보고되는지 검증한다."""
        event = SimpleNamespace(
            envelope=SimpleNamespace(
                timestamp=1,
                session_id="session-1",
            ),
            type=SimpleNamespace(value="other"),
            payload=object(),
        )

        self.diagnostics.inspect(_observation(normalized_event=event))

        self.assertEqual(len(self.reporter.events), 1)
        diagnostic = self.reporter.events[0]
        self.assertEqual(diagnostic.target_field, "payload")
        self.assertEqual(
            diagnostic.message,
            "unsupported_event_payload",
        )

    def test_reports_unknown_decision(self) -> None:
        """매핑된 decision 값이 unknown이면 unknown_decision으로 보고되는지 검증한다."""
        event = SimpleNamespace(
            envelope=SimpleNamespace(
                timestamp=1,
                session_id="session-1",
            ),
            type=SimpleNamespace(value="tool_decision"),
            payload=SimpleNamespace(
                tokens=None,
                decision=SimpleNamespace(value="unknown"),
            ),
        )

        self.diagnostics.inspect(_observation(normalized_event=event))

        self.assertEqual(len(self.reporter.events), 1)
        diagnostic = self.reporter.events[0]
        self.assertEqual(diagnostic.target_field, "payload.decision")
        self.assertEqual(diagnostic.message, "unknown_decision")

    def test_missing_decision_reports_mapping_and_invariant(self) -> None:
        """현재 정책상 decision 누락과 UNKNOWN 결과가 각각 별도 이슈로 기록되는지 검증한다."""
        event = SimpleNamespace(
            envelope=SimpleNamespace(
                timestamp=1,
                session_id="session-1",
            ),
            type=SimpleNamespace(value="tool_decision"),
            payload=SimpleNamespace(
                tokens=None,
                decision=SimpleNamespace(value="unknown"),
            ),
        )

        self.diagnostics.inspect(
            _observation(
                normalized_event=event,
                mapping_results={"payload.decision": None},
                mapping_reasons={
                    "payload.decision": "source_key_missing",
                },
            )
        )

        findings = {
            (diagnostic.issue_type, diagnostic.message)
            for diagnostic in self.reporter.events
        }
        self.assertEqual(
            findings,
            {
                ("mapping_miss", "source_key_missing"),
                ("invariant_failure", "unknown_decision"),
            },
        )

    def test_reports_missing_span_identifiers(self) -> None:
        """span_id와 trace_id 누락이 각각 독립적인 invariant로 보고되는지 검증한다."""
        event = SimpleNamespace(
            envelope=SimpleNamespace(
                timestamp=1,
                session_id="session-1",
            ),
            type=SimpleNamespace(value="turn"),
            payload=object(),
            span_id=None,
            trace_id=None,
        )

        self.diagnostics.inspect(_observation(normalized_event=event))

        targets = {
            diagnostic.target_field
            for diagnostic in self.reporter.events
        }
        self.assertEqual(targets, {"span_id", "trace_id"})

    def test_reports_missing_metric_name(self) -> None:
        """metric point 이름 누락이 missing_metric_name으로 보고되는지 검증한다."""
        event = SimpleNamespace(
            envelope=SimpleNamespace(
                timestamp=1,
                session_id="session-1",
            ),
            point=SimpleNamespace(name=""),
        )

        self.diagnostics.inspect(_observation(normalized_event=event))

        self.assertEqual(len(self.reporter.events), 1)
        diagnostic = self.reporter.events[0]
        self.assertEqual(diagnostic.target_field, "point.name")
        self.assertEqual(diagnostic.message, "missing_metric_name")


if __name__ == "__main__":
    unittest.main()
