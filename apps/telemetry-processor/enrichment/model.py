"""엔리치먼트 파이프라인을 흐르는 공통 컨테이너.

원본 Normalized 이벤트는 불변으로 감싸 두고, 파생/주석 필드만 여기에 쌓는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from normalizer.model import Normalized


@dataclass
class Enriched:
    event: Normalized
    team_ids_as_of: list[str] = field(default_factory=list)
    # P6 — provider 주석(공통 컬럼 승격 금지 → enrichment_json 으로만 적재)
    annotations: dict[str, Any] = field(default_factory=dict)

    # ---- envelope 공유 접근자(신호 무관, 엔리치먼트·적재가 공통으로 사용) ----

    @property
    def event_id(self) -> str:
        env = self.event.envelope
        # record_id 는 finalize()가 항상 스탬프하지만, 빈 키가 ReplacingMergeTree
        # 의 전 행을 한 키로 합치는 사고를 막기 위해 source_record_id 로 방어한다.
        return env.record_id or env._ingest.source_record_id or ""

    @property
    def tenant_id(self) -> str | None:
        return self.event.envelope.identity.tenant_id

    @property
    def signal(self) -> str:
        return self.event.envelope._ingest.signal.value

    @property
    def product(self) -> str:
        return self.event.envelope.client.product

    @property
    def timestamp(self) -> float | None:
        return self.event.envelope.timestamp


def wrap(events: list[Normalized]) -> list[Enriched]:
    """Normalized 리스트를 Enriched 로 감싼다(1:1, 행 수 보존)."""
    return [Enriched(event=e) for e in events]
