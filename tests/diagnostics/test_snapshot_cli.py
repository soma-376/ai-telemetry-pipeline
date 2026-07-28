from __future__ import annotations

import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from diagnostics.snapshot_cli import fetch_summary, write_summary


class _FixedDateTime:
    @classmethod
    def now(cls, tz=None) -> datetime:
        return datetime(2026, 7, 27, 12, 34, 56, tzinfo=tz or timezone.utc)


class SnapshotCliTest(unittest.TestCase):
    def test_fetch_summary_requires_json_array(self) -> None:
        """diagnostics endpoint의 최상위 값이 배열이 아니면 거부하는지 검증한다."""
        with patch(
            "diagnostics.snapshot_cli.urlopen",
            return_value=io.StringIO('{"issue":"unknown_event"}'),
        ):
            with self.assertRaises(ValueError):
                fetch_summary("http://localhost/diagnostics")

    def test_fetch_summary_returns_array(self) -> None:
        """정상적인 JSON 배열 응답을 변경 없이 반환하는지 검증한다."""
        document = [{"issue": "unknown_event"}]
        with patch(
            "diagnostics.snapshot_cli.urlopen",
            return_value=io.StringIO(json.dumps(document)),
        ):
            self.assertEqual(
                fetch_summary("http://localhost/diagnostics"),
                document,
            )

    def test_write_summary_is_atomic_and_avoids_name_collision(self) -> None:
        """임시 파일로 안전하게 저장하고 동일 시각의 파일명 충돌을 피하는지 검증한다."""
        document = [{"issue": "unknown_event", "count": 1}]

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with patch(
                "diagnostics.snapshot_cli.datetime",
                _FixedDateTime,
            ):
                first = write_summary(document, directory)
                second = write_summary(document, directory)

            self.assertEqual(
                first.name,
                "diagnostics-summary-20260727-123456-KST.json",
            )
            self.assertEqual(
                second.name,
                "diagnostics-summary-20260727-123456-KST-1.json",
            )
            self.assertEqual(
                json.loads(first.read_text(encoding="utf-8")),
                document,
            )
            self.assertFalse(first.with_suffix(".json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
