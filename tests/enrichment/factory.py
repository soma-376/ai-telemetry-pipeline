"""테스트용 Normalized 이벤트 팩토리.

어댑터 경로와 동일하게 build_envelope + finalize 를 태워 record_id 스탬프까지
재현한다(수제 dict 금지 — 실제 스키마 계약으로 검증).
"""
from __future__ import annotations

from normalizer.common.envelope import build_envelope, finalize
from normalizer.model import (
    Client,
    Identity,
    Ingest,
    LogKind,
    NormalizedLog,
    Prompt,
    SignalType,
    Surface,
)


def make_log(
    *,
    user_id: str | None = None,
    tenant_id: str | None = "acme",
    ts: float = 1_782_900_000.0,  # 2026-07-01 근방(UTC)
    session_id: str = "sess-1",
    sequence: int = 1,
    source_record_id: str | None = "raw-1",
) -> NormalizedLog:
    envelope = build_envelope(
        client=Client(product="claude_code", surface=Surface.CLI),
        identity=Identity(tenant_id=tenant_id, user_id=user_id),
        session_id=session_id,
        ts=ts,
        ingest=Ingest(
            adapter_version=2,
            signal=SignalType.LOG,
            source_record_id=source_record_id,
        ),
    )
    ev = NormalizedLog(
        envelope=envelope,
        type=LogKind.USER_PROMPT,
        payload=Prompt(length=5),
        sequence=sequence,
    )
    return finalize(ev)
