from __future__ import annotations

from dataclasses import dataclass, field

from .common import Envelope


@dataclass
class MetricPoint:
    name: str
    value: int | float | None
    unit: str | None = None
    description: str | None = None
    metric_type: str | None = None
    aggregation_temporality: int | None = None
    is_monotonic: bool | None = None
    start_time: float | None = None
    count: int | None = None
    sum: float | None = None
    min: float | None = None
    max: float | None = None
    bucket_counts: list[int] = field(default_factory=list)
    explicit_bounds: list[float] = field(default_factory=list)
    attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class NormalizedMetric:
    envelope: Envelope
    point: MetricPoint
