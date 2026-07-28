"""JSONL 로더: 한 줄 → Record. 깨진 라인은 크래시가 아니라 알람 + 파킹(PLAN §108).

파킹 원칙: 어떤 라인도 조용히 버리지 않는다. 파싱 실패/구조 이상은 parked에
사유와 함께 남기고 카운트를 올린다. 빈 줄만 무시(에러 아님).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

from .contract import Record

Alarm = Callable[[str], None]


def _stderr_alarm(msg: str) -> None:
    sys.stderr.write("[enricher.io_jsonl][ALARM] %s\n" % msg)


@dataclass
class ParkedLine:
    line_no: int
    raw: str
    error: str


@dataclass
class LoadResult:
    records: List[Record] = field(default_factory=list)
    parked: List[ParkedLine] = field(default_factory=list)

    @property
    def parked_count(self) -> int:
        return len(self.parked)

    @property
    def record_count(self) -> int:
        return len(self.records)


def load_lines(lines: Iterable[str], alarm: Optional[Alarm] = None) -> LoadResult:
    """반복 가능한 텍스트 라인들을 로드. 예외를 밖으로 던지지 않는다."""
    if alarm is None:
        alarm = _stderr_alarm
    result = LoadResult()
    for i, line in enumerate(lines, start=1):
        raw = line.rstrip("\n")
        if raw.strip() == "":
            continue  # 빈 줄: 무시(파킹 아님)
        try:
            obj = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as e:
            alarm("line %d 파싱 실패: %s" % (i, e))
            result.parked.append(ParkedLine(i, raw, "json_decode: %s" % e))
            continue
        if not isinstance(obj, dict):
            alarm("line %d 최상위가 object 아님: %s" % (i, type(obj).__name__))
            result.parked.append(ParkedLine(i, raw, "not_object: %s" % type(obj).__name__))
            continue
        try:
            rec = Record.from_dict(obj, raw_line=raw)
        except Exception as e:  # 구조 이상(예: identity가 dict 아님) → 크래시 대신 파킹
            alarm("line %d 구조 이상: %s" % (i, e))
            result.parked.append(ParkedLine(i, raw, "structure: %s" % e))
            continue
        result.records.append(rec)
    return result


def load_file(path: str, alarm: Optional[Alarm] = None) -> LoadResult:
    with open(path, "r", encoding="utf-8") as f:
        return load_lines(f, alarm=alarm)
