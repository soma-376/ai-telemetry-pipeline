"""조직 provider — installation_id 를 이벤트 발생 시점 팀 소속으로 해석한다.

order=0 으로 가장 먼저 실행하며, whitelist 컬럼 team_ids_as_of 를 채운다.
소속은 event ts 기준 as-of(joined_at ≤ ts < left_at)로 확정한다.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import psycopg

from ..errors import BackendUnavailable
from ..model import Enriched
from .base import EnrichmentProvider

_MEMBERSHIP_SQL = """
SELECT tm.team_id::text, tm.joined_at, tm.left_at
FROM enrollment.installations i
JOIN enrollment.team_memberships tm ON tm.member_id = i.member_id
JOIN enrollment.teams t ON t.id = tm.team_id AND t.status = 'active'
WHERE i.id = %s::uuid
"""

Interval = Tuple[str, datetime, "datetime | None"]


class OrgProvider(EnrichmentProvider):
    name = "org"
    order = 0

    def __init__(self) -> None:
        self._dsn = os.environ.get("ENRICHMENT_PG_DSN", "")

    def enrich(self, item: Enriched, ctx: Dict[str, Any]) -> Dict[str, Any]:
        installation_id = item.event.envelope.identity.installation_id
        ts = item.timestamp
        if not installation_id or ts is None:
            return {}

        # push 단위 캐시: 같은 installation 은 한 번만 조회한다.
        cache: Dict[str, List[Interval]] = ctx.setdefault("_org_memberships", {})
        if installation_id not in cache:
            cache[installation_id] = self._load(installation_id)

        at = datetime.fromtimestamp(ts, tz=timezone.utc)
        team_ids = [
            team_id
            for team_id, joined_at, left_at in cache[installation_id]
            if joined_at <= at and (left_at is None or at < left_at)
        ]
        item.team_ids_as_of = team_ids
        return {"team_ids": team_ids}

    def _load(self, installation_id: str) -> List[Interval]:
        try:
            with psycopg.connect(self._dsn) as conn, conn.cursor() as cur:
                cur.execute(_MEMBERSHIP_SQL, (installation_id,))
                return [(row[0], row[1], row[2]) for row in cur.fetchall()]
        except psycopg.OperationalError as exc:
            # OperationalError 만 잡는다 — 범위를 넓히면 스키마 오류 같은 영구 오류까지
            # 재시도돼 collector 재시도 큐가 막힌다.
            raise BackendUnavailable(f"rds unreachable: {exc}") from exc
