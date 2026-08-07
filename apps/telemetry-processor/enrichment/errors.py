"""enrichment 오류 분류.

RDS/ClickHouse 는 파이프라인 외부 인프라다 — 장애를 영구 오류(400)로 돌려보내면
collector otlphttp exporter 가 배치를 폐기한다. 재시도 가능(503)으로 분류해야
collector 가 재전송해 유실이 없다.
"""
from __future__ import annotations


class BackendUnavailable(RuntimeError):
    """RDS/ClickHouse 등 외부 백엔드 접근 불가(일시 장애) — HTTP 503 으로 응답."""
