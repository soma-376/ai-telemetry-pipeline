#!/usr/bin/env python3
"""Claude Code log adapter — 원시 OTLP → NormalizedLog.

프롬프트/응답 원문은 읽지 않는다(콜렉터에서 삭제되어 도착; 어댑터도 방어적으로 드롭).
"""
from __future__ import annotations

from dataclasses import dataclass

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
    LlmResponse,
    Prompt,
    Tokens,
    ToolAction,
    ToolCall,
    ToolDecision,
    ToolKind,
    ValueSource,
)
from ...otlp import (
    _extract_command,
    _extract_files,
    _leftover_raw,
    _merge_json_attrs,
    _opt_bool,
    _opt_float,
    _opt_int,
    _opt_str,
    _parse_ts,
)
from .common import ADAPTER, ADAPTER_VERSION, build_client, build_identity

_CLAUDE_ACTION = {
    "Edit": ToolAction.EDIT,
    "Write": ToolAction.WRITE,
    "NotebookEdit": ToolAction.EDIT,
    "MultiEdit": ToolAction.EDIT,
    "Read": ToolAction.READ,
    "Grep": ToolAction.SEARCH,
    "Glob": ToolAction.SEARCH,
    "WebFetch": ToolAction.FETCH,
    "WebSearch": ToolAction.SEARCH,
    "Bash": ToolAction.EXEC,
    "PowerShell": ToolAction.EXEC,
}
_CLAUDE_FILE_KEYS = ("file_path", "notebook_path", "path", "pattern")
_CLAUDE_CMD_KEYS = ("command", "bash_command", "full_command")


@dataclass(frozen=True)
class DecisionMapping:
    decision: Decision = Decision.UNKNOWN
    decided_by: DecisionSource = DecisionSource.UNKNOWN
    scope: DecisionScope = DecisionScope.UNKNOWN


# CC tool_decision.source 는 결정 주체 외에 결과·범위 정보도 포함한다.
_CLAUDE_DECISION_SOURCE_MAP: dict[str, DecisionMapping] = {
    "config": DecisionMapping(decided_by=DecisionSource.CONFIG),
    "hook": DecisionMapping(decided_by=DecisionSource.HOOK),
    "user_permanent": DecisionMapping(
        decision=Decision.ACCEPT,
        decided_by=DecisionSource.USER,
        scope=DecisionScope.PERMANENT,
    ),
    "user_temporary": DecisionMapping(
        decision=Decision.ACCEPT,
        decided_by=DecisionSource.USER,
    ),
    "user_reject": DecisionMapping(
        decision=Decision.REJECT,
        decided_by=DecisionSource.USER,
        scope=DecisionScope.ONCE,
    ),
    "user_abort": DecisionMapping(
        decision=Decision.ABORT,
        decided_by=DecisionSource.USER,
        scope=DecisionScope.ONCE,
    ),
}

_CLAUDE_DECISION_VALUE_MAP: dict[str, Decision] = {
    "accept": Decision.ACCEPT,
    "modify": Decision.MODIFY,
    "reject": Decision.REJECT,
    "abort": Decision.ABORT,
}


