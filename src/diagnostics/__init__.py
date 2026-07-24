"""Structured diagnostics for telemetry data quality."""

from .model import DiagnosticEvent
from .reporter import DiagnosticReporter, NullReporter
from .jsonl_reporter import JsonlReporter
from .tracking import TrackingAttrs

__all__ = [
    "DiagnosticEvent",
    "DiagnosticReporter",
    "JsonlReporter",
    "NullReporter",
    "TrackingAttrs",
]
