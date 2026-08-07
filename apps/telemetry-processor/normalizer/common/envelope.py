#!/usr/bin/env python3
"""공통 envelope 조립 + 결정적 record_id 생성.

identity/client/context 추출은 툴마다 다르니 각 어댑터가 만들어 넘기고,
공통 필드(신규 필드 포함)는 여기서 일괄 세팅한다 →
어댑터가 새 필드를 빠뜨릴 수 없게 만드는 것이 목적.
"""
from __future__ import annotations

import hashlib

from .context import IngestContext
from ..model import (
    Client,
    Envelope,
    Identity,
    Ingest,
    Lifecycle,
    LlmCall,
    LlmResponse,
    MetricPoint,
    Normalized,
    NormalizedLog,
    NormalizedMetric,
    NormalizedSpan,
    Prompt,
    ToolCall,
    ToolDecision,
)

# record_id 해시에 쓰는 tenant 폴백. JSON에는 None을 싣지만 키 재료는 이 값으로
# 고정한다 — tenant 표기를 바꿨다고 과거 방출분의 키가 흔들리면 안 되기 때문.
_TENANT_KEY_FALLBACK = "(unknown)"


def build_envelope(
    *,
    client: Client,
    identity: Identity,
    session_id: str,
    ts: float,
    ingest: Ingest,
) -> Envelope:
    """세 신호가 공유하는 공통 봉투. 어댑터는 이걸 만들어 Normalized{Log,Span,Metric}
    에 끼우고, payload를 채운 뒤 finalize(ev)로 record_id를 확정한다."""
    return Envelope(
        identity=identity,
        client=client,
        timestamp=ts,
        session_id=session_id,
        _ingest=ingest,
    )


def build_ingest(
    *, ctx: IngestContext, adapter: str, adapter_version: int
) -> Ingest:
    return Ingest(
        adapter_version=adapter_version,
        signal=ctx.signal_type,
        source_record_id=ctx.raw_record_id,
    )


def _payload_discriminator(payload, *, call_id: str | None) -> str:
    """같은 (session, sequence, ts) 에 이벤트가 겹칠 때 키를 가르는 꼬리표.
    payload/조인키 내용에서만 뽑는다 — 재읽기해도 같아야 하므로."""
    p = payload
    if isinstance(p, LlmCall):
        t = p.tokens
        # request_id(CC only)가 있으면 섞어 유일성 강화. 없으면 None 그대로.
        return "|".join(
            str(x)
            for x in (
                p.model,
                t.input,
                t.output,
                t.cache_read,
                t.cache_create,
                p.request_id,
            )
        )
    if isinstance(p, LlmResponse):
        return f"{p.model}|{p.response_length}|{p.request_id}"
    if isinstance(p, ToolCall):
        return f"{call_id}|{p.success}"
    if isinstance(p, ToolDecision):
        return (
            f"{call_id}|{p.decision.value}|"
            f"{p.decided_by.value}|{p.scope.value}"
        )
    if isinstance(p, Prompt):
        return f"{p.length}|{p.command_name}"
    if isinstance(p, Lifecycle):
        return str(p.kind)
    if isinstance(p, MetricPoint):
        dimensions = "|".join(f"{k}={v}" for k, v in sorted(p.attrs.items()))
        return f"{p.name}|{p.value}|{p.count}|{p.sum}|{dimensions}"
    return "-"


def _idem_fields(ev: Normalized) -> tuple[str, str, str]:
    """타입별로 (sequence|-, type.value, discriminator) 를 뽑는다.
    스팬은 sequence 가 없어 span_id 로 유일성을 보강한다."""
    if isinstance(ev, NormalizedMetric):
        disc = _payload_discriminator(ev.point, call_id=None)
        return "-", "metric", disc
    disc = _payload_discriminator(ev.payload, call_id=ev.call_id)
    if isinstance(ev, NormalizedSpan):
        # 스팬은 event.sequence 가 없어 (session, ts) 만으로 겹칠 수 있다.
        # span_id 는 전역 유일하므로 이걸로 가른다.
        return "-", ev.type.value, f"{disc}|{ev.span_id}"
    seq = ev.sequence if ev.sequence is not None else "-"
    return str(seq), ev.type.value, disc


def finalize(ev: Normalized) -> Normalized:
    """payload 확정 후 envelope.record_id를 결정적으로 계산한다.

    입력은 전부 원시 레코드에서 파생된 값뿐 — 벽시계·난수·처리순서 없음.
    → 같은 raw 를 다시 읽으면 반드시 같은 키. 5분 주기/replay 가 멱등해진다.

    ⚠️ sequence 가 없고(예: Gemini 미확인) 같은 ts 에 내용까지 동일한 두 레코드는
       한 키로 합쳐져 과소집계될 수 있다. Gemini 실데이터로 유무 확인 후 재검토.

    call_id 페어링(join.pair_call_ids) 이전에, 각 어댑터가 payload 를 채운 직후
    호출한다. 그래야 키가 "그 레코드 자체"를 가리키고 이후 mutation 에 안 흔들린다.
    """
    env = ev.envelope
    seq, type_val, disc = _idem_fields(ev)
    nanos = int(round(env.timestamp * 1e9))
    parts = "|".join(
        str(x)
        for x in (
            env.identity.tenant_id or _TENANT_KEY_FALLBACK,
            env.client.product,
            env.session_id,
            seq,
            nanos,
            type_val,
            disc,
        )
    )
    env.record_id = "idem-" + hashlib.sha1(parts.encode()).hexdigest()[:16]
    return ev
