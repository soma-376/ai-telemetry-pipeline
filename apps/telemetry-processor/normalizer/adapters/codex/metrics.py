"""Codex metric adapter."""
from __future__ import annotations

from ...common.context import IngestContext
from ...common.metric import build_metric_event
from ...model import NormalizedMetric
from .common import ADAPTER, ADAPTER_VERSION, build_client, build_identity


def to_event(
    res_attrs: dict,
    rec: dict,
    attrs: dict,
    name: str,
    ctx: IngestContext,
) -> NormalizedMetric:
    return build_metric_event(
        res_attrs=res_attrs,
        rec=rec,
        attrs=attrs,
        name=name,
        ctx=ctx,
        identity=build_identity(res_attrs, attrs, ctx.tenant_id),
        client=build_client(res_attrs, attrs),
        adapter=ADAPTER,
        adapter_version=ADAPTER_VERSION,
    )
