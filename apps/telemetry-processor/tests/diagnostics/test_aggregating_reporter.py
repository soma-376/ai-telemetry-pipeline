from __future__ import annotations

import threading
import unittest

from diagnostics import AggregatingReporter, DiagnosticEvent


def _event(**overrides) -> DiagnosticEvent:
    values = {
        "issue_type": "unknown_event",
        "source_record_id": "raw-test",
        "signal": "log",
        "adapter": "codex",
        "event_name": "codex.test",
        "message": "normalization_not_supported",
    }
    values.update(overrides)
    return DiagnosticEvent(**values)


class AggregatingReporterTest(unittest.TestCase):
    def test_groups_equal_events(self) -> None:
        """같은 adapter, issue, reason의 이벤트가 하나의 그룹으로 합산되는지 검증한다."""
        reporter = AggregatingReporter()

        reporter.report(_event(source_record_id="raw-1"))
        reporter.report(_event(source_record_id="raw-2"))

        self.assertEqual(
            reporter.snapshot(),
            [
                {
                    "adapter": "codex",
                    "issue": "unknown_event",
                    "reason": "normalization_not_supported",
                    "occurrence_count": 2,
                    "breakdown_by": "event_name",
                    "breakdown": {"codex.test": 2},
                }
            ],
        )

    def test_counts_each_unmapped_key_once_per_event(self) -> None:
        """한 이벤트의 중복 키는 한 번만 세고 키별 등장 횟수는 누적하는지 검증한다."""
        reporter = AggregatingReporter()

        reporter.report(
            _event(
                issue_type="unmapped_fields",
                event_name="codex.known",
                keys=("alpha", "beta", "alpha"),
                message="source_key_not_read",
            )
        )
        reporter.report(
            _event(
                issue_type="unmapped_fields",
                event_name="codex.known",
                keys=("alpha",),
                message="source_key_not_read",
            )
        )

        snapshot = reporter.snapshot()[0]
        self.assertEqual(snapshot["occurrence_count"], 2)
        self.assertEqual(
            snapshot["breakdown"],
            {"alpha": 2, "beta": 1},
        )

    def test_snapshot_does_not_reset_counts(self) -> None:
        """snapshot 조회가 현재 인메모리 집계를 초기화하지 않는지 검증한다."""
        reporter = AggregatingReporter()
        reporter.report(_event())

        first = reporter.snapshot()
        second = reporter.snapshot()

        self.assertEqual(first, second)

    def test_report_is_thread_safe(self) -> None:
        """여러 thread가 동시에 보고해도 occurrence와 breakdown count가 유실되지 않는지 검증한다."""
        reporter = AggregatingReporter()
        workers = 5
        reports_per_worker = 200

        def report_many() -> None:
            for _ in range(reports_per_worker):
                reporter.report(_event())

        threads = [
            threading.Thread(target=report_many)
            for _ in range(workers)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        snapshot = reporter.snapshot()[0]
        self.assertEqual(
            snapshot["occurrence_count"],
            workers * reports_per_worker,
        )
        self.assertEqual(
            snapshot["breakdown"],
            {"codex.test": workers * reports_per_worker},
        )


if __name__ == "__main__":
    unittest.main()
