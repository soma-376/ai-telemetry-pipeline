#!/usr/bin/env python3
"""OTLP/HTTP JSON receiver for the normalize → enrich → store flow.

파일(*.jsonl) 경유 없이 collector 가 직접 밀어준다:
  collector otlphttp exporter(encoding: json) → 이 서버
    POST /v1/logs | /v1/traces | /v1/metrics
받은 OTLP JSON({resourceLogs|resourceSpans|resourceMetrics: ...})을 그대로
processor 에 넣는다 — 파서·정규화·enrichment는 각 패키지에서 담당한다.

enrichment 결과는 push 단위 배치로 ClickHouse(enriched_events)에 적재한다.
RDS/ClickHouse 장애는 503 으로 응답한다 — collector otlphttp exporter 가
재시도하므로 배치가 유실되지 않는다(400 은 영구 오류로 폐기됨).
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import time

from diagnostics import AggregatingReporter
from enrichment.errors import BackendUnavailable
from enrichment.sink_clickhouse import ensure_schema, insert
from processor import process

_SIGNAL_PATHS = {"/v1/logs", "/v1/traces", "/v1/metrics"}
_LOG_REQUEST_HEADERS = os.environ.get("LOG_REQUEST_HEADERS", "false").lower() == "true"
_SAFE_HEADERS = {
    "content-type",
    "content-encoding",
    "content-length",
    "user-agent",
    "x-request-id",
    "x-pulsemetry-token-id",
    "x-pulsemetry-tenant-id",
    "x-pulsemetry-installation-id",
    "x-pulsemetry-member-id",
}

# 프록시가 토큰을 검증해 붙인 신뢰 키(헤더)를 OTLP resource 속성으로 승격한다.
# normalizer 는 이미 이 속성명을 읽으므로(tenant.id / developer.installation_id)
# 여기서 심어주면 하류 변경 없이 신원이 정규화 이벤트까지 따라간다.
#   resource-attr 이름 → 운반 헤더 이름
_IDENTITY_STAMP = {
    "tenant.id": "x-pulsemetry-tenant-id",
    "developer.installation_id": "x-pulsemetry-installation-id",
}
# readers 가 traces 를 resourceSpans/resourceTraces 양쪽에서 읽으므로 둘 다 스탬프.
_RESOURCE_KEYS = (
    "resourceLogs",
    "resourceMetrics",
    "resourceSpans",
    "resourceTraces",
)


def _stamp_identity(doc: dict, headers) -> None:
    """프록시 검증 신원을 각 resource 의 속성에 upsert 한다.

    클라이언트가 동일 키를 자기신고했더라도 프록시 값으로 덮어써(신뢰 경계),
    정본 신뢰 키가 payload 자기신고값을 항상 이긴다. 값이 없는 헤더는 건너뛴다.
    """
    stamps = {attr: headers.get(hdr) for attr, hdr in _IDENTITY_STAMP.items()}
    stamps = {attr: value for attr, value in stamps.items() if value}
    if not stamps:
        return
    for resource_key in _RESOURCE_KEYS:
        for block in doc.get(resource_key, []):
            attrs = block.setdefault("resource", {}).setdefault("attributes", [])
            remaining = dict(stamps)
            for attr in attrs:
                key = attr.get("key")
                if key in remaining:
                    attr["value"] = {"stringValue": remaining.pop(key)}
            for key, value in remaining.items():
                attrs.append({"key": key, "value": {"stringValue": value}})


class OTLPHandler(BaseHTTPRequestHandler):
    diagnostics: AggregatingReporter

    def do_GET(self):
        if self.path != "/diagnostics":
            self.send_error(404, "unknown path")
            return
        payload = json.dumps(
            self.diagnostics.snapshot(),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if self.path not in _SIGNAL_PATHS:
            self.send_error(404, "unknown signal path")
            return

        if _LOG_REQUEST_HEADERS:
            headers = {
                name.lower(): value
                for name, value in self.headers.items()
                if name.lower() in _SAFE_HEADERS
            }
            print(json.dumps({
                "event": "collector_request",
                "path": self.path,
                "headers": headers,
            }, ensure_ascii=False, separators=(",", ":")), flush=True)

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        if self.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)

        try:
            doc = json.loads(body)
        except ValueError as exc:
            self.send_error(400, f"invalid json: {exc}")
            return

        # 프록시가 헤더로 넘긴 신뢰 신원을 resource 속성으로 승격(정규화 전에).
        _stamp_identity(doc, self.headers)

        try:
            items = process(doc, diagnostics=self.diagnostics)
            insert(items)
        except BackendUnavailable as exc:
            # 인프라 장애는 재시도 가능 — collector 가 5xx 를 재전송한다.
            self.send_error(503, f"backend unavailable: {exc}")
            return
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
    args = parser.parse_args()

    # 적재 테이블 멱등 보장(CREATE IF NOT EXISTS). compose 는 clickhouse healthy 를
    # 기다렸다 processor 를 띄우므로 보통 1회에 성공한다. 실패해도 서버는 띄운다 —
    # 이후 insert 가 503 을 돌려주고 collector 가 재시도한다.
    for attempt in range(5):
        try:
            ensure_schema()
            print("clickhouse schema ensured", flush=True)
            break
        except BackendUnavailable as exc:
            print(f"warning: clickhouse schema not ensured ({exc}); "
                  f"retry {attempt + 1}/5", flush=True)
            time.sleep(2)

    OTLPHandler.diagnostics = AggregatingReporter()
    server = ThreadingHTTPServer((args.host, args.port), OTLPHandler)
    print(
        f"OTLP receiver listening on {args.host}:{args.port}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
