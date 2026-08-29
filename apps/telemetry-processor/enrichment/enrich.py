"""Apply enrichment while preserving the normalized event stream.

한 OTLP push 단위로 실행된다. provider 는 annotations 를 쌓고, org provider 는
RDS(enrollment 스키마)를 push 단위로 조회해 installation_id + ts as-of 조인으로
team_ids_as_of 를 채운다 — whitelist 컬럼 승격은 이 필드 하나뿐이다(ADR 0006).
RDS 장애는 BackendUnavailable(503, 재시도 가능)로 분류된다. 신뢰 키 installation_id 는
어댑터가 이미 envelope 에 담아두므로 여기서 다시 해석할 필요가 없다.
"""
from __future__ import annotations

from collections.abc import Iterable

from normalizer.model import Normalized

from .model import Enriched, wrap
from .providers.registry import Registry

# 모듈 로드 시 1회 자동 발견(pkgutil 스캔을 push 마다 반복하지 않는다).
_REGISTRY = Registry()


def enrich(events: Iterable[Normalized]) -> list[Enriched]:
    """Normalized 이벤트에 provider 주석을 부여해 Enriched 로 반환한다. 행 수 보존.

    normalize()가 push 전체를 이미 버퍼링(pair_call_ids)하므로 generator 대신
    list 를 확정 반환한다.
    """
    items = wrap(list(events))
    if not items:
        return items
    _REGISTRY.apply(items, {})
    return items
