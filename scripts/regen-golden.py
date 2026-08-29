#!/usr/bin/env python3
"""golden fixture 재생성 — `*.otlp.jsonl` 입력을 `*.normalized.jsonl` 기대출력으로 굽는다.

## 왜 있나

Kotlin 이식(PROJ-74)이 동작 동일성을 기계적으로 검증할 수 있게, 현행 Python
normalizer 의 출력을 **언어 중립 JSON** 으로 고정한다. 입력과 기대출력을 나란히
커밋하므로 Kotlin 테스트가 같은 파일 쌍을 읽어 그대로 대조할 수 있다.

## 파일 형식 (Kotlin 이식이 읽어야 하는 계약)

- 입력  `<name>.otlp.jsonl` — 한 줄이 OTLP 문서 하나(`{"resourceLogs": [...]}`).
- 기대  `<name>.normalized.jsonl` — 한 줄이 정규화 이벤트 하나. 형태는

      {"document_index": 0, "event_index": 0, "event": { ...Normalized... }}

  `document_index` 는 이벤트를 만든 입력 줄 번호(0-base), `event_index` 는 그
  문서 안에서 `normalize()` 가 방출한 순서다. 문서 하나가 0건을 낼 수도 있다.
  `event` 는 `serialization.event_to_json()` 과 같은 값이다 — ClickHouse
  `raw_json` 에 실제로 들어가는 그 형태(envelope 중첩, enum 은 값 문자열).

  줄 순서와 `event` 안의 키 순서는 재현되지만, 대조는 **JSON 값 동등성** 으로
  하면 된다(키 순서에 기대지 마라).

## 결정성 전제

`envelope.record_id` 는 `finalize()` 가 입력 파생값만으로 만든다 — 벽시계도
난수도 처리순서도 섞이지 않는다. 그래서 이 파일이 golden 으로 성립한다.
다시 구웠는데 diff 가 난다면 **정규화 동작이 바뀐 것이다.** 검토 없이 커밋하지 마라.

## 사용법

    scripts/test-processor.sh ../../scripts/regen-golden.py   # 는 동작하지 않는다
    docker run --rm -v "$PWD:/w" -w /w/apps/telemetry-processor python:3.13-slim \
        python /w/scripts/regen-golden.py

인자 없이 돌리면 `tests/fixtures/` 아래 모든 `*.otlp.jsonl` 을 다시 굽는다.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1] / "apps" / "telemetry-processor"
sys.path.insert(0, str(_APP_ROOT))

from normalizer import normalize  # noqa: E402

FIXTURE_ROOT = _APP_ROOT / "tests" / "fixtures"


def golden_lines(otlp_path: Path) -> list[str]:
    """입력 문서를 순서대로 정규화해 golden 줄들을 만든다."""
    lines: list[str] = []
    with otlp_path.open(encoding="utf-8") as handle:
        for document_index, raw in enumerate(handle):
            raw = raw.strip()
            if not raw:
                continue
            # 제너레이터다 — list() 로 소비해야 pair_call_ids 까지 끝난 상태가 된다.
            events = list(normalize(json.loads(raw)))
            for event_index, event in enumerate(events):
                lines.append(
                    json.dumps(
                        {
                            "document_index": document_index,
                            "event_index": event_index,
                            "event": asdict(event),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )
    return lines


def regenerate(otlp_path: Path) -> Path:
    golden_path = otlp_path.with_name(
        otlp_path.name.replace(".otlp.jsonl", ".normalized.jsonl")
    )
    lines = golden_lines(otlp_path)
    golden_path.write_text(
        "".join(line + "\n" for line in lines), encoding="utf-8"
    )
    print(f"{otlp_path.name}: {len(lines)} events -> {golden_path.name}")
    return golden_path


def main() -> None:
    targets = (
        [Path(arg) for arg in sys.argv[1:]]
        if len(sys.argv) > 1
        else sorted(FIXTURE_ROOT.rglob("*.otlp.jsonl"))
    )
    if not targets:
        raise SystemExit("no *.otlp.jsonl fixtures found")
    for target in targets:
        regenerate(target)


if __name__ == "__main__":
    main()
