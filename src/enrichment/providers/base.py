"""EnrichmentProvider ABC (PLAN §6 P6).

외부 종속성(조직/GitHub/Jira/AI분석)을 하나의 인터페이스로 통일한다.
enrich(item, ctx) 는 annotations dict 를 반환한다(→ enrichment_json). 행을 드롭하지 않는다.
`order` 가 작을수록 먼저 적용된다(org=0 이 먼저, 이후 컬럼을 다른 provider 가 참조 가능).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from ..model import Enriched


class EnrichmentProvider(ABC):
    name: str = "base"
    order: int = 100  # org=0 이 먼저. 동일 order 는 name 정렬.

    @abstractmethod
    def enrich(self, item: Enriched, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """item 의 annotations dict 반환. no-op 은 {} 반환.

        org 레퍼런스 구현은 부수효과로 whitelist 컬럼을 채운다(그 외 provider 는 금지).
        """
        raise NotImplementedError
