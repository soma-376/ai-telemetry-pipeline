#!/usr/bin/env python3
"""수집 시점에 콜렉터/로더가 스탬프하는 툴 무관 값들의 운반체.

어댑터 시그니처에 tenant_id/raw_record_id/signal_type을 낱개로 흘리지 않고
이 하나로 묶어 넘긴다. 클라이언트가 주장한 값이 아니라 신뢰 가능한 출처의 값이다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from diagnostics import DiagnosticReporter, NullReporter
from ..model import SignalType


@dataclass
class IngestContext:
    tenant_id: str | None  # 콜렉터가 인증 자격증명에서 스탬프. 없으면 None
    raw_record_id: str  # 원본 레코드 참조 ID 또는 payload hash
    signal_type: SignalType = SignalType.LOG
    diagnostics: DiagnosticReporter = field(default_factory=NullReporter)
