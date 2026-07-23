#!/usr/bin/env python3
"""OTLP 와이어 리더 — 툴 무관. 세 시그널을 공통 레코드 스트림으로 편다.

logs/metrics/traces 는 와이어 포맷이 다르지만(logRecords vs dataPoints vs spans),
여기서 (res_attrs, rec, attrs, name, signal_type) 5튜플로 통일해 내보낸다.
"어느 벤더 필드가 payload 로 가는가"(소스별 매핑)는 adapters/ 의 몫이고,
"OTLP 규격을 어떻게 읽는가"(이 파일)는 모든 툴이 공유한다.
"""

from __future__ import annotations

from typing import Iterator

from ..model import SignalType
from .attributes import _attr_value

Record = tuple  # (res_attrs, rec, attrs, name, signal_type)


def _attrs(obj: dict) -> dict:
    return {a["key"]: _attr_value(a["value"]) for a in obj.get("attributes", [])}


def read_logs(doc: dict) -> Iterator[Record]:
    for rl in doc.get("resourceLogs", []):
        res_attrs = _attrs(rl.get("resource", {}))
        for sl in rl.get("scopeLogs", []):
            for rec in sl.get("logRecords", []):
                name = (rec.get("body", {}) or {}).get("stringValue", "")
                yield res_attrs, rec, _attrs(rec), name, SignalType.LOG


def read_metrics(doc: dict) -> Iterator[Record]:
    for rm in doc.get("resourceMetrics", []):
        res_attrs = _attrs(rm.get("resource", {}))
        for sm in rm.get("scopeMetrics", []):
            for m in sm.get("metrics", []):
                name = m.get("name", "")
                for kind in ("sum", "gauge", "histogram", "exponentialHistogram"):
                    body = m.get(kind)
                    if not body:
                        continue
                    for dp in body.get("dataPoints", []):
                        rec = dict(dp)
                        rec["_metric"] = {
                            "unit": m.get("unit"),
                            "description": m.get("description"),
                            "type": kind,
                            "aggregationTemporality": body.get(
                                "aggregationTemporality"
                            ),
                            "isMonotonic": body.get("isMonotonic"),
                        }
                        yield res_attrs, rec, _attrs(dp), name, SignalType.METRIC


def read_traces(doc: dict) -> Iterator[Record]:
    # OTLP 는 resourceSpans, 일부 익스포터는 resourceTraces 로도 쓴다 — 둘 다 허용.
    for rs in doc.get("resourceSpans", []) + doc.get("resourceTraces", []):
        res_attrs = _attrs(rs.get("resource", {}))
        for ss in rs.get("scopeSpans", []):
            for span in ss.get("spans", []):
                name = span.get("name", "")
                yield res_attrs, span, _attrs(span), name, SignalType.SPAN


def read_all(doc: dict) -> Iterator[Record]:
    """한 OTLP 문서에서 존재하는 모든 시그널을 편다(파일이 섞여 있어도 안전)."""
    yield from read_logs(doc)
    yield from read_metrics(doc)
    yield from read_traces(doc)
