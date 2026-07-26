"""Central diagnostics engine skeleton.

Detection, classification, filtering, and aggregation will eventually be
coordinated by :class:`Diagnostics`.  The implementation is intentionally
empty for now so the public shape can be agreed on before behavior is moved
from the existing diagnostics modules.
"""

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

    def snapshot(self) -> list[dict[str, object]]:
        """현재까지 누적된 진단 집계 결과를 반환한다."""
        pass

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
        return []

    def _find_invariant_failures(
        self, observation: Observation
    ) -> list[Issue]:
        """정규화된 값에서 발생한 모든 불변 조건 위반을 찾는다."""
        return []

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
        pass

    def _detect_invariant_failure_reason(
        self, observation: Observation, issue: Issue
    ) -> str:
        """불변 조건을 위반한 구체적인 원인을 판별한다."""
        pass

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
                source_record_id=observation.source_record_id,
                signal=observation.signal,
                source_values=observation.source_values,
                message=finding.reason,
            )
        )
