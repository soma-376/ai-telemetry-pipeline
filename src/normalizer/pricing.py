#!/usr/bin/env python3
"""
모델별 토큰 단가 표 — cost_usd 를 직접 주지 않는 툴(예: Codex)의 비용 추정 및
캐시 절감액 계산에 사용.

⚠️ 아래 단가는 자리표시자(placeholder)다. 실제 청구서/공식 가격표로 반드시 갱신할 것.
단위: USD per 1M tokens.
"""
from __future__ import annotations

# model 부분 문자열(소문자) → (input, output, cache_read, cache_create) per 1M tokens
# 부분 문자열 매칭이므로 "gpt-5-codex", "gpt-5-codex-2026-.." 등을 함께 커버.
_PRICE_PER_MTOK: dict[str, tuple[float, float, float, float]] = {
    # --- OpenAI Codex 계열 (⚠️ 확인 필요) ---
    "gpt-5-codex": (1.25, 10.0, 0.125, 1.25),
    "gpt-5":       (1.25, 10.0, 0.125, 1.25),
    "o4-mini":     (1.10, 4.40, 0.275, 1.10),
    "codex":       (1.25, 10.0, 0.125, 1.25),
    # --- Anthropic Claude 계열 (참고용; Claude는 보통 cost_usd 직접 제공) ---
    "opus":        (15.0, 75.0, 1.50, 18.75),
    "sonnet":      (3.0,  15.0, 0.30, 3.75),
    "haiku":       (0.80, 4.0,  0.08, 1.0),
}

_DEFAULT = (1.25, 10.0, 0.125, 1.25)   # 미상 모델 fallback


def _rates(model: str | None) -> tuple[float, float, float, float]:
    if model:
        m = model.lower()
        for key, rates in _PRICE_PER_MTOK.items():
            if key in m:
                return rates
    return _DEFAULT


def estimate_cost(model: str | None, tok_input: int, tok_output: int,
                  tok_cache_read: int, tok_cache_create: int) -> float:
    """단가표로 비용(USD) 추정. cost_usd 가 없을 때만 사용."""
    ri, ro, rcr, rcc = _rates(model)
    return (tok_input * ri + tok_output * ro
            + tok_cache_read * rcr + tok_cache_create * rcc) / 1_000_000


def cache_savings(model: str | None, tok_cache_read: int) -> float:
    """캐시 히트로 절감한 추정액(USD): (input 단가 - cache_read 단가) × cache_read 토큰."""
    ri, _ro, rcr, _rcc = _rates(model)
    return max(0.0, (ri - rcr)) * tok_cache_read / 1_000_000
