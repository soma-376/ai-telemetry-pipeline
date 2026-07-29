from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from .common import Envelope, LlmCall, Lifecycle, ToolCall, ToolDecision
from .enums import LogKind


@dataclass
class Prompt:
    length: int | None = None
    command_name: str | None = None


@dataclass
class LlmResponse:
    model: str | None = None
    response_length: int | None = None
    source: str | None = None
    request_id: str | None = None
    stop_reason: str | None = None
    refusal_category: str | None = None


LogPayload = Union[
    Prompt,
    LlmCall,
    LlmResponse,
    ToolCall,
    ToolDecision,
    Lifecycle,
]


@dataclass
class NormalizedLog:
    envelope: Envelope
    type: LogKind = LogKind.OTHER
    payload: LogPayload | None = None
    turn_id: str | None = None
    call_id: str | None = None
    sequence: int | None = None
