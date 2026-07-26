"""Data model for structured diagnostic events."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class DiagnosticEvent:
    issue_type: str
    source_record_id: str
    signal: str
    adapter: str | None = None
    event_name: str | None = None
    source_values: dict[str, Any] = field(default_factory=dict)
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
