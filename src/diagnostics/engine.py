"""진단 이슈 탐지, 원인 분류, 필터링을 조정하는 중앙 엔진."""

from __future__ import annotations

from .model import DiagnosticEvent, Finding, Issue, Observation
from .reporter import DiagnosticReporter, NullReporter


_ROUTING_KEYS = frozenset({"event.name"})


class Diagnostics:
    """Coordinate issue detection, reason classification, and aggregation."""

    def __init__(self, reporter: DiagnosticReporter | None = None) -> None:
        self._reporter = reporter or NullReporter()

    def inspect(self, observation: Observation) -> None:
        """관찰 데이터에서 모든 이슈를 검사하고 발견 결과를 집계한다."""
        issues = self._detect_issues(observation)

        for issue in issues:
            reason = self._detect_reason(observation, issue)
            finding = Finding(
                issue=issue.issue_type,
                reason=reason,
                subject=issue.subject,
                keys=issue.keys,
            )

            if self._should_ignore(observation, finding):
                continue

            self._aggregate(observation, finding)

    def _detect_issues(self, observation: Observation) -> list[Issue]:
        """관찰 데이터에서 발생한 모든 이슈 유형과 대상을 판별한다."""
        if self._is_unknown_event(observation):
            return [
                Issue(
                    issue_type="unknown_event",
                    subject=observation.event_name,
                )
            ]

        issues: list[Issue] = []
        issues.extend(self._find_mapping_misses(observation))
        issues.extend(self._find_invariant_failures(observation))

        unmapped_keys = self._find_unmapped_fields(observation)
        if unmapped_keys:
            issues.append(
                Issue(
                    issue_type="unmapped_fields",
                    keys=unmapped_keys,
                )
            )

        return issues

    def _detect_reason(
        self, observation: Observation, issue: Issue
    ) -> str:
        """판별된 이슈가 발생한 구체적인 원인을 판별한다."""
        match issue.issue_type:
            case "unknown_event":
                return self._detect_unknown_event_reason(
                    observation,
                    issue,
                )
            case "mapping_miss":
                return self._detect_mapping_miss_reason(
                    observation,
                    issue,
                )
            case "invariant_failure":
                return self._detect_invariant_failure_reason(
                    observation,
                    issue,
                )
            case "unmapped_fields":
                return self._detect_unmapped_fields_reason(
                    observation,
                    issue,
                )
            case _:
                return "unclassified"

    def _is_unknown_event(self, observation: Observation) -> bool:
        """매칭된 어댑터가 이벤트를 정규화하지 못했는지 판별한다."""
        return observation.normalized_event is None

    def _find_mapping_misses(self, observation: Observation) -> list[Issue]:
        """매핑에 실패한 모든 대상 필드를 찾는다."""
        return [
            Issue(issue_type="mapping_miss", subject=target)
            for target, value in sorted(observation.mapping_results.items())
            if value is None
        ]

    def _find_invariant_failures(
        self, observation: Observation
    ) -> list[Issue]:
        """정규화된 값에서 발생한 모든 불변 조건 위반을 찾는다."""
        event = observation.normalized_event
        if event is None:
            return []

        failures: list[Issue] = []
        envelope = getattr(event, "envelope", None)
        if envelope is not None:
            timestamp = getattr(envelope, "timestamp", None)
            if not isinstance(timestamp, (int, float)) or timestamp <= 0:
                failures.append(
                    Issue(
                        issue_type="invariant_failure",
                        subject="envelope.timestamp",
                    )
                )

            session_id = getattr(envelope, "session_id", None)
            session_mapping_failed = (
                "envelope.session_id" in observation.mapping_results
                and observation.mapping_results["envelope.session_id"] is None
            )
            if (
                not session_mapping_failed
                and (not session_id or session_id == "(unknown)")
            ):
                failures.append(
                    Issue(
                        issue_type="invariant_failure",
                        subject="envelope.session_id",
                    )
                )

        event_type = getattr(getattr(event, "type", None), "value", None)
        payload = getattr(event, "payload", None)
        if event_type == "other" or (
            hasattr(event, "payload") and payload is None
        ):
            failures.append(
                Issue(
                    issue_type="invariant_failure",
                    subject="payload",
                )
            )

        tokens = getattr(payload, "tokens", None)
        reconciles = getattr(tokens, "reconciles", None)
        if callable(reconciles) and reconciles() is False:
            failures.append(
                Issue(
                    issue_type="invariant_failure",
                    subject="payload.tokens.total_reported",
                )
            )

        decision = getattr(getattr(payload, "decision", None), "value", None)
        if decision == "unknown":
            failures.append(
                Issue(
                    issue_type="invariant_failure",
                    subject="payload.decision",
                )
            )

        if hasattr(event, "span_id") and not getattr(event, "span_id", None):
            failures.append(
                Issue(
                    issue_type="invariant_failure",
                    subject="span_id",
                )
            )
        if hasattr(event, "trace_id") and not getattr(event, "trace_id", None):
            failures.append(
                Issue(
                    issue_type="invariant_failure",
                    subject="trace_id",
                )
            )

        point = getattr(event, "point", None)
        if point is not None and not getattr(point, "name", None):
            failures.append(
                Issue(
                    issue_type="invariant_failure",
                    subject="point.name",
                )
            )

        return failures

    def _find_unmapped_fields(self, observation: Observation) -> tuple[str, ...]:
        """소스에 존재하지만 정규화 과정에서 읽히지 않은 키를 찾는다."""
        unmapped_keys = (
            observation.source_values.keys()
            - observation.accessed_keys
            - _ROUTING_KEYS
        )
        return tuple(sorted(unmapped_keys))

    def _detect_unknown_event_reason(
        self, observation: Observation, issue: Issue
    ) -> str:
        """현재 어댑터가 이벤트를 정규화하지 못했음을 나타낸다."""
        return "normalization_not_supported"

    def _detect_mapping_miss_reason(
        self, observation: Observation, issue: Issue
    ) -> str:
        """대상 필드 매핑에 실패한 구체적인 원인을 판별한다."""
        return observation.mapping_reasons.get(
            issue.subject or "",
            "target_value_missing",
        )

    def _detect_invariant_failure_reason(
        self, observation: Observation, issue: Issue
    ) -> str:
        """불변 조건을 위반한 구체적인 원인을 판별한다."""
        return {
            "envelope.timestamp": "invalid_timestamp",
            "envelope.session_id": "unknown_session",
            "payload": "unsupported_event_payload",
            "payload.tokens.total_reported": "token_total_mismatch",
            "payload.decision": "unknown_decision",
            "span_id": "missing_span_id",
            "trace_id": "missing_trace_id",
            "point.name": "missing_metric_name",
        }.get(issue.subject or "", "invariant_violated")

    def _detect_unmapped_fields_reason(
        self, observation: Observation, issue: Issue
    ) -> str:
        """소스 키가 사용되지 않은 구체적인 원인을 판별한다."""
        return "source_key_not_read"

    def _should_ignore(
        self, observation: Observation, finding: Finding
    ) -> bool:
        """발견 결과가 진단에서 제외할 알려진 노이즈인지 판별한다."""
        return False

    def _aggregate(
        self, observation: Observation, finding: Finding
    ) -> None:
        """발견 결과를 인메모리 집계에 추가한다."""
        self._reporter.report(
            DiagnosticEvent(
                issue_type=finding.issue,
                adapter=observation.adapter,
                event_name=observation.event_name,
                target_field=finding.subject,
                keys=finding.keys,
                source_record_id=observation.source_record_id,
                signal=observation.signal,
                source_values=observation.source_values,
                message=finding.reason,
            )
        )
