#!/usr/bin/env python3
"""OTLP 속성 추출 유틸 — 툴 무관 공용.

⚠️ 규칙: 값이 없으면 0 이 아니라 None. "0건"과 "측정 불가"는 다른 사실이다.
"""
from __future__ import annotations

import json


def _attr_value(v: dict):
    if "stringValue" in v:
        return v["stringValue"]
    if "intValue" in v:
        try:
            return int(v["intValue"])
        except (TypeError, ValueError):
            return v["intValue"]
    if "doubleValue" in v:
        return v["doubleValue"]
    if "boolValue" in v:
        return v["boolValue"]
    return None


def _opt_int(attrs: dict, *keys: str) -> int | None:
    """없으면 None. 0 으로 대체하지 않는다 — unset 과 0 은 다른 사실이다."""
    for k in keys:
        v = attrs.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            return int(v)
        if isinstance(v, str) and v.strip().isdigit():
            return int(v)
    return None


def _opt_float(attrs: dict, *keys: str) -> float | None:
    for k in keys:
        v = attrs.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str) and v:
            try:
                return float(v)
            except ValueError:
                continue
    return None


def _opt_str(*sources: dict, keys: tuple[str, ...]) -> str | None:
    for src in sources:
        for k in keys:
            v = src.get(k)
            if isinstance(v, str) and v:
                return v
    return None


def _opt_bool(attrs: dict, *keys: str) -> bool | None:
    for k in keys:
        v = attrs.get(k)
        if isinstance(v, bool):
            return v
        if isinstance(v, str) and v.lower() in ("true", "false"):
            return v.lower() == "true"
    return None


# ---------------------------------------------------------------------------
# 진단 매핑 축약형.
#
# attrs.map(target, lambda: _opt_X(attrs, ...)) 의 보일러플레이트를 없앤다 —
# 필드당 새 정보는 (타깃 이름, required 여부) 뿐이므로 한 줄이면 충분하다.
# attrs 는 TrackingAttrs 여야 한다(덕타이핑 — 순환 의존을 피하려고 import 안 함).


def _map_str(
    attrs: dict,
    target: str,
    *keys: str,
    res_attrs: dict | None = None,
    required: bool = True,
) -> str | None:
    """res_attrs 를 주면 attrs 미스 시 리소스 속성까지 뒤진다(세션 ID 등)."""
    sources = (attrs,) if res_attrs is None else (attrs, res_attrs)
    return attrs.map(
        target, lambda: _opt_str(*sources, keys=keys), required=required
    )


def _map_int(
    attrs: dict, target: str, *keys: str, required: bool = True
) -> int | None:
    return attrs.map(
        target, lambda: _opt_int(attrs, *keys), required=required
    )


def _map_float(
    attrs: dict, target: str, *keys: str, required: bool = True
) -> float | None:
    return attrs.map(
        target, lambda: _opt_float(attrs, *keys), required=required
    )


def _map_bool(
    attrs: dict, target: str, *keys: str, required: bool = True
) -> bool | None:
    return attrs.map(
        target, lambda: _opt_bool(attrs, *keys), required=required
    )


def _merge_json_attrs(attrs: dict, *keys: str) -> dict:
    """JSON 문자열로 담긴 도구 인자 속성들을 dict 로 병합."""
    out: dict = {}
    for k in keys:
        raw = attrs.get(k)
        if isinstance(raw, str) and raw.strip().startswith("{"):
            try:
                out.update(json.loads(raw))
            except json.JSONDecodeError:
                pass
    return out
