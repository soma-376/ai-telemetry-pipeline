"""Jira provider — no-op 스텁 (PLAN §4 범위 밖, §3.2.3).

인터페이스만 제공하고 빈 dict 를 반환한다(이번 범위 구현 X).
"""
from __future__ import annotations

from typing import Any, Dict

from ..model import Enriched
from .base import EnrichmentProvider


class JiraProvider(EnrichmentProvider):
    name = "jira"

    def enrich(self, item: Enriched, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return {}  # no-op
