"""Convert one OTLP document into a stream of normalized events."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass, field

from diagnostics import (
    Diagnostics,
    DiagnosticReporter,
    NullReporter,
    Observation,
    TrackingAttrs,
)
from .common.call_id import pair_call_ids
from .common.context import IngestContext
from .model import Normalized
from .otlp.readers import read_all
from .adapters import claude_code, codex

_SOURCES = (claude_code, codex)


@dataclass(frozen=True)
class AdapterOutcome:
    """어댑터 매칭 결과와 정규화된 이벤트를 함께 보존한다."""

    adapter: str | None
    event_name: str | None
    event: Normalized | None
    accessed_keys: frozenset[str] = frozenset()
    mapping_results: dict[str, object] = field(default_factory=dict)
    mapping_reasons: dict[str, str] = field(default_factory=dict)


def _raw_record_id(rec: dict) -> str:
    payload = json.dumps(rec, sort_keys=True, ensure_ascii=False).encode()
    return "raw-" + hashlib.sha1(payload).hexdigest()[:16]


def _to_event(
    res_attrs: dict,
    rec: dict,
    attrs: dict,
    name: str,
    ctx: IngestContext,
) -> AdapterOutcome:
    for source in _SOURCES:
        event_name = source.match(
            res_attrs,
            rec,
            attrs,
            name,
            ctx.signal_type,
        )
        if event_name is not None:
            tracked = TrackingAttrs(attrs)
            event = source.to_event(
                res_attrs,
                rec,
                tracked,
                event_name,
                ctx,
            )
            return AdapterOutcome(
                adapter=source.ADAPTER,
                event_name=event_name,
                event=event,
                accessed_keys=frozenset(tracked.accessed),
                mapping_results=dict(tracked.mapping_results),
                mapping_reasons=dict(tracked.mapping_reasons),
            )

    return AdapterOutcome(
        adapter=None,
        event_name=name or None,
        event=None,
    )


def normalize(
    doc: dict,
    diagnostics: DiagnosticReporter | None = None,
) -> Iterator[Normalized]:
    """Normalize an OTLP push.

    The push is buffered until call IDs have been paired, then emitted as a
    stream for downstream enrichment.
    """
    events: list[Normalized] = []
    reporter = diagnostics or NullReporter()
    diagnostics_engine = Diagnostics(reporter)
    for res_attrs, rec, attrs, name, signal_type in read_all(doc):
        tenant_id = res_attrs.get("tenant.id")
        ctx = IngestContext(
            tenant_id=str(tenant_id) if tenant_id else None,
            raw_record_id=_raw_record_id(rec),
            signal_type=signal_type,
            diagnostics=reporter,
        )
        outcome = _to_event(res_attrs, rec, attrs, name, ctx)

        # 제품 namespace 밖의 레코드는 처리하지 않는다.
        if outcome.adapter is None:
            continue

        # 제품 namespace에 속한 모든 이벤트를 진단한다.
        diagnostics_engine.inspect(
            Observation(
                adapter=outcome.adapter,
                signal=signal_type.value,
                event_name=outcome.event_name,
                source_record_id=ctx.raw_record_id,
                normalized_event=outcome.event,
                source_values=attrs,
                accessed_keys=outcome.accessed_keys,
                mapping_results=outcome.mapping_results,
                mapping_reasons=outcome.mapping_reasons,
            )
        )

        # 정규화에 성공한 이벤트만 downstream으로 전달한다.
        if outcome.event is not None:
            events.append(outcome.event)

    pair_call_ids(events)
    yield from events
