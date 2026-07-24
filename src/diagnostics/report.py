"""Aggregate structured diagnostic JSONL logs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def summarize(path: Path) -> list[dict[str, object]]:
    counts: Counter[tuple[str, str, str, str]] = Counter()
    with path.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            event = json.loads(line)
            key = (
                event.get("issue_type") or "-",
                event.get("adapter") or "-",
                event.get("event_name") or "-",
                event.get("target_field") or "-",
            )
            counts[key] += 1
    return [
        {
            "issue_type": key[0],
            "adapter": key[1],
            "event_name": key[2],
            "target_field": key[3],
            "count": count,
        }
        for key, count in counts.most_common()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize diagnostic JSONL")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.path), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
