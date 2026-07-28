"""엔리치먼트 파이프라인을 흐르는 공통 컨테이너.

원본 `Record` 는 불변으로 감싸 두고(raw 불변, PLAN §8), 파생/주석 필드만 여기에 쌓는다.
각 stage(P4 재확인 → P5 org → P6 provider)가 해당 필드를 채운다. 행은 절대 드롭하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .contract import Record


@dataclass
class Enriched:
    record: Record
    # P4 — 사원 존재 재확인
    employee_verified: Optional[bool] = None
    # P5 — 조직 as-of 매핑
    company_id: Optional[str] = None
    department_code_as_of: Optional[str] = None
    department_name_as_of: Optional[str] = None
    employee_name: Optional[str] = None
    # P6 — provider 주석(공통 컬럼 승격 금지 → enrichment_json 으로만 적재)
    annotations: Dict[str, Any] = field(default_factory=dict)


def wrap(records: List[Record]) -> List[Enriched]:
    """Record 리스트를 Enriched 로 감싼다(1:1, 행 수 보존)."""
    return [Enriched(record=r) for r in records]
