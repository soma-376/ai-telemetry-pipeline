#!/usr/bin/env python3
"""Map Codex OTLP spans to one ``NormalizedSpan`` per input span.

Codex documents these names as structured OTel events.  Accepting the same
names on the traces endpoint keeps the normalizer useful for collectors that
promote those events to spans.
"""
from __future__ import annotations

from ...common.call_id import synth_call_id
from ...common.context import IngestContext
from ...common.envelope import build_envelope, build_ingest, finalize
from ...model import (
    Decision,
    DecisionScope,
    DecisionSource,
    Lifecycle,
    LlmCall,
    NormalizedSpan,
    SpanKind,
    ToolAction,
    ToolCall,
    ToolDecision,
    ToolKind,
)
from ...otlp import (
    _extract_command,
    _extract_files,
    _map_bool,
    _map_int,
    _map_str,
    _merge_json_attrs,
)
from .common import ADAPTER, ADAPTER_VERSION, build_client, build_identity
from .logs import _CODEX_ACTION, _CODEX_CMD_KEYS, _CODEX_DECISION, _CODEX_FILE_KEYS


def _start(rec: dict) -> float:
    value = rec.get("startTimeUnixNano")
    return int(value) / 1e9 if value else 0.0


def _duration_ms(rec: dict, attrs: dict) -> int | None:
    start = rec.get("startTimeUnixNano")
    end = rec.get("endTimeUnixNano")
    if start and end:
        return int((int(end) - int(start)) / 1e6)
    return _map_int(attrs, "payload.duration_ms", "duration_ms", required=False)


def to_event(
    res_attrs: dict, rec: dict, attrs: dict, name: str, ctx: IngestContext
) -> NormalizedSpan | None:
    short = name.removeprefix("codex.")
    session = (
        _map_str(
            attrs,
            "envelope.session_id",
            "conversation.id",
            "conversation_id",
            "thread.id",
            "session.id",
            res_attrs=res_attrs,
        )
        or "(unknown)"
    )
    started_at = _start(rec)
    envelope = build_envelope(
        client=build_client(res_attrs, attrs),
        identity=build_identity(res_attrs, attrs, ctx.tenant_id),
        session_id=session,
        ts=started_at,
        ingest=build_ingest(ctx=ctx, adapter=ADAPTER, adapter_version=ADAPTER_VERSION),
    )
    ev = NormalizedSpan(
        envelope=envelope,
        trace_id=rec.get("traceId"),
        span_id=rec.get("spanId"),
        parent_id=rec.get("parentSpanId") or None,
    )
    duration_ms = _duration_ms(rec, attrs)

    if short == "conversation_starts":
        ev.type = SpanKind.TURN
        ev.payload = Lifecycle(
            kind="session_start",
            attrs={
                key: str(value)
                for key, value in (
                    ("duration_ms", duration_ms),
                    (
                        "reasoning_effort",
                        _map_str(
                            attrs,
                            "payload.reasoning_effort",
                            "model_reasoning_effort",
                            required=False,
                        ),
                    ),
                    (
                        "approval_policy",
                        _map_str(attrs, "approval_policy", required=False),
                    ),
                    (
                        "sandbox_policy",
                        _map_str(attrs, "sandbox_policy", required=False),
                    ),
                )
                if value is not None
            },
        )

    elif short == "api_request":
        ev.type = SpanKind.LLM_REQUEST
        ev.payload = LlmCall(
            model=_map_str(attrs, "payload.model", "model", res_attrs=res_attrs),
            duration_ms=duration_ms,
            attempt=_map_int(attrs, "payload.attempt", "attempt", required=False),
            request_id=_map_str(
                attrs,
                "payload.request_id",
                "request_id",
                "client_request_id",
                required=False,
            ),
            error_type=_map_str(
                attrs, "payload.error_type", "error_type", "error", required=False
            ),
            status_code=_map_int(
                attrs, "payload.status_code", "status_code", "status", required=False
            ),
        )

    elif short == "tool_result":
        tool_name = _map_str(
            attrs, "payload.tool_name", "tool_name", "tool", "name"
        )
        args = _merge_json_attrs(
            attrs, "tool_input", "tool_parameters", "arguments", "input"
        )
        ev.type = SpanKind.TOOL_EXECUTION
        ev.call_id = synth_call_id(session, None, started_at, tool_name or "?")
        ev.envelope._ingest.call_id_inferred = True
        ev.payload = ToolCall(
            tool_name=tool_name,
            tool_kind=ToolKind.NATIVE,
            action=_CODEX_ACTION.get((tool_name or "").lower(), ToolAction.OTHER),
            files=_extract_files(args, _CODEX_FILE_KEYS),
            command=_extract_command(args, _CODEX_CMD_KEYS),
            success=_map_bool(attrs, "payload.success", "success"),
            error_type=_map_str(
                attrs, "payload.error_type", "error_type", "error", required=False
            ),
            duration_ms=duration_ms,
        )

    elif short == "tool_decision":
        tool_name = _map_str(
            attrs, "payload.tool_name", "tool_name", "tool", "name"
        )
        raw_decision = _map_str(attrs, "payload.decision", "decision")
        decision, decided_by, scope = _CODEX_DECISION.get(
            raw_decision or "",
            (Decision.UNKNOWN, DecisionSource.UNKNOWN, DecisionScope.UNKNOWN),
        )
        ev.type = SpanKind.TOOL_GATE
        ev.call_id = synth_call_id(session, None, started_at, tool_name or "?")
        ev.envelope._ingest.call_id_inferred = True
        ev.payload = ToolDecision(
            decision=decision,
            decided_by=decided_by,
            scope=scope,
            blocked_on_user_ms=duration_ms,
            tool_name=tool_name,
        )

    else:
        return None

    return finalize(ev)
