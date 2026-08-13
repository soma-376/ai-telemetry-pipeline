from __future__ import annotations

import json

from .context import IngestContext
from .envelope import build_envelope, build_ingest, finalize
from ..model import Client, Identity, MetricPoint, NormalizedMetric
from ..otlp import _map_str


def _seconds(value: str | int | None) -> float | None:
    return int(value) / 1e9 if value else None


def _number(rec: dict) -> int | float | None:
    if rec.get("asInt") is not None:
        return int(rec["asInt"])
    if rec.get("asDouble") is not None:
        return float(rec["asDouble"])
    return None


def _string_attrs(attrs: dict) -> dict[str, str]:
    return {
        key: (
            json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            if isinstance(value, (dict, list))
            else str(value)
        )
        for key, value in attrs.items()
    }


def build_metric_event(
    *,
    res_attrs: dict,
    rec: dict,
    attrs: dict,
    name: str,
    ctx: IngestContext,
    identity: Identity,
    client: Client,
    adapter: str,
    adapter_version: int,
) -> NormalizedMetric:
    meta = rec.get("_metric", {})
    # 메트릭은 session.id 를 datapoint 뿐 아니라 resource 레벨에 실을 수 있다 →
    # 로그 어댑터와 동일하게 둘 다 뒤진다.
    session_id = (
        _map_str(
            attrs,
            "envelope.session_id",
            "session.id",
            "conversation.id",
            "thread.id",
            res_attrs=res_attrs,
        )
        or "(unknown)"
    )
    envelope = build_envelope(
        client=client,
        identity=identity,
        session_id=session_id,
        ts=_seconds(rec.get("timeUnixNano")) or 0.0,
        ingest=build_ingest(
            ctx=ctx,
            adapter=adapter,
            adapter_version=adapter_version,
        ),
    )
    point = MetricPoint(
        name=name,
        value=_number(rec),
        unit=meta.get("unit"),
        description=meta.get("description"),
        metric_type=meta.get("type"),
        aggregation_temporality=meta.get("aggregationTemporality"),
        is_monotonic=meta.get("isMonotonic"),
        start_time=_seconds(rec.get("startTimeUnixNano")),
        count=int(rec["count"]) if rec.get("count") is not None else None,
        sum=float(rec["sum"]) if rec.get("sum") is not None else None,
        min=float(rec["min"]) if rec.get("min") is not None else None,
        max=float(rec["max"]) if rec.get("max") is not None else None,
        bucket_counts=[int(value) for value in rec.get("bucketCounts", [])],
        explicit_bounds=[
            float(value) for value in rec.get("explicitBounds", [])
        ],
        attrs=_string_attrs(attrs),
    )
    return finalize(NormalizedMetric(envelope=envelope, point=point))
