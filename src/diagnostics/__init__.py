"""Structured diagnostics for telemetry data quality."""

from .engine import Diagnostics
from .model import DiagnosticEvent, Finding, Issue, Observation
from .reporter import DiagnosticReporter, NullReporter
from .aggregating_reporter import AggregatingReporter
from .tracking import TrackingAttrs

__all__ = [
    "Diagnostics",
    "Finding",
    "Issue",
    "Observation",
    "DiagnosticEvent",
    "DiagnosticReporter",
    "AggregatingReporter",
    "NullReporter",
    "TrackingAttrs",
]