def to_event(
    res_attrs: dict, rec: dict, attrs: dict, name: str, ctx: IngestContext
) -> NormalizedLog | None:
    short = name.replace("claude_code.", "")

    identity = build_identity(res_attrs, attrs, ctx.tenant_id)
    client = build_client(res_attrs, attrs)
    session = _opt_str(attrs, res_attrs, keys=("session.id",)) or "(unknown)"
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
        turn_id=_opt_str(attrs, keys=("prompt.id",)),
        sequence=_opt_int(attrs, "event.sequence"),
    )

    if short == "api_request":
        cost = _opt_float(attrs, "cost_usd")
        tokens = Tokens(
            input=_opt_int(attrs, "input_tokens"),
            output=_opt_int(attrs, "output_tokens"),
            cache_read=_opt_int(attrs, "cache_read_tokens"),
            cache_create=_opt_int(attrs, "cache_creation_tokens"),
        )
        ev.type = LogKind.LLM_CALL
        ev.payload = LlmCall(
            model=_opt_str(attrs, keys=("model",)),
            tokens=tokens,
            cost_usd=cost,
            # CC 는 세 툴 중 유일하게 USD 를 직접 준다.
            cost_source=(
                ValueSource.REPORTED if cost is not None else ValueSource.ESTIMATED
            ),
            source=_opt_str(attrs, keys=("query_source",)),
            duration_ms=_opt_int(attrs, "duration_ms"),
            ttft_ms=_opt_int(attrs, "ttft_ms"),
            stop_reason=_opt_str(attrs, keys=("stop_reason",)),
            # 문서상 api_error 에만 있는 속성이다. api_request 에 생기면 자동 흡수된다.
            attempt=_opt_int(attrs, "attempt"),
            request_id=_opt_str(attrs, keys=("request_id",)),
        )

    elif short == "assistant_response":
        # api_request 와 짝인 응답측. 토큰·비용은 api_request 에 있으므로
        # 여기선 응답 고유 정보만. LLM_CALL 과 분리해 호출 수 왜곡을 막는다.
        ev.type = LogKind.LLM_RESPONSE
        ev.payload = LlmResponse(
            model=_opt_str(attrs, keys=("model",)),
            response_length=_opt_int(attrs, "response_length"),
            source=_opt_str(attrs, keys=("query_source",)),
            request_id=_opt_str(attrs, keys=("request_id",)),
            stop_reason=_opt_str(attrs, keys=("stop_reason",)),
        )

    elif short == "api_error":
        ev.type = LogKind.LLM_CALL
        ev.payload = LlmCall(
            model=_opt_str(attrs, keys=("model",)),
            error_type=_opt_str(attrs, keys=("error_type", "error")),
            status_code=_opt_int(attrs, "status_code"),
            duration_ms=_opt_int(attrs, "duration_ms"),
            attempt=_opt_int(attrs, "attempt"),
            request_id=_opt_str(attrs, keys=("request_id",)),
        )

    elif short == "api_refusal":
        # 거부는 HTTP 오류가 아니라 성공 응답 스트림으로 도착한다 → 짝인 api_request 가
        # 토큰·비용을 싣고 따로 나간다. assistant_response 와 같은 이유로 LLM_RESPONSE
        # 로 두어 '호출 수' 가 2배로 왜곡되지 않게 한다.
        #
        # ⚠️ server_fallback_hop=true 는 서버가 다른 모델로 재시도해 사용자가 보지 못한
        #    홉이다. 한 턴이 hop(true) + 최종(false) 을 모두 낼 수 있으므로 거부 '건수'
        #    를 셀 때는 _ingest.raw["server_fallback_hop"] 로 걸러야 한다.
        ev.type = LogKind.LLM_RESPONSE
        ev.payload = LlmResponse(
            model=_opt_str(attrs, keys=("model",)),
            source=_opt_str(attrs, keys=("query_source",)),
            request_id=_opt_str(attrs, keys=("request_id",)),
            # 이 이벤트의 존재 자체가 stop_reason=refusal 을 뜻한다(속성으로는 오지 않음).
            stop_reason="refusal",
            # category 는 OTEL_LOG_TOOL_DETAILS=1 이고 has_category=true 일 때만 온다.
            refusal_category=_opt_str(attrs, keys=("category",)),
        )

    elif short in ("tool_result", "tool_decision"):
        tool_name = _opt_str(attrs, keys=("tool_name",))
        call_id = _opt_str(attrs, keys=("tool_use_id",))
        inferred = call_id is None
        if call_id is None:
            call_id = synth_call_id(
                session, ev.sequence, ts, tool_name or "?"
            )
        ev.call_id = call_id
        ev.envelope._ingest.call_id_inferred = inferred
        args = _merge_json_attrs(attrs, "tool_input", "tool_parameters")

        if short == "tool_result":
            ev.type = LogKind.TOOL_CALL
            ev.payload = ToolCall(
                tool_name=tool_name,
                tool_kind=(
                    ToolKind.MCP if attrs.get("mcp_server.name") else ToolKind.NATIVE
                ),
                action=_CLAUDE_ACTION.get(tool_name or "", ToolAction.OTHER),
                files=_extract_files(args, _CLAUDE_FILE_KEYS),
                command=_extract_command(args, _CLAUDE_CMD_KEYS),
                success=_opt_bool(attrs, "success"),
                error_type=_opt_str(attrs, keys=("error_type",)),
                duration_ms=_opt_int(attrs, "duration_ms"),
                mcp_server=_opt_str(attrs, keys=("mcp_server.name",)),
                agent_id=_opt_str(attrs, keys=("agent_id",)),
                parent_agent_id=_opt_str(attrs, keys=("parent_agent_id",)),
            )
        else:
            raw_dec = _opt_str(attrs, keys=("decision",))
            raw_source = _opt_str(attrs, keys=("source",))
            mapping = _CLAUDE_DECISION_SOURCE_MAP.get(
                raw_source or "", DecisionMapping()
            )
            decision = _CLAUDE_DECISION_VALUE_MAP.get(raw_dec or "", mapping.decision)
            ev.type = LogKind.TOOL_DECISION
            ev.envelope._ingest.raw_value = raw_dec
            ev.payload = ToolDecision(
                decision=decision,
                decided_by=mapping.decided_by,
                scope=mapping.scope,
                tool_name=tool_name,
            )

    elif short == "mcp_server_connection":
        # MCP 서버 연결 이벤트 → Lifecycle. 서버·전송·상태를 attrs 로 승격해
        # "어떤 외부 서버에 붙었나"(거버넌스)를 살린다.
        attrs_map = {
            k: str(attrs[k])
            for k in (
                "server_name",
                "transport_type",
                "status",
                "server_scope",
                "is_plugin",
                "error",
                "duration_ms",
            )
            if attrs.get(k) is not None and attrs.get(k) != ""
        }
        ev.type = LogKind.LIFECYCLE
        ev.payload = Lifecycle(kind="mcp_connection", attrs=attrs_map)

    elif short == "compaction":
        # pre/post_tokens 는 압축 전후의 '컨텍스트 크기'지 청구된 토큰이 아니다.
        # Lifecycle 에 두면 billable(Tokens.input/output/cache_*) 과 구조적으로 섞일
        # 수 없다 — 더하면 이중계산이 되는 값이므로 이 분리가 안전장치다.
        # 압축이 실제로 태운 토큰은 query_source="compact" 인 별도 api_request 에 있다.
        ev.type = LogKind.LIFECYCLE
        ev.payload = Lifecycle(
            kind="compaction",
            tokens_before=_opt_int(attrs, "pre_tokens"),
            tokens_after=_opt_int(attrs, "post_tokens"),
            attrs={
                k: str(attrs[k])
                for k in (
                    "trigger",
                    "success",
                    "duration_ms",
                    "error",
                    "precompute_reuse",
                )
                if attrs.get(k) is not None and attrs.get(k) != ""
            },
        )

    elif short == "user_prompt":
        ev.type = LogKind.USER_PROMPT
        ev.payload = Prompt(
            length=_opt_int(attrs, "prompt_length"),
            command_name=_opt_str(attrs, keys=("command_name",)),
        )

    else:
        return None

    return finalize(ev)
