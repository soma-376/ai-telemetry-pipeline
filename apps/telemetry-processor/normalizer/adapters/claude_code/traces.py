#!/usr/bin/env python3
"""Claude Code trace adapter — 스팬 하나 → NormalizedSpan 하나.

로그와 같은 stateless 규칙(1 레코드 = 1 NormalizedSpan)이다. 스팬 3개(tool/execution/
blocked_on_user)를 합치는 건 조인이라 여기서 안 한다 — 뷰(트리 조립) 몫이다.
구조는 span_id/parent_id 로, 역할은 type(SpanKind)으로 보존해 뷰가 구분·조립한다.

토큰·비용은 담지 않는다. 같은 LLM 호출을 로그(api_request)가 이미 싣고,
둘은 request_id 로 조인된다 → 여기서 또 실으면 이중계산이다. signal=SPAN 이라
사용량 집계(signal=LOG)와도 섞이지 않는다.
"""
from __future__ import annotations

from ...common.context import IngestContext
from ...common.envelope import build_envelope, build_ingest, finalize
from ...model import (
    NormalizedSpan,
    SpanKind,
    Lifecycle,
    LlmCall,
    ToolAction,
    ToolCall,
    ToolDecision,
    ToolKind,
)
from ...otlp import _map_bool, _map_int, _map_str
from .common import ADAPTER, ADAPTER_VERSION, build_client, build_identity
from .logs import (
    _CLAUDE_ACTION,
    _CLAUDE_DECISION_SOURCE_MAP,
    _CLAUDE_DECISION_VALUE_MAP,
    DecisionMapping,
)


def _start(rec: dict) -> float:
    n = rec.get("startTimeUnixNano")
    return int(n) / 1e9 if n else 0.0


def _dur_ms(rec: dict) -> int | None:
    s, e = rec.get("startTimeUnixNano"), rec.get("endTimeUnixNano")
    return int((int(e) - int(s)) / 1e6) if s and e else None


def to_event(
    res_attrs: dict, rec: dict, attrs: dict, name: str, ctx: IngestContext
) -> NormalizedSpan | None:
    short = name.replace("claude_code.", "")

    identity = build_identity(res_attrs, attrs, ctx.tenant_id)
    client = build_client(res_attrs, attrs)
    session = (
        _map_str(attrs, "envelope.session_id", "session.id", res_attrs=res_attrs)
        or "(unknown)"
    )

    ingest = build_ingest(
        ctx=ctx,
        adapter=ADAPTER,
        adapter_version=ADAPTER_VERSION,
    )
    envelope = build_envelope(
        client=client, identity=identity, session_id=session, ts=_start(rec), ingest=ingest
    )
    ev = NormalizedSpan(
        envelope=envelope,
        trace_id=rec.get("traceId"),
        span_id=rec.get("spanId"),
        parent_id=rec.get("parentSpanId") or None,
    )
    dur = _dur_ms(rec)

    if short == "interaction":
        # 턴 루트. duration·프롬프트 길이만(원문 없음). 트리 루트 마커.
        ev.type = SpanKind.TURN
        ev.payload = Lifecycle(
            kind="turn",
            attrs={
                k: str(v)
                for k, v in (
                    ("duration_ms", dur),
                    (
                        "prompt_length",
                        _map_int(
                            attrs, "payload.prompt_length", "user_prompt_length"
                        ),
                    ),
                )
                if v is not None
            },
        )

    elif short == "llm_request":
        # 구조·타이밍만. 토큰/비용은 로그(api_request)에 있고 request_id 로 조인.
        ev.type = SpanKind.LLM_REQUEST
        ev.payload = LlmCall(
            model=_map_str(attrs, "payload.model", "model", "gen_ai.request.model"),
            duration_ms=dur,
            ttft_ms=_map_int(attrs, "payload.ttft_ms", "ttft_ms", required=False),
            stop_reason=_map_str(
                attrs, "payload.stop_reason", "stop_reason", required=False
            ),
            attempt=_map_int(attrs, "payload.attempt", "attempt", required=False),
            request_id=_map_str(
                attrs, "payload.request_id", "request_id", "client_request_id",
                required=False,
            ),
        )

    elif short == "tool":
        # 툴 호출의 '무엇'(이름·파일·명령). 성공여부는 자식 execution 에 있다.
        tool_name = _map_str(attrs, "payload.tool_name", "tool_name")
        ev.type = SpanKind.TOOL
        # tool_use_id 부재는 로그측이 합성으로 복구하는 알려진 케이스라
        # 매핑 미스로 세지 않는다(logs.py 와 동일 취급).
        ev.call_id = _map_str(attrs, "call_id", "tool_use_id", required=False)
        # 파일·명령은 해당 종류의 툴에만 있다.
        fp = _map_str(attrs, "payload.files", "file_path", required=False)
        ev.payload = ToolCall(
            tool_name=tool_name,
            tool_kind=ToolKind.NATIVE,
            action=_CLAUDE_ACTION.get(tool_name or "", ToolAction.OTHER),
            files=[fp] if fp else [],
            command=_map_str(attrs, "payload.command", "full_command", required=False),
            duration_ms=dur,
        )

    elif short == "tool.execution":
        # 툴 호출의 '결과'(성공/실패). 부모(tool)와 parent_id 로 이어진다.
        ev.type = SpanKind.TOOL_EXECUTION
        ev.call_id = _map_str(attrs, "call_id", "tool_use_id", required=False)
        ev.payload = ToolCall(
            success=_map_bool(attrs, "payload.success", "success"),
            error_type=_map_str(
                attrs, "payload.error_type", "error", required=False
            ),
            duration_ms=dur,
        )

    elif short == "tool.blocked_on_user":
        # 승인 게이트. 결정·주체·대기시간.
        raw_dec = _map_str(attrs, "payload.decision", "decision")
        raw_src = _map_str(attrs, "payload.decided_by", "source")
        mapping = _CLAUDE_DECISION_SOURCE_MAP.get(raw_src or "", DecisionMapping())
        ev.type = SpanKind.TOOL_GATE
        ev.payload = ToolDecision(
            decision=_CLAUDE_DECISION_VALUE_MAP.get(raw_dec or "", mapping.decision),
            decided_by=mapping.decided_by,
            scope=mapping.scope,
            blocked_on_user_ms=dur,
        )

    elif short == "hook":
        # 훅 실행(베타·게이트). 이벤트·개수·소요시간을 Lifecycle attrs 로 보존.
        ev.type = SpanKind.HOOK
        ev.payload = Lifecycle(
            kind="hook",
            attrs={
                k: str(attrs[k])
                for k in (
                    "hook_event", "hook_name", "num_hooks",
                    "num_blocking", "num_success", "duration_ms",
                )
                if attrs.get(k) is not None and attrs.get(k) != ""
            },
        )

    else:
        return None  # 미지의 스팬은 무시

    return finalize(ev)
