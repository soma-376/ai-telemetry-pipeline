"""provider 등록·순차 적용 파이프라인 (PLAN §6 P6).

자동 발견: 이 패키지의 모든 모듈을 스캔해 EnrichmentProvider 구상 클래스를 찾는다.
→ **새 스텁 파일 추가만으로 registry 에 붙는다(코어 수정 0).** 이 파일은 특정 provider
이름을 하드코딩하지 않는다(구조 불변식).

적용은 order→name 순. 각 provider 결과를 item.annotations[name] 에 기록. 행 수 불변.
"""
from __future__ import annotations

import importlib
import pkgutil
from typing import Any, Dict, List, Optional

from ..model import Enriched
from . import __name__ as _PKG_NAME
from . import __path__ as _PKG_PATH
from .base import EnrichmentProvider

_SKIP_MODULES = {"base", "registry"}


def discover_providers() -> List[EnrichmentProvider]:
    """패키지 스캔으로 구상 provider 인스턴스 목록 생성(order→name 정렬)."""
    found: Dict[str, EnrichmentProvider] = {}
    for modinfo in pkgutil.iter_modules(list(_PKG_PATH)):
        if modinfo.name in _SKIP_MODULES:
            continue
        mod = importlib.import_module("%s.%s" % (_PKG_NAME, modinfo.name))
        for obj in vars(mod).values():
            if (isinstance(obj, type)
                    and issubclass(obj, EnrichmentProvider)
                    and obj is not EnrichmentProvider):
                inst = obj()
                found[inst.name] = inst
    return sorted(found.values(), key=lambda p: (getattr(p, "order", 100), p.name))


class Registry:
    def __init__(self, providers: Optional[List[EnrichmentProvider]] = None):
        self.providers = (providers if providers is not None else discover_providers())
        self.providers.sort(key=lambda p: (getattr(p, "order", 100), p.name))

    def names(self) -> List[str]:
        return [p.name for p in self.providers]

    def apply(self, items: List[Enriched], ctx: Dict[str, Any]) -> List[Enriched]:
        """모든 항목에 모든 provider 를 순차 적용. in-place, 행 수 불변."""
        for it in items:
            for p in self.providers:
                result = p.enrich(it, ctx) or {}
                it.annotations[p.name] = result
        return items
