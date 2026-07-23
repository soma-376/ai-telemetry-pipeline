"""Compose normalization and enrichment into one event stream."""

from __future__ import annotations

from collections.abc import Iterator

from enrichment import enrich
from normalizer import normalize
from normalizer.model import Normalized


def process(doc: dict) -> Iterator[Normalized]:
    """Process one OTLP document and stream normalized, enriched events."""
    yield from enrich(normalize(doc))
