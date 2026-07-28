"""Adaptor→Enricher 입력 계약 (schema v4 envelope).

`../adaptor`의 `normalizer`를 import 하지 않고 wire 형태만 독립 재정의한다(결합 금지).

파킹 원칙(PLAN §8): **미지 필드는 드롭하지 않는다.** 각 레벨에서 알려진 키만
타입 슬롯으로 뽑고, 나머지는 그 레벨의 `extra` bag에 verbatim 보존한다.
`to_dict()`는 (알려진 present 키 + extra)를 합쳐 원본과 동치인 dict를 복원한다.

3.9/3.11 교차 호환: match문·런타임 `X|Y` 유니온 회피, `from __future__ import annotations`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional

JSON = Dict[str, Any]


def _split(d: JSON, known: List[str]):
    """알려진 키(present)와 미지 키(extra)를 분리해 반환.

    present: 입력에 실제로 존재한 알려진 키만(→ 부재 vs null 구분 보존).
    extra:   알려지지 않은 키 전부(파킹).
    """
    if not isinstance(d, dict):
        raise TypeError("object(dict)가 아님: %r" % type(d).__name__)
    present = {k: d[k] for k in known if k in d}
    extra = {k: v for k, v in d.items() if k not in known}
    return present, extra


@dataclass
class Identity:
    tenant_id: Optional[str] = None
    actor_id: Optional[str] = None
    email: Optional[str] = None
    internal_employee_id: Optional[str] = None
    extra: JSON = field(default_factory=dict)
    _present: FrozenSet[str] = field(default_factory=frozenset)

    KNOWN = ("tenant_id", "actor_id", "email", "internal_employee_id")

    @classmethod
    def from_dict(cls, d: JSON) -> "Identity":
        present, extra = _split(d, list(cls.KNOWN))
        return cls(
            tenant_id=present.get("tenant_id"),
            actor_id=present.get("actor_id"),
            email=present.get("email"),
            internal_employee_id=present.get("internal_employee_id"),
            extra=extra,
            _present=frozenset(present.keys()),
        )

    def to_dict(self) -> JSON:
        out: JSON = {}
        for k in self.KNOWN:
            if k in self._present:
                out[k] = getattr(self, k)
        out.update(self.extra)
        return out


@dataclass
class Client:
    product: Optional[str] = None
    extra: JSON = field(default_factory=dict)
    _present: FrozenSet[str] = field(default_factory=frozenset)

    KNOWN = ("product",)

    @classmethod
    def from_dict(cls, d: JSON) -> "Client":
        present, extra = _split(d, list(cls.KNOWN))
        return cls(product=present.get("product"), extra=extra,
                   _present=frozenset(present.keys()))

    def to_dict(self) -> JSON:
        out: JSON = {}
        if "product" in self._present:
            out["product"] = self.product
        out.update(self.extra)
        return out


@dataclass
class Ingest:
    signal: Optional[str] = None
    extra: JSON = field(default_factory=dict)
    _present: FrozenSet[str] = field(default_factory=frozenset)

    KNOWN = ("signal",)

    @classmethod
    def from_dict(cls, d: JSON) -> "Ingest":
        present, extra = _split(d, list(cls.KNOWN))
        return cls(signal=present.get("signal"), extra=extra,
                   _present=frozenset(present.keys()))

    def to_dict(self) -> JSON:
        out: JSON = {}
        if "signal" in self._present:
            out["signal"] = self.signal
        out.update(self.extra)
        return out


@dataclass
class Envelope:
    identity: Optional[Identity] = None
    client: Optional[Client] = None
    timestamp: Optional[float] = None
    session_id: Optional[str] = None
    event_id: Optional[str] = None
    ingest: Optional[Ingest] = None       # JSON 키는 "_ingest"
    extra: JSON = field(default_factory=dict)
    _present: FrozenSet[str] = field(default_factory=frozenset)

    KNOWN = ("identity", "client", "timestamp", "session_id", "event_id", "_ingest")

    @classmethod
    def from_dict(cls, d: JSON) -> "Envelope":
        present, extra = _split(d, list(cls.KNOWN))
        return cls(
            identity=Identity.from_dict(present["identity"]) if "identity" in present else None,
            client=Client.from_dict(present["client"]) if "client" in present else None,
            timestamp=present.get("timestamp"),
            session_id=present.get("session_id"),
            event_id=present.get("event_id"),
            ingest=Ingest.from_dict(present["_ingest"]) if "_ingest" in present else None,
            extra=extra,
            _present=frozenset(present.keys()),
        )

    def to_dict(self) -> JSON:
        out: JSON = {}
        if "identity" in self._present:
            out["identity"] = self.identity.to_dict()
        if "client" in self._present:
            out["client"] = self.client.to_dict()
        if "timestamp" in self._present:
            out["timestamp"] = self.timestamp
        if "session_id" in self._present:
            out["session_id"] = self.session_id
        if "event_id" in self._present:
            out["event_id"] = self.event_id
        if "_ingest" in self._present:
            out["_ingest"] = self.ingest.to_dict()
        out.update(self.extra)
        return out


@dataclass
class Record:
    """최상위 이벤트 레코드. 신호별 페이로드는 payload(log/llm) 또는 point(metric)."""
    envelope: Optional[Envelope] = None
    event_type: Optional[str] = None      # JSON 키는 "type"
    payload: Optional[JSON] = None
    point: Optional[JSON] = None
    extra: JSON = field(default_factory=dict)
    _present: FrozenSet[str] = field(default_factory=frozenset)
    raw_line: Optional[str] = None        # 원본 JSONL 텍스트(P7 raw_json verbatim용)

    KNOWN = ("envelope", "type", "payload", "point")

    @classmethod
    def from_dict(cls, d: JSON, raw_line: Optional[str] = None) -> "Record":
        present, extra = _split(d, list(cls.KNOWN))
        return cls(
            envelope=Envelope.from_dict(present["envelope"]) if "envelope" in present else None,
            event_type=present.get("type"),
            payload=present.get("payload"),
            point=present.get("point"),
            extra=extra,
            _present=frozenset(present.keys()),
            raw_line=raw_line,
        )

    def to_dict(self) -> JSON:
        out: JSON = {}
        if "envelope" in self._present:
            out["envelope"] = self.envelope.to_dict()
        if "type" in self._present:
            out["type"] = self.event_type
        if "payload" in self._present:
            out["payload"] = self.payload
        if "point" in self._present:
            out["point"] = self.point
        out.update(self.extra)
        return out

    # ---- 후속 phase 편의 접근자 (엔리치먼트는 공유 identity 기준, 신호 무관) ----
    @property
    def identity(self) -> Optional[Identity]:
        return self.envelope.identity if self.envelope else None

    @property
    def internal_employee_id(self) -> Optional[str]:
        return self.identity.internal_employee_id if self.identity else None

    @property
    def tenant_id(self) -> Optional[str]:
        return self.identity.tenant_id if self.identity else None

    @property
    def actor_id(self) -> Optional[str]:
        return self.identity.actor_id if self.identity else None

    @property
    def email(self) -> Optional[str]:
        return self.identity.email if self.identity else None

    @property
    def signal(self) -> Optional[str]:
        return self.envelope.ingest.signal if (self.envelope and self.envelope.ingest) else None

    @property
    def product(self) -> Optional[str]:
        return self.envelope.client.product if (self.envelope and self.envelope.client) else None

    @property
    def timestamp(self) -> Optional[float]:
        return self.envelope.timestamp if self.envelope else None

    @property
    def event_id(self) -> Optional[str]:
        return self.envelope.event_id if self.envelope else None

    @property
    def session_id(self) -> Optional[str]:
        return self.envelope.session_id if self.envelope else None
