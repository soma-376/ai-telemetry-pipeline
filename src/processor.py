"""Compose normalization and enrichment into one event stream."""

from __future__ import annotations

from collections.abc import Iterator

from diagnostics import DiagnosticReporter
from enrichment.enrich import enrich
from normalizer import normalize
from normalizer.model import Normalized


def process(
    doc: dict,
    diagnostics: DiagnosticReporter | None = None,
) -> Iterator[Normalized]:
    """Process one OTLP document and stream normalized, enriched events."""
    yield from enrich(normalize(doc, diagnostics=diagnostics))
