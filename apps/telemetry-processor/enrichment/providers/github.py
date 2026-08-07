"""GitHub provider — no-op 스텁 (PLAN §4 범위 밖, §3.2.3).

실제 GitHub 연동은 이번 슬라이스 범위가 아니다. 인터페이스만 제공하고 빈 dict 를 반환한다.
새 스텁을 추가하는 것만으로 registry 에 자동 등록됨을 보이는 예시이기도 하다.
"""
from __future__ import annotations

from typing import Any, Dict

from ..model import Enriched
from .base import EnrichmentProvider


class GithubProvider(EnrichmentProvider):
    name = "github"

    def enrich(self, item: Enriched, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return {}  # no-op
