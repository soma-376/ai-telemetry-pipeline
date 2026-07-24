#!/usr/bin/env python3
"""OTLP/HTTP JSON receiver for the normalize → enrich flow.

파일(*.jsonl) 경유 없이 collector 가 직접 밀어준다:
  collector otlphttp exporter(encoding: json) → 이 서버
    POST /v1/logs | /v1/traces | /v1/metrics
받은 OTLP JSON({resourceLogs|resourceSpans|resourceMetrics: ...})을 그대로
processor 에 넣는다 — 파서·정규화·enrichment는 각 패키지에서 담당한다.

현재 enrichment 뒤의 영속화 단계는 아직 연결하지 않는다.
"""

from __future__ import annotations

import argparse
import gzip
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from diagnostics import JsonlReporter
from processor import process

_SIGNAL_PATHS = {"/v1/logs", "/v1/traces", "/v1/metrics"}


class OTLPHandler(BaseHTTPRequestHandler):
    diagnostics: JsonlReporter

    def do_POST(self):
        if self.path not in _SIGNAL_PATHS:
            self.send_error(404, "unknown signal path")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        if self.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)

        try:
            # Generator stages are lazy, so consume the stream to execute the
            # normalize/enrichment flow.
            for _event in process(json.loads(body), diagnostics=self.diagnostics):
                pass
        except Exception as exc:  # noqa: BLE001 — 잘못된 배치는 400 으로 돌려보냄
            self.send_error(400, f"parse error: {exc}")
            return

        # OTLP 성공 응답(빈 ExportServiceResponse).
        payload = b"{}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # 접속 로그 소음 억제
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="OTLP/HTTP JSON ingestion receiver")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--diagnostics",
        type=Path,
        default=Path("data/diagnostics.jsonl"),
        help="진단 JSONL 경로",
    )
    args = parser.parse_args()

    OTLPHandler.diagnostics = JsonlReporter(args.diagnostics)
    server = ThreadingHTTPServer((args.host, args.port), OTLPHandler)
    print(
        f"OTLP receiver listening on {args.host}:{args.port}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        OTLPHandler.diagnostics.close()


if __name__ == "__main__":
    main()
