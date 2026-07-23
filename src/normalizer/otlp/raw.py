#!/usr/bin/env python3
"""미매핑 벤더 속성 보존 — 여기 쌓이는 것이 다음 승격 후보다."""
from __future__ import annotations

# 공통 필드로 승격 완료된 키 — raw 에 중복해 담지 않는다.
_MAPPED_KEYS = {
    "session.id", "conversation.id", "conversation_id", "thread.id",
    "user.email", "user.id", "user.account_id", "user.account_uuid",
    "organization.id", "auth_mode", "ingest.principal",
    "event.sequence", "event.timestamp", "prompt.id", "prompt_id",
    "model", "app.version", "service.version", "app.entrypoint",
    "originator", "session_source", "terminal.type", "query_source",
    "cost_usd", "input_tokens", "output_tokens", "cache_read_tokens",
    "cache_creation_tokens", "cached_input_tokens", "prompt_tokens",
    "completion_tokens", "cached_tokens", "reasoning_output_tokens",
    "reasoning_tokens", "total_tokens",
    "tool_name", "tool", "name", "tool_use_id", "tool_input", "tool_parameters",
    "arguments", "input", "decision", "source", "success", "duration_ms",
    "ttft_ms", "stop_reason", "attempt", "request_id", "status_code",
    "error", "error_type", "prompt_length", "length", "command_name",
    "mcp_server.name", "agent_id", "parent_agent_id",
    "response_length",
    # event.name 은 body(이벤트명)와 값이 동일한 중복 → raw 에 담지 않는다.
    "event.name",
    # mcp_server_connection 에서 Lifecycle.attrs 로 승격한 키들.
    "server_name", "transport_type", "status", "server_scope", "is_plugin",
    # compaction 에서 Lifecycle 로 승격한 키들.
    "pre_tokens", "post_tokens", "trigger", "precompute_reuse",
    # api_refusal 에서 LlmResponse.refusal_category 로 승격.
    "category",
}

# 고위험 원문. 콜렉터가 sanitize 하는 게 원칙이지만, 오설정/미설정 시 원문이
# 새지 않도록 어댑터에서 방어적으로 드롭한다 (raw 로도 흘리지 않는다).
_CONTENT_DENYLIST = {"prompt", "response"}


def _leftover_raw(attrs: dict) -> dict[str, str]:
    """승격되지 않은 벤더 속성. 여기 쌓이는 것이 다음 승격 후보다.

    Codex 매핑은 to-spec 이고 Gemini 는 미착수 — 실데이터를 흘린 뒤
    이 맵을 보고 어떤 키가 실제로 오는지 확인할 것.
    """
    return {
        k: str(v)
        for k, v in attrs.items()
        if k not in _MAPPED_KEYS
        and k not in _CONTENT_DENYLIST
        and v is not None
        and v != ""
    }
