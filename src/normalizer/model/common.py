from __future__ import annotations

from dataclasses import dataclass, field

from .enums import (
    Decision,
    DecisionScope,
    DecisionSource,
    SignalType,
    Surface,
    ToolAction,
    ToolKind,
    ValueSource,
)

SCHEMA_VERSION = 1


@dataclass
class Identity:
    tenant_id: str | None = None
    user_id: str | None = None
    vendor_email: str | None = None
    vendor_account_id: str | None = None


@dataclass
class Client:
    product: str
    surface: Surface = Surface.UNKNOWN
    version: str | None = None


@dataclass
class Ingest:
    adapter_version: int = 0
    signal: SignalType = SignalType.LOG
    source_record_id: str | None = None
    call_id_inferred: bool = False
    raw_value: str | None = None
    raw: dict[str, str] = field(default_factory=dict)


@dataclass
class Envelope:
    identity: Identity
    client: Client
    timestamp: float
    session_id: str
    schema_version: int = SCHEMA_VERSION
    record_id: str = ""
    _ingest: Ingest = field(default_factory=Ingest)


@dataclass
class Tokens:
    input: int | None = None
    output: int | None = None
    cache_read: int | None = None
    cache_create: int | None = None
    reasoning: int | None = None
    tool: int | None = None
    total_reported: int | None = None

    @property
    def billable(self) -> int:
        return sum(
            value or 0
            for value in (self.input, self.output, self.cache_read, self.cache_create)
        )

    def reconciles(self) -> bool | None:
        if self.total_reported is None:
            return None
        return self.total_reported == self.billable


@dataclass
class LlmCall:
    """LLM 호출. 로그(api_request)·스팬(llm_request) 공유.
    스팬에선 tokens/cost/source 를 안 채운다(이중계산 회피) — 필드는 공유하되 값만 비운다."""

    model: str | None = None
    tokens: Tokens = field(default_factory=Tokens)
    cost_usd: float | None = None
    cost_source: ValueSource = ValueSource.ESTIMATED
    source: str | None = None
    duration_ms: int | None = None
    ttft_ms: int | None = None
    stop_reason: str | None = None
    attempt: int | None = None
    request_id: str | None = None
    error_type: str | None = None
    status_code: int | None = None


@dataclass
class ToolCall:
    tool_name: str | None = None
    tool_kind: ToolKind = ToolKind.UNKNOWN
    action: ToolAction = ToolAction.OTHER
    files: list[str] = field(default_factory=list)
    command: str | None = None
    success: bool | None = None
    error_type: str | None = None
    duration_ms: int | None = None
    mcp_server: str | None = None
    agent_id: str | None = None
    parent_agent_id: str | None = None


@dataclass
class ToolDecision:
    decision: Decision = Decision.UNKNOWN
    decided_by: DecisionSource = DecisionSource.UNKNOWN
    scope: DecisionScope = DecisionScope.UNKNOWN
    blocked_on_user_ms: int | None = None
    tool_name: str | None = None


@dataclass
class Lifecycle:
    kind: str
    start_type: str | None = None
    active_time_sec: int | None = None
    turn_count: int | None = None
    tokens_before: int | None = None
    tokens_after: int | None = None
    attrs: dict[str, str] = field(default_factory=dict)
