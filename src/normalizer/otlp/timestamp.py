#!/usr/bin/env python3
"""타임스탬프 파싱 — ISO8601 문자열 / timeUnixNano 를 epoch seconds 로 통일."""
from __future__ import annotations

from datetime import datetime


def _parse_ts(rec: dict, attrs: dict) -> float:
    ts = attrs.get("event.timestamp")
    if isinstance(ts, str) and ts:
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    nano = rec.get("timeUnixNano") or rec.get("observedTimeUnixNano")
    if nano:
        try:
            return int(nano) / 1e9
        except (TypeError, ValueError):
            pass
    return 0.0
