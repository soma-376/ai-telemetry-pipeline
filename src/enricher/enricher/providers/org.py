"""org provider — P5(as-of 조직 매핑)를 provider 인터페이스로 감싼 레퍼런스 구현.

ctx["org_of"] (as-of 해석기)를 사용해 whitelist 컬럼(company_id/department_*/employee_name)을
채운다. 조직 데이터는 공통 컬럼으로 승격되므로 annotations 는 비운다({}).
"""
from __future__ import annotations

from typing import Any, Dict

from ..enrich_org import enrich_org_item
from ..model import Enriched
from .base import EnrichmentProvider


class OrgProvider(EnrichmentProvider):
    name = "org"
    order = 0  # 코어 org 매핑을 먼저 적용

    def enrich(self, item: Enriched, ctx: Dict[str, Any]) -> Dict[str, Any]:
        org_of = ctx["org_of"]
        enrich_org_item(item, org_of)  # whitelist 컬럼 세팅(side effect)
        return {}  # org 산출물은 컬럼으로만(enrichment_json 승격 금지)
