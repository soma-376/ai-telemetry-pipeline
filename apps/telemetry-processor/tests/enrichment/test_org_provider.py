"""org provider 의 as-of 조인과 RDS 장애 분류 고정.

as-of 경계는 좌폐우개(`joined_at <= at < left_at`)다.
DB 없이 보려면 `Registry([OrgProvider()]).apply(items, ctx)` 를 직접 부르고
`ctx["_org_memberships"]` 를 미리 채운다 — 이 캐시가 조회를 가로채는 seam 이다.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import psycopg

from enrichment.errors import BackendUnavailable
from enrichment.model import wrap
from enrichment.providers.org import OrgProvider
from enrichment.providers.registry import Registry

from .factory import make_log

# 2026-07-01T00:00:00Z 근방. factory 기본 ts 와 같은 시각이다.
AT = 1_782_900_000.0


def _utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)


def _at() -> datetime:
    return datetime.fromtimestamp(AT, tz=timezone.utc)


class OrgAsOfTest(unittest.TestCase):
    def _apply(self, memberships, *, installation_id="inst-0001", ts=AT):
        """캐시를 미리 채워 RDS 조회 없이 as-of 로직만 돌린다."""
        items = wrap([make_log(installation_id=installation_id, ts=ts)])
        ctx = {"_org_memberships": {installation_id: memberships}}
        Registry([OrgProvider()]).apply(items, ctx)
        return items[0]

    def test_joined_before_and_still_member(self) -> None:
        """가입 이후이고 탈퇴가 없으면 소속으로 잡히는지 검증한다."""
        item = self._apply([("team-a", _utc("2026-01-01T00:00:00"), None)])

        self.assertEqual(item.team_ids_as_of, ["team-a"])
        self.assertEqual(item.annotations["org"], {"team_ids": ["team-a"]})

    def test_joined_at_boundary_is_inclusive(self) -> None:
        """joined_at 과 정확히 같은 시각은 소속에 포함된다(좌폐)."""
        item = self._apply([("team-a", _at(), None)])

        self.assertEqual(item.team_ids_as_of, ["team-a"])

    def test_left_at_boundary_is_exclusive(self) -> None:
        """left_at 과 정확히 같은 시각은 소속에서 제외된다(우개)."""
        item = self._apply(
            [("team-a", _utc("2026-01-01T00:00:00"), _at())]
        )

        self.assertEqual(item.team_ids_as_of, [])

    def test_left_after_event_is_still_member(self) -> None:
        """이벤트 이후에 탈퇴했다면 그 시점에는 여전히 소속이다."""
        item = self._apply(
            [("team-a", _utc("2026-01-01T00:00:00"), _utc("2026-12-31T00:00:00"))]
        )

        self.assertEqual(item.team_ids_as_of, ["team-a"])

    def test_joined_after_event_is_not_a_member(self) -> None:
        """이벤트 이후에 가입했다면 그 시점에는 소속이 아니다."""
        item = self._apply([("team-a", _utc("2026-12-31T00:00:00"), None)])

        self.assertEqual(item.team_ids_as_of, [])

    def test_multiple_active_teams_are_all_returned(self) -> None:
        """동시에 여러 팀에 속하면 전부 반환하며 입력 순서를 유지한다."""
        item = self._apply(
            [
                ("team-a", _utc("2026-01-01T00:00:00"), None),
                ("team-b", _utc("2026-02-01T00:00:00"), None),
                ("team-old", _utc("2025-01-01T00:00:00"), _utc("2026-03-01T00:00:00")),
            ]
        )

        self.assertEqual(item.team_ids_as_of, ["team-a", "team-b"])

    def test_no_installation_id_skips_lookup(self) -> None:
        """installation_id 가 없으면 조회 없이 빈 주석을 남기는지 검증한다."""
        items = wrap([make_log(installation_id=None)])
        ctx: dict = {}

        Registry([OrgProvider()]).apply(items, ctx)

        self.assertEqual(items[0].team_ids_as_of, [])
        self.assertEqual(items[0].annotations["org"], {})
        # 캐시를 만들지도 않는다 → RDS 를 아예 부르지 않았다는 뜻.
        self.assertNotIn("_org_memberships", ctx)

    def test_cache_is_shared_across_items_in_one_push(self) -> None:
        """같은 installation 은 push 안에서 한 번만 조회하는지 검증한다."""
        items = wrap(
            [
                make_log(installation_id="inst-0001", sequence=1),
                make_log(installation_id="inst-0001", sequence=2),
            ]
        )
        ctx = {
            "_org_memberships": {
                "inst-0001": [("team-a", _utc("2026-01-01T00:00:00"), None)]
            }
        }

        with patch("psycopg.connect") as connect:
            Registry([OrgProvider()]).apply(items, ctx)

        connect.assert_not_called()
        self.assertEqual(
            [item.team_ids_as_of for item in items], [["team-a"], ["team-a"]]
        )


class OrgFailureClassificationTest(unittest.TestCase):
    """RDS 장애만 503(재시도 가능)으로 좁게 분류한다.

    범위를 넓히면 스키마 오류 같은 영구 오류까지 재시도돼 collector 재시도 큐가
    막힌다. 그래서 `OperationalError` 하나만 잡는다 — 이 좁음이 의도된 결정이다.
    """

    def _enrich(self):
        items = wrap([make_log(installation_id="inst-0001")])
        Registry([OrgProvider()]).apply(items, {})
        return items

    def test_operational_error_becomes_backend_unavailable(self) -> None:
        """연결 불가(OperationalError)는 BackendUnavailable 로 승격된다 → 503."""
        with patch(
            "psycopg.connect",
            side_effect=psycopg.OperationalError("connection refused"),
        ):
            with self.assertRaises(BackendUnavailable) as caught:
                self._enrich()

        self.assertIn("rds unreachable", str(caught.exception))

    def test_programming_error_is_not_swallowed(self) -> None:
        """스키마 오류(ProgrammingError)는 잡지 않고 그대로 올린다 → 400."""
        with patch(
            "psycopg.connect",
            side_effect=psycopg.ProgrammingError('relation "x" does not exist'),
        ):
            with self.assertRaises(psycopg.ProgrammingError):
                self._enrich()

    def test_generic_error_is_not_swallowed(self) -> None:
        """psycopg 계열이 아닌 오류도 승격 대상이 아니다."""
        with patch("psycopg.connect", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self._enrich()


if __name__ == "__main__":
    unittest.main()
