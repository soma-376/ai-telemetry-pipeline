#!/usr/bin/env python3
"""Codex OTLP signal adapters."""
from __future__ import annotations

from ...common.context import IngestContext
from ...model import Normalized, SignalType
from . import logs, metrics, traces
from .common import ADAPTER, ADAPTER_VERSION, PREFIX

_SIGNAL = {
    SignalType.LOG: logs,
    SignalType.METRIC: metrics,
    SignalType.SPAN: traces,
}


def match(
    res_attrs: dict,
    rec: dict,
    attrs: dict,
    name: str,
    signal_type: SignalType,
) -> str | None:
    """Return the Codex event name when this record belongs to Codex."""
    event_name = attrs.get("event.name") if signal_type == SignalType.LOG else name
    if isinstance(event_name, str) and event_name.startswith(PREFIX):
        return event_name
    return None


def to_event(
    res_attrs: dict, rec: dict, attrs: dict, name: str, ctx: IngestContext
) -> Normalized | None:
    mod = _SIGNAL.get(ctx.signal_type)
    return mod.to_event(res_attrs, rec, attrs, name, ctx) if mod else None


__all__ = ["PREFIX", "ADAPTER", "ADAPTER_VERSION", "match", "to_event"]
