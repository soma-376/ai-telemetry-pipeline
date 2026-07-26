"""Thread-safe in-memory diagnostics aggregation."""

from __future__ import annotations

import threading
from collections import Counter
from dataclasses import dataclass, field

from .model import DiagnosticEvent


@dataclass
class _Aggregate:
    occurrence_count: int = 0
    breakdown: Counter[str] = field(default_factory=Counter)


def _classification(event: DiagnosticEvent) -> tuple[str, str, tuple[str, ...]]:
    """Return the aggregation fields for every diagnostic issue type."""
    reason = event.message or "unclassified"
    if event.issue_type == "unknown_event":
        return reason, "event_name", (event.event_name or "(unnamed)",)
    if event.issue_type in ("mapping_miss", "invariant_failure"):
        return reason, "target_field", (
            event.target_field or "(unspecified)",
        )
    if event.issue_type == "unmapped_fields":
        return reason, "source_key", event.keys
    return reason, "issue", (event.issue_type,)


class AggregatingReporter:
    """Accumulate diagnostics and expose an explicit point-in-time snapshot."""

    def __init__(self) -> None:
        self._groups: dict[
            tuple[str | None, str, str, str], _Aggregate
        ] = {}
        self._lock = threading.Lock()

    def report(self, event: DiagnosticEvent) -> None:
        reason, breakdown_by, items = _classification(event)
        group_key = (
            event.adapter,
            event.issue_type,
            reason,
            breakdown_by,
        )
        with self._lock:
            aggregate = self._groups.setdefault(group_key, _Aggregate())
            aggregate.occurrence_count += 1
            # 한 이벤트에 같은 항목이 중복되어도 한 번만 센다.
            aggregate.breakdown.update(set(items))

    def snapshot(self) -> list[dict[str, object]]:
        """Return a consistent copy without stopping or resetting aggregation."""
        with self._lock:
            groups: list[dict[str, object]] = []
            ordered = sorted(
                self._groups.items(),
                key=lambda item: (
                    item[0][0] or "",
                    item[0][1],
                    item[0][2],
                    item[0][3],
                ),
            )
            for (adapter, issue, reason, breakdown_by), aggregate in ordered:
                groups.append(
                    {
                        "adapter": adapter,
                        "issue": issue,
                        "reason": reason,
                        "occurrence_count": aggregate.occurrence_count,
                        "breakdown_by": breakdown_by,
                        "breakdown": dict(sorted(aggregate.breakdown.items())),
                    }
                )
            return groups

    def close(self) -> None:
        """Reporter compatibility hook; snapshots are explicitly requested."""
        return None


# 기존 실행 코드의 import를 깨지 않기 위한 호환 별칭.
JsonlReporter = AggregatingReporter
