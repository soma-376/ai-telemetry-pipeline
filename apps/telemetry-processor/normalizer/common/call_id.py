#!/usr/bin/env python3
"""call_id 합성 + tool_decision↔tool_call 페어링.

tool_use_id 를 주는 툴(Claude Code)은 손대지 않는다. 안 주는 툴(Codex)만
어댑터가 합성하고(_ingest.call_id_inferred=True), 여기서 세션 내 시간순으로 잇는다.
"AI 제안 수락률" KPI 가 이 조인에 걸려 있다.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict

from ..model import LogKind, Normalized


def synth_call_id(session: str, seq: int | None, ts: float, tool_name: str) -> str:
    """tool_use_id 를 주지 않는 툴(Codex)용 합성 조인 키 — 레코드 단위 고유값.

    이 값만으로는 tool_decision 과 tool_result 가 이어지지 않는다.
    둘을 잇는 건 pair_call_ids() 의 사후 패스다.
    """
    return "syn-" + hashlib.sha1(
        f"{session}|{tool_name}|{seq}|{ts}".encode()
    ).hexdigest()[:12]


def pair_call_ids(events: list[Normalized]) -> None:
    """합성 call_id 를 쓰는 툴에서 tool_decision ↔ tool_call 을 같은 키로 잇는다.

    합성 키를 시각 버킷으로 만들면 승인과 실행이 몇 초 벌어질 때 서로 다른 키가
    되어 조인이 조용히 깨진다. 대신 세션 내 시간순으로 "같은 도구명의 직전 미결
    승인"과 짝지어 키를 물려준다.

    tool_use_id 를 주는 툴(Claude Code)은 call_id_inferred=False 라 손대지 않는다.
    """
    # tool_call/tool_decision 은 로그·스팬 둘 다에서 나온다(둘 다 call_id 를 가짐).
    # 메트릭은 call_id 가 없어 애초에 여기 안 들어온다.
    by_session: dict[str, list[Normalized]] = defaultdict(list)
    for e in events:
        if getattr(e, "call_id", None) is None:
            continue
        if e.type in (LogKind.TOOL_CALL, LogKind.TOOL_DECISION):
            by_session[e.envelope.session_id].append(e)

    for evs in by_session.values():
        pending: dict[str, str] = {}  # tool_name → 아직 실행과 이어지지 않은 결정의 call_id
        for e in sorted(
            evs, key=lambda x: (x.envelope.timestamp, getattr(x, "sequence", None) or 0)
        ):
            if not e.envelope._ingest.call_id_inferred:
                continue
            key = e.payload.tool_name or "?"
            if e.type is LogKind.TOOL_DECISION:
                pending[key] = e.call_id
            elif e.type is LogKind.TOOL_CALL:
                prior = pending.pop(key, None)
                if prior is not None:
                    e.call_id = prior
