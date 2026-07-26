"""Structured diagnostics for telemetry data quality."""

from .diagnostics import Diagnostics
from .model import DiagnosticEvent, Finding, Issue, Observation
from .reporter import DiagnosticReporter, NullReporter
from .jsonl_reporter import AggregatingReporter, JsonlReporter
from .tracking import TrackingAttrs

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
    "TrackingAttrs",
]
