"""Reporter interface used by pipeline stages."""

from __future__ import annotations

from typing import Protocol

from .model import DiagnosticEvent


class DiagnosticReporter(Protocol):
    def report(self, event: DiagnosticEvent) -> None: ...


class NullReporter:
    def report(self, event: DiagnosticEvent) -> None:
        pass
