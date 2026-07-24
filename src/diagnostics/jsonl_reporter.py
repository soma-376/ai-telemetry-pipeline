"""Thread-safe JSONL diagnostic reporter."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import TextIO

from .model import DiagnosticEvent

_TIME_FMT = "%Y-%m-%d %H:%M:%S"


class JsonlReporter:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._output: TextIO = path.open("a", encoding="utf-8", buffering=1)
        self._lock = threading.Lock()

    def report(self, event: DiagnosticEvent) -> None:
        data = event.to_dict()
        source_ts = data.pop("timestamp", None)
        # time(기록 시각) → issue_type 순으로 맨 앞에 배치, 나머지는 뒤에.
        ordered: dict = {
            "time": datetime.now().strftime(_TIME_FMT),
            "issue_type": data.pop("issue_type"),
        }
        if source_ts is not None:
            ordered["event_time"] = datetime.fromtimestamp(source_ts).strftime(
                _TIME_FMT
            )
        ordered.update(data)
        line = json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self._output.write(line + "\n")

    def close(self) -> None:
        self._output.close()
