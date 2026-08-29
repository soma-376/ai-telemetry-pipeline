"""OTLP 리시버의 HTTP 상태 매핑 고정 — 503/400 비대칭의 최종 관문.

  BackendUnavailable  → 503 (재시도 가능. collector 가 재전송한다)
  그 밖의 예외        → 400 (영구 오류. collector 가 배치를 폐기한다)
  JSON 파싱 실패      → 400

인프라 장애를 400 으로 돌려보내면 배치가 유실되고, 영구 오류를 503 으로
돌려보내면 재시도 큐가 막힌다. 이 분기가 그 경계다.

리시버를 실제로 띄우고 HTTP 로 두드린다 — 모듈 전역의 `process`/`insert` 를
바꿔 끼워 정규화·적재는 태우지 않는다.
"""
from __future__ import annotations

import gzip
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import otlp_receiver
from diagnostics import AggregatingReporter
from enrichment.errors import BackendUnavailable

_EMPTY_LOGS = {"resourceLogs": []}


class _Receiver:
    """실제 OTLPHandler 를 임시 포트에 띄운다."""

    def __init__(self) -> None:
        otlp_receiver.OTLPHandler.diagnostics = AggregatingReporter()
        self._server = ThreadingHTTPServer(
            ("127.0.0.1", 0), otlp_receiver.OTLPHandler
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )

    def __enter__(self) -> str:
        self._thread.start()
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def _post(base: str, path: str, body: bytes, headers: dict | None = None):
    """(status, body) 를 돌려준다. 4xx/5xx 도 예외 없이 값으로 받는다."""
    request = urllib.request.Request(
        base + path, data=body, method="POST", headers=headers or {}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


class StatusMappingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_process = otlp_receiver.process
        self._original_insert = otlp_receiver.insert
        self.processed: list[dict] = []
        self.inserted: list[list] = []

        def fake_process(doc, diagnostics=None):
            self.processed.append(doc)
            return []

        def fake_insert(items):
            self.inserted.append(items)
            return len(items)

        otlp_receiver.process = fake_process
        otlp_receiver.insert = fake_insert

    def tearDown(self) -> None:
        otlp_receiver.process = self._original_process
        otlp_receiver.insert = self._original_insert

    # ── 정상 경로 ────────────────────────────────────────────────────────────

    def test_success_returns_empty_otlp_response(self) -> None:
        """성공은 200 + 빈 ExportServiceResponse(`{}`) 인지 검증한다."""
        with _Receiver() as base:
            status, body = _post(base, "/v1/logs", json.dumps(_EMPTY_LOGS).encode())

        self.assertEqual(status, 200)
        self.assertEqual(body, b"{}")
        self.assertEqual(len(self.processed), 1)

    def test_all_three_signal_paths_are_accepted(self) -> None:
        """세 신호 경로 모두 받는지 검증한다."""
        with _Receiver() as base:
            for path in ("/v1/logs", "/v1/traces", "/v1/metrics"):
                with self.subTest(path=path):
                    status, _ = _post(
                        base, path, json.dumps(_EMPTY_LOGS).encode()
                    )
                    self.assertEqual(status, 200)

    def test_gzip_body_is_decompressed(self) -> None:
        """Content-Encoding: gzip 본문을 풀어서 처리하는지 검증한다."""
        payload = gzip.compress(json.dumps(_EMPTY_LOGS).encode())

        with _Receiver() as base:
            status, _ = _post(
                base, "/v1/logs", payload, {"Content-Encoding": "gzip"}
            )

        self.assertEqual(status, 200)
        self.assertEqual(self.processed[0], _EMPTY_LOGS)

    def test_unknown_path_is_404(self) -> None:
        """알 수 없는 경로는 404 이고 처리 자체를 하지 않는지 검증한다."""
        with _Receiver() as base:
            status, _ = _post(base, "/v1/unknown", b"{}")

        self.assertEqual(status, 404)
        self.assertEqual(self.processed, [])

    # ── 503: 재시도 가능 ─────────────────────────────────────────────────────

    def test_backend_unavailable_from_process_is_503(self) -> None:
        """enrichment 의 RDS 장애(BackendUnavailable)는 503 이다."""
        def failing(doc, diagnostics=None):
            raise BackendUnavailable("rds unreachable: connection refused")

        otlp_receiver.process = failing

        with _Receiver() as base:
            status, body = _post(
                base, "/v1/logs", json.dumps(_EMPTY_LOGS).encode()
            )

        self.assertEqual(status, 503)
        self.assertIn(b"backend unavailable", body)

    def test_backend_unavailable_from_insert_is_503(self) -> None:
        """ClickHouse 적재 장애도 같은 503 경로를 탄다."""
        def failing(items):
            raise BackendUnavailable("clickhouse 400: DB::Exception")

        otlp_receiver.insert = failing

        with _Receiver() as base:
            status, _ = _post(
                base, "/v1/logs", json.dumps(_EMPTY_LOGS).encode()
            )

        self.assertEqual(status, 503)

    # ── 400: 영구 오류 ───────────────────────────────────────────────────────

    def test_invalid_json_is_400(self) -> None:
        """JSON 파싱 실패는 400 이고 처리로 넘어가지 않는지 검증한다."""
        with _Receiver() as base:
            status, body = _post(base, "/v1/logs", b"{not json")

        self.assertEqual(status, 400)
        self.assertIn(b"invalid json", body)
        self.assertEqual(self.processed, [])

    def test_other_exception_is_400(self) -> None:
        """BackendUnavailable 이 아닌 예외는 전부 400 으로 떨어진다."""
        def failing(doc, diagnostics=None):
            raise ValueError("unexpected shape")

        otlp_receiver.process = failing

        with _Receiver() as base:
            status, body = _post(
                base, "/v1/logs", json.dumps(_EMPTY_LOGS).encode()
            )

        self.assertEqual(status, 400)
        self.assertIn(b"parse error", body)

    def test_backend_unavailable_subclass_still_maps_to_503(self) -> None:
        """BackendUnavailable 은 RuntimeError 를 상속하지만 503 분기가 먼저다."""
        class Narrower(BackendUnavailable):
            pass

        def failing(doc, diagnostics=None):
            raise Narrower("still infra")

        otlp_receiver.process = failing

        with _Receiver() as base:
            status, _ = _post(
                base, "/v1/logs", json.dumps(_EMPTY_LOGS).encode()
            )

        self.assertEqual(status, 503)


class IdentityStampTest(unittest.TestCase):
    """프록시가 헤더로 넘긴 신뢰 신원이 resource 속성을 이기는지 본다."""

    def _stamped(self, doc: dict, headers: dict) -> dict:
        otlp_receiver._stamp_identity(doc, headers)
        return doc

    def test_stamps_tenant_and_installation_into_every_resource_block(self) -> None:
        """헤더 신원을 resource 속성으로 승격하는지 검증한다."""
        doc = {"resourceLogs": [{"resource": {"attributes": []}}]}

        self._stamped(
            doc,
            {
                "x-pulsemetry-tenant-id": "ten-1",
                "x-pulsemetry-installation-id": "inst-1",
            },
        )

        attrs = doc["resourceLogs"][0]["resource"]["attributes"]
        self.assertEqual(
            {a["key"]: a["value"]["stringValue"] for a in attrs},
            {"tenant.id": "ten-1", "developer.installation_id": "inst-1"},
        )

    def test_proxy_value_overwrites_client_self_report(self) -> None:
        """클라이언트 자기신고 값을 프록시 값이 덮어쓰는지 검증한다(신뢰 경계)."""
        doc = {
            "resourceLogs": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "tenant.id", "value": {"stringValue": "spoofed"}}
                        ]
                    }
                }
            ]
        }

        self._stamped(doc, {"x-pulsemetry-tenant-id": "ten-real"})

        attrs = doc["resourceLogs"][0]["resource"]["attributes"]
        self.assertEqual(len(attrs), 1)
        self.assertEqual(attrs[0]["value"]["stringValue"], "ten-real")

    def test_missing_headers_leave_the_document_untouched(self) -> None:
        """헤더가 없으면 문서를 건드리지 않는지 검증한다."""
        doc = {"resourceLogs": [{"resource": {"attributes": []}}]}

        self._stamped(doc, {})

        self.assertEqual(doc["resourceLogs"][0]["resource"]["attributes"], [])

    def test_stamps_span_blocks_under_both_resource_keys(self) -> None:
        """resourceSpans 와 resourceTraces 둘 다 스탬프하는지 검증한다."""
        doc = {
            "resourceSpans": [{"resource": {"attributes": []}}],
            "resourceTraces": [{"resource": {"attributes": []}}],
        }

        self._stamped(doc, {"x-pulsemetry-tenant-id": "ten-1"})

        for key in ("resourceSpans", "resourceTraces"):
            with self.subTest(key=key):
                attrs = doc[key][0]["resource"]["attributes"]
                self.assertEqual(attrs[0]["key"], "tenant.id")


if __name__ == "__main__":
    unittest.main()
