"""Structured diagnostics for telemetry data quality."""

from .diagnostics import Diagnostics, Finding, Issue, Observation
from .model import DiagnosticEvent
from .reporter import DiagnosticReporter, NullReporter
from .jsonl_reporter import AggregatingReporter, JsonlReporter

__all__ = [
    "Diagnostics",
    "Finding",
    "Issue",
    "Observation",
    "DiagnosticEvent",
    "DiagnosticReporter",
    "AggregatingReporter",
    "JsonlReporter",
    "NullReporter",
]
