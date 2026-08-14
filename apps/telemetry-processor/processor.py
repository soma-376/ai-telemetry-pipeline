"""Compose normalization and enrichment into one event stream."""

from __future__ import annotations

from diagnostics import DiagnosticReporter
from enrichment.enrich import enrich
from enrichment.model import Enriched
from normalizer import normalize


def process(
    doc: dict,
    diagnostics: DiagnosticReporter | None = None,
) -> list[Enriched]:
    """Process one OTLP document: normalize → enrich.

    저장은 하지 않는다(순수 변환) — ClickHouse 적재는 리시버가 담당한다.
    """
    return enrich(normalize(doc, diagnostics=diagnostics))
