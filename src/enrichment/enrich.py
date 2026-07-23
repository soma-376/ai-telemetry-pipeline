"""Apply enrichment while preserving the normalized event stream."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from normalizer.model import Normalized


def enrich(events: Iterable[Normalized]) -> Iterator[Normalized]:
    """Yield normalized events after applying enrichment rules.

    Enrichment rules can be added here without changing the stream contract.
    """
    yield from events
