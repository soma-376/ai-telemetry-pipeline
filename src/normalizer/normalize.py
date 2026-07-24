"""Convert one OTLP document into a stream of normalized events."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator

from diagnostics import (
    DiagnosticEvent,
    DiagnosticReporter,
    NullReporter,
    TrackingAttrs,
)
from diagnostics.checks import report_unmapped_fields
from .common.call_id import pair_call_ids
from .common.context import IngestContext
from .model import Normalized
from .otlp.readers import read_all
from .adapters import claude_code, codex

_SOURCES = (claude_code, codex)


def _raw_record_id(rec: dict) -> str:
    payload = json.dumps(rec, sort_keys=True, ensure_ascii=False).encode()
    return "raw-" + hashlib.sha1(payload).hexdigest()[:16]


def _to_event(
    res_attrs: dict,
    rec: dict,
    attrs: dict,
    name: str,
    ctx: IngestContext,
) -> Normalized | None:
    for source in _SOURCES:
        event_name = source.match(
            res_attrs,
            rec,
            attrs,
            name,
            ctx.signal_type,
        )
        if event_name is not None:
            # in-scope 확정. 이 순간부터만 추적 dict 로 감싸 안 읽은 키를 잡는다.
            tracked = TrackingAttrs(attrs)
            event = source.to_event(res_attrs, rec, tracked, event_name, ctx)
            report_unmapped_fields(
                ctx.diagnostics,
                adapter=source.ADAPTER,
                event_name=event_name,
                source_record_id=ctx.raw_record_id,
                signal=ctx.signal_type.value,
                tracked=tracked,
            )
            return event
    return None


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

    for res_attrs, rec, attrs, name, signal_type in read_all(doc):
        tenant_id = res_attrs.get("tenant.id")
        ctx = IngestContext(
            tenant_id=str(tenant_id) if tenant_id else None,
            raw_record_id=_raw_record_id(rec),
            signal_type=signal_type,
            diagnostics=reporter,
        )
        event = _to_event(res_attrs, rec, attrs, name, ctx)
        if event is not None:
            events.append(event)
        else:
            reporter.report(
                DiagnosticEvent(
                    issue_type="unknown_event",
                    event_name=name or None,
                    source_record_id=ctx.raw_record_id,
                    signal=signal_type.value,
                    source_values=attrs,
                    message="No adapter matched the OTLP record",
                )
            )

    pair_call_ids(events)
    yield from events
