"""결정론적 합성 Adaptor 데이터셋 생성기 (PLAN §6 P2).

§결정론 상수의 4명 사원에 대해 log/metric 이벤트를 고정 시드로 emit 한다.
동일 시드 2회 실행 시 **바이트 동일**하며, 총 레코드 수는 EXPECTED_COUNT 로 고정.

시나리오 커버리지(각 최소 1건):
  ① 정상        : emp-001, emp-003 (등록 사원)
  ② 미등록      : emp-404 (RDS에 없음)
  ③ 이동 전/후  : emp-002 @ 2026-05-15(backend) / 2026-06-15(platform)
  ④ 2개 회사    : acme / globex
  ⑤ log+metric  : 두 신호 모두

출력은 P1 계약(contract.Record) 형태의 JSONL. 키 정렬·고정 separators 로
직렬화해 결정론을 보장한다(원본은 io_jsonl 이 raw_line 으로 verbatim 보존).
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

JSON = Dict[str, Any]

FIXED_SEED = 20260601
EXPECTED_COUNT = 8  # 아래 _PLAN 의 레코드 수와 반드시 일치(문서화된 기대값)

MOVE_DATE = "2026-06-01"  # emp-002 backend→platform 이동일(참고용 상수)


def _epoch(y: int, m: int, d: int, hh: int = 12) -> float:
    """UTC 정오 기준 epoch 초(결정론). as-of 는 이 날짜(UTC)로 해석된다."""
    return datetime(y, m, d, hh, 0, 0, tzinfo=timezone.utc).timestamp()


# (emp_id, tenant, actor/email, signal, (y,m,d), event_id) — 생성 순서 고정
_PLAN = [
    ("emp-001", "acme",   "alice@acme.test", "log",    (2026, 5, 10), "evt-0001"),
    ("emp-001", "acme",   "alice@acme.test", "metric", (2026, 5, 10), "evt-0002"),
    ("emp-002", "acme",   "bob@acme.test",   "log",    (2026, 5, 15), "evt-0003"),  # 이동 전
    ("emp-002", "acme",   "bob@acme.test",   "log",    (2026, 6, 15), "evt-0004"),  # 이동 후
    ("emp-002", "acme",   "bob@acme.test",   "metric", (2026, 6, 15), "evt-0005"),
    ("emp-003", "globex", "carol@globex.test", "log",    (2026, 5, 20), "evt-0006"),
    ("emp-003", "globex", "carol@globex.test", "metric", (2026, 5, 20), "evt-0007"),
    ("emp-404", "acme",   "dave@acme.test",  "log",    (2026, 5, 25), "evt-0008"),  # 미등록
]


def _envelope(tenant, actor, emp_id, ts, event_id, signal, sess) -> JSON:
    return {
        "identity": {
            "tenant_id": tenant,
            "actor_id": actor,
            "email": actor,
            "internal_employee_id": emp_id,
        },
        "client": {"product": "claude_code"},
        "timestamp": ts,
        "session_id": sess,
        "event_id": event_id,
        "_ingest": {"signal": signal},
    }


def generate() -> List[JSON]:
    """결정론적으로 레코드 dict 리스트 생성. 매 호출 동일 결과."""
    rng = random.Random(FIXED_SEED)
    records: List[JSON] = []
    for idx, (emp_id, tenant, actor, signal, (y, m, d), eid) in enumerate(_PLAN, 1):
        ts = _epoch(y, m, d)
        sess = "sess-%s-%02d" % (emp_id, idx)
        env = _envelope(tenant, actor, emp_id, ts, eid, signal, sess)
        if signal == "log":
            rec = {
                "envelope": env,
                "type": "llm_call",
                "payload": {
                    "model": "claude-3-5-sonnet",
                    "cost_usd": round(rng.uniform(0.001, 0.05), 5),
                    "tokens": rng.randint(100, 2000),
                },
            }
        else:  # metric
            rec = {
                "envelope": env,
                "type": "metric",
                "point": {"name": "tokens_total", "value": rng.randint(1000, 5000)},
            }
        records.append(rec)
    return records


def to_jsonl(records: List[JSON]) -> str:
    """결정론적 JSONL 직렬화: 키 정렬 + 고정 separators + 후행 개행."""
    lines = [
        json.dumps(r, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        for r in records
    ]
    return "\n".join(lines) + "\n"


def main(argv: List[str]) -> int:
    text = to_jsonl(generate())
    if len(argv) >= 2 and argv[1] not in ("-", "/dev/stdout"):
        with open(argv[1], "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
