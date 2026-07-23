#!/usr/bin/env python3
"""툴별 원시 OTLP를 신호별 Normalized{Log,Span,Metric}로 변환한다.

셋은 공통 Envelope(identity / client / session_id / timestamp / _ingest)를 품고,
신호별 상관 필드(turn_id·span_id 등)와 payload 만 각자 갖는다.
_ingest는 배관 정보이므로 KPI가 읽지 않는다. 자세한 건 model/event.py 참조.

다운스트림은 Normalized 위에서만 동작하므로, 새 CLI 툴을 붙일 때는
adapters/ 에 모듈 하나만 추가하면 된다.

패키지 구성:
  model/     공통 스키마(enums + 메시지). 순수 데이터, 로직 없음.
  otlp/      OTLP 파싱 공용 유틸(툴 무관).
  envelope   공통 Envelope 조립 + 결정적 record_id.
  join       call_id 합성·페어링.
  adapters/  소스별 어댑터(claude_code, codex, …). 새 소스는 여기.
  normalize  normalize(push 배치 1건) + 수집 컨텍스트 주입.

⚠️ 규칙 두 가지 (어기면 조용히 틀린 숫자가 나온다):
  1. 값이 없으면 0 이 아니라 None. "0건"과 "측정 불가"는 다른 사실이다.
  2. Tokens.reasoning / Tokens.tool 은 output 의 부분집합일 수 있다. 합산 금지.
     합산은 Tokens.billable (input+output+cache_read+cache_create) 로만.
"""
from __future__ import annotations

from .normalize import normalize
from .model import (
    SCHEMA_VERSION,
    Artifact,
    Client,
    Decision,
    DecisionScope,
    DecisionSource,
    Envelope,
    Identity,
    Ingest,
    LogKind,
    SpanKind,
    Lifecycle,
    LlmCall,
    LlmResponse,
    LogPayload,
    MetricPoint,
    Normalized,
    NormalizedLog,
    NormalizedMetric,
    NormalizedSpan,
    Prompt,
    SignalType,
    SpanPayload,
    Surface,
    Tokens,
    ToolAction,
    ToolCall,
    ToolDecision,
    ToolKind,
    ValueSource,
)

__all__ = [
    "normalize",
    "SCHEMA_VERSION",
    # enums
    "Surface",
    "SignalType",
    "ValueSource",
    "LogKind",
    "SpanKind",
    "ToolKind",
    "ToolAction",
    "Decision",
    "DecisionSource",
    "DecisionScope",
    # messages
    "Identity",
    "Client",
    "Envelope",
    "Ingest",
    "Tokens",
    "Prompt",
    "LlmCall",
    "LlmResponse",
    "ToolCall",
    "ToolDecision",
    "Artifact",
    "Lifecycle",
    "MetricPoint",
    "LogPayload",
    "SpanPayload",
    "NormalizedLog",
    "NormalizedSpan",
    "NormalizedMetric",
    "Normalized",
]
