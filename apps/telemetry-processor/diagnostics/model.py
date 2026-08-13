"""Data model for structured diagnostic events."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Observation:
    """Facts supplied by a normalizer or adapter for diagnostics inspection."""

    adapter: str
    signal: str
    event_name: str | None
    source_record_id: str
    normalized_event: Any | None
    source_values: dict[str, Any] = field(default_factory=dict)
    accessed_keys: frozenset[str] = field(default_factory=frozenset)
    mapping_results: dict[str, Any] = field(default_factory=dict)
    mapping_reasons: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Issue:
    """An issue detected from an observation."""

    issue_type: str
    subject: str | None = None
    keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class Finding:
    """A detected issue classified with its specific reason."""

    issue: str
    reason: str
    subject: str | None = None
    keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiagnosticEvent:
    issue_type: str
    source_record_id: str
    signal: str
    adapter: str | None = None
    event_name: str | None = None
    target_field: str | None = None
    keys: tuple[str, ...] = ()
    source_values: dict[str, Any] = field(default_factory=dict)
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
