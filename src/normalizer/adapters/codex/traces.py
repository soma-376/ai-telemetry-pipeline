#!/usr/bin/env python3
"""Codex trace adapter — 스텁(미구현).

Codex 스팬을 NormalizedSpan으로 매핑할 자리.
현재 실데이터 없음 → 미착수.
"""
from __future__ import annotations

from ...common.context import IngestContext
from ...model import NormalizedSpan


def to_event(
    res_attrs: dict, rec: dict, attrs: dict, name: str, ctx: IngestContext
) -> NormalizedSpan | None:
    return None  # TODO: traces 매핑
