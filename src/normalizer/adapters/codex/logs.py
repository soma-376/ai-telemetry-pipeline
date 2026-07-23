#!/usr/bin/env python3
"""Codex log adapter — 원시 OTLP → NormalizedLog.

⚠️ 아래 키명은 공식 문서 스키마 기준 to-spec 이며 실데이터로 미검증이다.
   승격 안 된 속성은 _ingest.raw 에 쌓이므로, 실데이터를 흘린 뒤 raw 를 확인할 것.
   Codex 는 tool_use_id 를 주지 않아 call_id 를 합성한다(join.pair_call_ids 가 이음).
"""
from __future__ import annotations

from ...common.call_id import synth_call_id
from ...common.context import IngestContext
from ...common.envelope import build_envelope, build_ingest, finalize
from ...model import (
    Decision,
    DecisionScope,
    DecisionSource,
    NormalizedLog,
    LogKind,
    Lifecycle,
    LlmCall,
    Prompt,
    Tokens,
    ToolAction,
    ToolCall,
    ToolDecision,
    ToolKind,
    ValueSource,
)
from ...pricing import estimate_cost
from ...otlp import (
    _extract_command,
    _extract_files,
    _leftover_raw,
    _merge_json_attrs,
    _opt_bool,
    _opt_int,
    _opt_str,
    _parse_ts,
)
from .common import ADAPTER, ADAPTER_VERSION, build_client, build_identity

_CODEX_ACTION = {
    "apply_patch": ToolAction.EDIT,
    "edit": ToolAction.EDIT,
    "write": ToolAction.WRITE,
    "write_file": ToolAction.WRITE,
    "read_file": ToolAction.READ,
    "read": ToolAction.READ,
    "grep": ToolAction.SEARCH,
    "web_search": ToolAction.SEARCH,
    "web.search": ToolAction.SEARCH,
    "shell": ToolAction.EXEC,
    "local_shell": ToolAction.EXEC,
    "exec": ToolAction.EXEC,
    "bash": ToolAction.EXEC,
}
_CODEX_FILE_KEYS = ("path", "file_path", "file", "changed_files", "paths")
_CODEX_CMD_KEYS = ("command", "cmd", "shell_command", "full_command")

# Codex 승인 결과를 결정·주체·적용 범위로 분리한다.
_CODEX_DECISION = {
    "approved": (Decision.ACCEPT, DecisionSource.USER, DecisionScope.ONCE),
    "approved_for_session": (
        Decision.ACCEPT,
        DecisionSource.USER,
        DecisionScope.SESSION,
    ),
    "approved_with_amendment": (
        Decision.MODIFY,
        DecisionSource.USER,
        DecisionScope.ONCE,
    ),
    "denied": (Decision.REJECT, DecisionSource.USER, DecisionScope.ONCE),
    "abort": (Decision.ABORT, DecisionSource.USER, DecisionScope.ONCE),
}


def to_event(
    res_attrs: dict, rec: dict, attrs: dict, name: str, ctx: IngestContext
) -> NormalizedLog:
    short = name.replace("codex.", "")

    identity = build_identity(res_attrs, attrs, ctx.tenant_id)
    client = build_client(res_attrs, attrs)
    session = (
        _opt_str(
            attrs,
            res_attrs,
            keys=("conversation.id", "conversation_id", "thread.id", "session.id"),
        )
        or "(unknown)"
    )
    ts = _parse_ts(rec, attrs)

    ingest = build_ingest(
        ctx=ctx,
        adapter=ADAPTER,
        adapter_version=ADAPTER_VERSION,
        raw=_leftover_raw(attrs),
    )
    envelope = build_envelope(
        client=client,
        identity=identity,
        session_id=session,
        ts=ts,
        ingest=ingest,
    )
    ev = NormalizedLog(
        envelope=envelope,
        # Codex 는 턴 상관 ID 를 텔레메트리로 노출하지 않는다 → 세그먼트는 갭 휴리스틱 폴백.
        turn_id=None,
        sequence=_opt_int(attrs, "event.sequence"),
    )

    if short == "sse_event":
        # 토큰은 response.completed 시점의 sse_event 에 실린다.
        tokens = Tokens(
            input=_opt_int(
                attrs, "input_token_count", "input_tokens", "prompt_tokens"
            ),
            output=_opt_int(
                attrs, "output_token_count", "output_tokens", "completion_tokens"
            ),
            cache_read=_opt_int(
                attrs,
                "cached_token_count",
                "cached_input_tokens",
                "cache_read_tokens",
                "cached_tokens",
            ),
            # cache_create: Codex 는 캐시 생성 토큰을 구분하지 않는다 → None 유지.
            reasoning=_opt_int(
                attrs,
                "reasoning_token_count",
                "reasoning_output_tokens",
                "reasoning_tokens",
            ),
            total_reported=_opt_int(attrs, "total_tokens"),
        )
        if tokens.billable > 0 or tokens.total_reported is not None:
            model = _opt_str(attrs, res_attrs, keys=("model",))
            cost_usd = (
                estimate_cost(
                    model,
                    tokens.input or 0,
                    tokens.output or 0,
                    tokens.cache_read or 0,
                    tokens.cache_create or 0,
                )
                if tokens.billable > 0
                else None
            )
            ev.type = LogKind.LLM_CALL
            ev.payload = LlmCall(
                model=model,
                tokens=tokens,
                cost_usd=cost_usd,
                cost_source=ValueSource.ESTIMATED,
                source=_opt_str(attrs, keys=("originator", "session_source")),
                duration_ms=_opt_int(attrs, "duration_ms"),
            )

    elif short in ("tool_result", "tool_decision"):
        tool_name = _opt_str(attrs, keys=("tool_name", "tool", "name"))
        # Codex 는 tool_use_id 를 주지 않는다 → 합성한다.
        ev.call_id = synth_call_id(
            session, ev.sequence, ts, tool_name or "?"
        )
        ev.envelope._ingest.call_id_inferred = True
        args = _merge_json_attrs(
            attrs, "tool_input", "tool_parameters", "arguments", "input"
        )

        if short == "tool_result":
            ev.type = LogKind.TOOL_CALL
            ev.payload = ToolCall(
                tool_name=tool_name,
                tool_kind=ToolKind.NATIVE,
                action=_CODEX_ACTION.get((tool_name or "").lower(), ToolAction.OTHER),
                files=_extract_files(args, _CODEX_FILE_KEYS),
                command=_extract_command(args, _CODEX_CMD_KEYS),
                success=_opt_bool(attrs, "success"),
                duration_ms=_opt_int(attrs, "duration_ms"),
            )
        else:
            raw_dec = _opt_str(attrs, keys=("decision",))
            decision, decided_by, scope = _CODEX_DECISION.get(
                raw_dec or "",
                (Decision.UNKNOWN, DecisionSource.UNKNOWN, DecisionScope.UNKNOWN),
            )
            ev.type = LogKind.TOOL_DECISION
            ev.envelope._ingest.raw_value = raw_dec
            ev.payload = ToolDecision(
                decision=decision,
                decided_by=decided_by,
                scope=scope,
                tool_name=tool_name,
            )

    elif short == "user_prompt":
        ev.type = LogKind.USER_PROMPT
        ev.payload = Prompt(length=_opt_int(attrs, "prompt_length", "length"))

    elif short == "conversation_starts":
        ev.type = LogKind.LIFECYCLE
        ev.payload = Lifecycle(kind="session_start")

    return finalize(ev)
