from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from .common import Envelope, LlmCall, Lifecycle, ToolCall, ToolDecision
from .enums import SpanKind

SpanPayload = Union[LlmCall, ToolCall, ToolDecision, Lifecycle]


@dataclass
class NormalizedSpan:
    envelope: Envelope
    type: SpanKind = SpanKind.OTHER
    payload: SpanPayload | None = None
    trace_id: str | None = None
    span_id: str | None = None
    parent_id: str | None = None
    call_id: str | None = None
