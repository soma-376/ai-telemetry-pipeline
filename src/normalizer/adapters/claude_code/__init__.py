#!/usr/bin/env python3
"""Claude Code OTLP signal adapters."""
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
    """Return the Claude Code event name when this record belongs to Claude Code."""
    if isinstance(name, str) and name.startswith(PREFIX):
        return name
    return None


def to_event(
    res_attrs: dict, rec: dict, attrs: dict, name: str, ctx: IngestContext
) -> Normalized | None:
    mod = _SIGNAL.get(ctx.signal_type)
    return mod.to_event(res_attrs, rec, attrs, name, ctx) if mod else None


__all__ = ["PREFIX", "ADAPTER", "ADAPTER_VERSION", "match", "to_event"]
