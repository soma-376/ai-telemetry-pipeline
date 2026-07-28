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
    _map_bool,
    _map_float,
    _map_int,
    _map_str,
    _merge_json_attrs,
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
    session = (
        _map_str(attrs, "envelope.session_id", "session.id", res_attrs=res_attrs)
        or "(unknown)"
    )
    ts = _parse_ts(rec, attrs)

    ingest = build_ingest(
        ctx=ctx,
        adapter=ADAPTER,
        adapter_version=ADAPTER_VERSION,
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
        turn_id=_map_str(attrs, "turn_id", "prompt.id", required=False),
        sequence=_map_int(attrs, "sequence", "event.sequence", required=False),
    )

    if short == "api_request":
        cost = _map_float(attrs, "payload.cost_usd", "cost_usd")
        tokens = Tokens(
            input=_map_int(attrs, "payload.tokens.input", "input_tokens"),
            output=_map_int(attrs, "payload.tokens.output", "output_tokens"),
            cache_read=_map_int(
                attrs, "payload.tokens.cache_read", "cache_read_tokens"
            ),
            cache_create=_map_int(
                attrs, "payload.tokens.cache_create", "cache_creation_tokens"
            ),
        )
        ev.type = LogKind.LLM_CALL
        ev.payload = LlmCall(
            model=_map_str(attrs, "payload.model", "model"),
            tokens=tokens,
            cost_usd=cost,
            # CC 는 세 툴 중 유일하게 USD 를 직접 준다.
            cost_source=(
                ValueSource.REPORTED if cost is not None else ValueSource.ESTIMATED
            ),
            source=_map_str(attrs, "payload.source", "query_source", required=False),
            reasoning_effort=_map_str(
                attrs, "payload.reasoning_effort", "effort", required=False
            ),
            duration_ms=_map_int(attrs, "payload.duration_ms", "duration_ms"),
            ttft_ms=_map_int(attrs, "payload.ttft_ms", "ttft_ms", required=False),
            stop_reason=_map_str(
                attrs, "payload.stop_reason", "stop_reason", required=False
            ),
            # 문서상 api_error 에만 있는 속성이다. api_request 에 생기면 자동 흡수된다.
            attempt=_map_int(attrs, "payload.attempt", "attempt", required=False),
            request_id=_map_str(
                attrs, "payload.request_id", "request_id", required=False
            ),
        )

    elif short == "assistant_response":
        # api_request 와 짝인 응답측. 토큰·비용은 api_request 에 있으므로
        # 여기선 응답 고유 정보만. LLM_CALL 과 분리해 호출 수 왜곡을 막는다.
        ev.type = LogKind.LLM_RESPONSE
        ev.payload = LlmResponse(
            model=_map_str(attrs, "payload.model", "model"),
            response_length=_map_int(
                attrs, "payload.response_length", "response_length"
            ),
            source=_map_str(attrs, "payload.source", "query_source", required=False),
            request_id=_map_str(
                attrs, "payload.request_id", "request_id", required=False
            ),
            stop_reason=_map_str(
                attrs, "payload.stop_reason", "stop_reason", required=False
            ),
        )

    elif short == "api_error":
        ev.type = LogKind.LLM_CALL
        ev.payload = LlmCall(
            model=_map_str(attrs, "payload.model", "model"),
            error_type=_map_str(attrs, "payload.error_type", "error_type", "error"),
            # 네트워크 단절 등 HTTP 응답이 없는 오류는 status_code 가 없다.
            status_code=_map_int(
                attrs, "payload.status_code", "status_code", required=False
            ),
            duration_ms=_map_int(
                attrs, "payload.duration_ms", "duration_ms", required=False
            ),
            attempt=_map_int(attrs, "payload.attempt", "attempt", required=False),
            request_id=_map_str(
                attrs, "payload.request_id", "request_id", required=False
            ),
        )

    elif short == "api_refusal":
        # 거부는 HTTP 오류가 아니라 성공 응답 스트림으로 도착한다 → 짝인 api_request 가
        # 토큰·비용을 싣고 따로 나간다. assistant_response 와 같은 이유로 LLM_RESPONSE
        # 로 두어 '호출 수' 가 2배로 왜곡되지 않게 한다.
        #
        # ⚠️ server_fallback_hop=true 는 서버가 다른 모델로 재시도해 사용자가 보지 못한
        #    홉이다. 한 턴이 hop(true) + 최종(false) 을 모두 낼 수 있으므로 거부 '건수'
        #    를 셀 때는 원본 아카이브의 server_fallback_hop 값으로 걸러야 한다.
        ev.type = LogKind.LLM_RESPONSE
        ev.payload = LlmResponse(
            model=_map_str(attrs, "payload.model", "model"),
            source=_map_str(attrs, "payload.source", "query_source", required=False),
            request_id=_map_str(
                attrs, "payload.request_id", "request_id", required=False
            ),
            # 이 이벤트의 존재 자체가 stop_reason=refusal 을 뜻한다(속성으로는 오지 않음).
            stop_reason="refusal",
            # category 는 OTEL_LOG_TOOL_DETAILS=1 이고 has_category=true 일 때만 온다.
            refusal_category=_map_str(
                attrs, "payload.refusal_category", "category", required=False
            ),
        )

    elif short in ("tool_result", "tool_decision"):
        tool_name = _map_str(attrs, "payload.tool_name", "tool_name")
        # tool_use_id 부재는 합성으로 복구하는 알려진 케이스(call_id_inferred 로
        # 추적)라 매핑 미스로 세지 않는다.
        call_id = _map_str(attrs, "call_id", "tool_use_id", required=False)
        inferred = call_id is None
        if call_id is None:
            call_id = synth_call_id(
                session, ev.sequence, ts, tool_name or "?"
            )
        ev.call_id = call_id
        ev.envelope._ingest.call_id_inferred = inferred
        args = _merge_json_attrs(attrs, "tool_input", "tool_parameters")

        if short == "tool_result":
            mcp_server = _map_str(
                attrs, "payload.mcp_server", "mcp_server.name", required=False
            )
            ev.type = LogKind.TOOL_CALL
            ev.payload = ToolCall(
                tool_name=tool_name,
                tool_kind=ToolKind.MCP if mcp_server else ToolKind.NATIVE,
                action=_CLAUDE_ACTION.get(tool_name or "", ToolAction.OTHER),
                files=_extract_files(args, _CLAUDE_FILE_KEYS),
                command=_extract_command(args, _CLAUDE_CMD_KEYS),
                success=_map_bool(attrs, "payload.success", "success"),
                error_type=_map_str(
                    attrs, "payload.error_type", "error_type", required=False
                ),
                duration_ms=_map_int(
                    attrs, "payload.duration_ms", "duration_ms", required=False
                ),
                mcp_server=mcp_server,
                agent_id=_map_str(
                    attrs, "payload.agent_id", "agent_id", required=False
                ),
                parent_agent_id=_map_str(
                    attrs, "payload.parent_agent_id", "parent_agent_id",
                    required=False,
                ),
            )
        else:
            raw_dec = _map_str(attrs, "payload.decision", "decision")
            raw_source = _map_str(attrs, "payload.decided_by", "source")
            mapping = _CLAUDE_DECISION_SOURCE_MAP.get(
                raw_source or "", DecisionMapping()
            )
            decision = _CLAUDE_DECISION_VALUE_MAP.get(raw_dec or "", mapping.decision)
            ev.type = LogKind.TOOL_DECISION
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
            tokens_before=_map_int(attrs, "payload.tokens_before", "pre_tokens"),
            tokens_after=_map_int(attrs, "payload.tokens_after", "post_tokens"),
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
            length=_map_int(attrs, "payload.length", "prompt_length"),
            # 슬래시 커맨드가 아닌 일반 프롬프트에는 없다.
            command_name=_map_str(
                attrs, "payload.command_name", "command_name", required=False
            ),
        )

    else:
        return None

    return finalize(ev)
