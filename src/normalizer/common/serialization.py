#!/usr/bin/env python3
"""Normalized(Log|Span|Metric) JSON serialization."""
from __future__ import annotations

import json
from dataclasses import asdict

from ..model import Normalized


def event_to_json(event: Normalized) -> str:
    """Normalized 이벤트를 한 줄 JSON으로 직렬화한다(envelope 중첩)."""
    return json.dumps(
        asdict(event),
        ensure_ascii=False,
        separators=(",", ":"),
    )
