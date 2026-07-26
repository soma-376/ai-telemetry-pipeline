"""Request the current diagnostics snapshot and save it as timestamped JSON."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen

_KST = timezone(timedelta(hours=9))


def fetch_summary(url: str) -> list[dict[str, object]]:
    with urlopen(url, timeout=10) as response:  # noqa: S310 - explicit local URL
        document = json.load(response)
    if not isinstance(document, list):
        raise ValueError("diagnostics snapshot root must be a JSON array")
    return document


def write_summary(
    document: list[dict[str, object]], directory: Path
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(_KST).strftime("%Y%m%d-%H%M%S-KST")
    output = directory / f"diagnostics-summary-{stamp}.json"
    suffix = 1
    while output.exists():
        output = directory / f"diagnostics-summary-{stamp}-{suffix}.json"
        suffix += 1
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Save current diagnostics summary")
    parser.add_argument(
        "--url",
        default="http://localhost:8080/diagnostics",
        help="running processor diagnostics endpoint",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/diagnostics"),
    )
    args = parser.parse_args()
    output = write_summary(fetch_summary(args.url), args.output_dir)
    print(output)


if __name__ == "__main__":
    main()
