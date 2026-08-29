"""ClickHouse 오류 분류 고정 — 4xx 까지 전부 BackendUnavailable(→503) 이다.

org provider 가 `OperationalError` 하나만 좁게 잡는 것과 정반대로, 여기서는
HTTPError 를 폭넓게 잡는다. **이 비대칭은 의도된 결정이다** — 4xx 를 영구 오류로
돌려보내면 collector otlphttp exporter 가 배치를 폐기하므로, 유실 없는 쪽으로
치우친다. 고치지 말고 그대로 고정한다.

실제 HTTP 왕복으로 검증한다. `execute(url=...)` 가 열려 있어 로컬 스텁 서버를
붙일 수 있다.
"""
from __future__ import annotations

import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from enrichment.errors import BackendUnavailable
from enrichment.sink_clickhouse import execute


def _make_handler(status: int, body: bytes):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 규약
            length = int(self.headers.get("Content-Length", 0))
            if length:
                self.rfile.read(length)
            self.send_response(status)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args) -> None:  # 테스트 출력 소음 억제
            pass

    return Handler


class _StubClickHouse:
    """응답 상태를 고정한 로컬 HTTP 스텁."""

    def __init__(self, status: int, body: bytes = b"stub error") -> None:
        self._server = HTTPServer(("127.0.0.1", 0), _make_handler(status, body))
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


def _closed_port() -> int:
    """즉시 닫아 확실히 연결이 거부되는 포트를 하나 얻는다."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ExecuteErrorClassificationTest(unittest.TestCase):
    def test_success_returns_response_body(self) -> None:
        """200 응답은 본문을 문자열로 돌려주는지 검증한다."""
        with _StubClickHouse(200, b"42\n") as url:
            self.assertEqual(execute("SELECT count()", url=url), "42\n")

    def test_every_http_error_becomes_backend_unavailable(self) -> None:
        """4xx·5xx 를 가리지 않고 전부 BackendUnavailable 로 분류하는지 검증한다.

        400(문법 오류)이나 401(인증 실패)은 재시도해도 낫지 않는 영구 오류지만,
        현행 코드는 이것도 503 으로 돌려보낸다. 유실보다 재시도를 택한 결정이다.
        """
        for status in (400, 401, 403, 404, 413, 500, 502, 503):
            with self.subTest(status=status):
                with _StubClickHouse(status, b"boom") as url:
                    with self.assertRaises(BackendUnavailable) as caught:
                        execute("INSERT INTO x FORMAT JSONEachRow", url=url)
                self.assertIn(f"clickhouse {status}", str(caught.exception))

    def test_error_detail_is_included(self) -> None:
        """CH 가 준 오류 본문을 메시지에 실어 원인 파악이 되게 하는지 검증한다."""
        with _StubClickHouse(400, b"DB::Exception: Syntax error") as url:
            with self.assertRaises(BackendUnavailable) as caught:
                execute("NONSENSE", url=url)

        self.assertIn("DB::Exception: Syntax error", str(caught.exception))

    def test_error_detail_is_truncated_to_500_chars(self) -> None:
        """긴 오류 본문은 500자로 잘라 로그가 넘치지 않게 하는지 검증한다."""
        with _StubClickHouse(400, b"x" * 5000) as url:
            with self.assertRaises(BackendUnavailable) as caught:
                execute("NONSENSE", url=url)

        self.assertEqual(str(caught.exception).count("x"), 500)

    def test_unreachable_host_becomes_backend_unavailable(self) -> None:
        """접속 자체가 안 되는 경우도 BackendUnavailable 이다."""
        url = f"http://127.0.0.1:{_closed_port()}"

        with self.assertRaises(BackendUnavailable) as caught:
            execute("SELECT 1", url=url)

        self.assertIn("clickhouse unreachable", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
