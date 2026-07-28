"""Apply enrichment while preserving the normalized event stream.

한 OTLP push 단위로 실행된다: P4(신원 해석) → P5/P6(provider 적용 — org as-of
매핑 + 확장 스텁). RDS 연결은 push 단위로 열고 닫는다(ThreadingHTTPServer 의
요청 스레드 간 공유 없음 → 동시성 안전).
"""
from __future__ import annotations

from collections.abc import Iterable

from normalizer.model import Normalized

from . import rds
from .enrich_org import OrgOf, make_rds_resolver
from .errors import BackendUnavailable
from .model import Enriched, wrap
from .providers.registry import Registry
from .resolve_employee import ResolveFn, resolve_employees, resolver_via_rds

# 모듈 로드 시 1회 자동 발견(pkgutil 스캔을 push 마다 반복하지 않는다).
_REGISTRY = Registry()


def enrich(events: Iterable[Normalized]) -> list[Enriched]:
    """Normalized 이벤트에 조직 정보를 부여해 Enriched 로 반환한다. 행 수 보존.

    normalize()가 push 전체를 이미 버퍼링(pair_call_ids)하므로 generator 대신
    list 를 확정 반환한다 — RDS 연결 수명을 push 단위로 결정적으로 관리하기 위함.
    """
    items = wrap(list(events))
    if not items:
        return items  # 빈 배치는 연결 자체를 열지 않는다.
    try:
        conn = rds.connect()
    except Exception as exc:
        raise BackendUnavailable(f"rds connect failed: {exc}") from exc
    # psycopg3: with 블록 종료 시 commit(예외 시 rollback) 후 연결을 닫는다.
    with conn:
        try:
            _apply(items, resolver_via_rds(conn), make_rds_resolver(conn))
        except Exception as exc:
            import psycopg  # 지연 import — connect 성공 이후라 반드시 존재

            if isinstance(exc, psycopg.Error):
                raise BackendUnavailable(f"rds query failed: {exc}") from exc
            raise
    return items


def enrich_with(events: Iterable[Normalized],
                resolve: ResolveFn, org_of: OrgOf) -> list[Enriched]:
    """순수 버전(단위 테스트) — RDS 없이 memory 오라클로 동일 플로우를 태운다."""
    return _apply(wrap(list(events)), resolve, org_of)


def _apply(items: list[Enriched], resolve: ResolveFn, org_of: OrgOf) -> list[Enriched]:
    resolve_employees(items, resolve)
    _REGISTRY.apply(items, {"org_of": org_of})
    return items
