from __future__ import annotations

import unittest

from diagnostics import TrackingAttrs


class TrackingAttrsTest(unittest.TestCase):
    def test_records_common_key_accesses(self) -> None:
        """get, 인덱싱, in 연산으로 조회한 키가 모두 접근 목록에 기록되는지 검증한다."""
        attrs = TrackingAttrs({"get": 1, "item": 2, "contains": 3})

        self.assertEqual(attrs.get("get"), 1)
        self.assertEqual(attrs["item"], 2)
        self.assertIn("contains", attrs)

        self.assertEqual(attrs.accessed, {"get", "item", "contains"})

    def test_records_successful_mapping(self) -> None:
        """매핑 성공 시 대상 필드와 변환 결과가 저장되고 실패 원인은 남지 않는지 검증한다."""
        attrs = TrackingAttrs({"input_tokens": "12"})

        value = attrs.map(
            "payload.tokens.input",
            lambda: int(attrs.get("input_tokens")),
        )

        self.assertEqual(value, 12)
        self.assertEqual(
            attrs.mapping_results,
            {"payload.tokens.input": 12},
        )
        self.assertEqual(attrs.mapping_reasons, {})

    def test_classifies_missing_null_and_conversion_failure(self) -> None:
        """키 누락, null 값, 변환 실패가 서로 다른 원인으로 분류되는지 검증한다."""
        attrs = TrackingAttrs(
            {
                "null_value": None,
                "invalid_value": "not-a-number",
            }
        )

        attrs.map("missing", lambda: attrs.get("absent"))
        attrs.map("null", lambda: attrs.get("null_value"))
        attrs.map(
            "invalid",
            lambda: (
                int(value)
                if (value := attrs.get("invalid_value")).isdigit()
                else None
            ),
        )

        self.assertEqual(
            attrs.mapping_reasons,
            {
                "missing": "source_key_missing",
                "null": "source_value_null",
                "invalid": "conversion_failed",
            },
        )

    def test_ignores_absent_optional_mapping(self) -> None:
        """선택 필드의 소스 키가 없으면 mapping miss로 기록하지 않는지 검증한다."""
        attrs = TrackingAttrs({})

        result = attrs.map(
            "payload.duration_ms",
            lambda: attrs.get("duration_ms"),
            required=False,
        )

        self.assertIsNone(result)
        self.assertEqual(attrs.mapping_results, {})
        self.assertEqual(attrs.mapping_reasons, {})

    def test_records_present_optional_null_and_conversion_failure(self) -> None:
        """선택 필드라도 키가 존재하면 null과 변환 실패를 진단하는지 검증한다."""
        attrs = TrackingAttrs(
            {
                "optional_null": None,
                "optional_invalid": "invalid",
            }
        )

        attrs.map(
            "optional.null",
            lambda: attrs.get("optional_null"),
            required=False,
        )
        attrs.map(
            "optional.invalid",
            lambda: (
                int(value)
                if (value := attrs.get("optional_invalid")).isdigit()
                else None
            ),
            required=False,
        )

        self.assertEqual(
            attrs.mapping_reasons,
            {
                "optional.null": "source_value_null",
                "optional.invalid": "conversion_failed",
            },
        )

    def test_restores_tracking_state_after_resolver_exception(self) -> None:
        """resolver 예외 이후에도 다음 매핑의 키 추적 상태가 오염되지 않는지 검증한다."""
        attrs = TrackingAttrs({"broken": "x", "healthy": "7"})

        with self.assertRaises(ValueError):
            attrs.map(
                "broken",
                lambda: int(attrs.get("broken")),
            )

        value = attrs.map(
            "healthy",
            lambda: int(attrs.get("healthy")),
        )

        self.assertEqual(value, 7)
        self.assertNotIn("broken", attrs.mapping_results)
        self.assertEqual(attrs.mapping_results["healthy"], 7)


if __name__ == "__main__":
    unittest.main()
