"""재사용 가능한 데이터 품질 체크.

각 함수는 "이런 문제를 발견하면 진단으로 남겨라"는 기록 헬퍼다. 문제 여부의
판단(방아쇠)은 호출부(어댑터/normalize)가 하고, 여기서는 DiagnosticEvent 의
모양만 책임진다. 세 가지 문제 유형:

  - report_unmapped_fields   → unmapped_fields   : 안 읽고 버려진 소스 키
  - report_empty_mapping    → mapping_miss      : 필드 뽑기 완전 실패
  - report_invariant_failure → invariant_failure : 매핑됐지만 값이 모순

(매칭 자체가 안 된 out-of-scope 레코드의 unknown_event 는 여기가 아니라
normalize.py 가 직접 만든다.)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .model import DiagnosticEvent
from .reporter import DiagnosticReporter
from .tracking import TrackingAttrs

# 라우팅용으로만 조회되는 키 — payload 필드가 아니므로 "안 읽음"에서 제외한다.
_ROUTING_KEYS = frozenset({"event.name"})


def report_unmapped_fields(
    reporter: DiagnosticReporter,
    *,
    adapter: str,
    event_name: str,
    source_record_id: str,
    signal: str,
    tracked: TrackingAttrs,
    routing_keys: frozenset[str] = _ROUTING_KEYS,
) -> None:
    """소스엔 있는데 어댑터가 아무도 안 읽고 흘린 키를 기록(조용한 필드 유실).

    ``tracked`` 는 어댑터에 그대로 넘겼던 TrackingAttrs 인스턴스여야 한다.
    그래야 ``accessed`` 가 어댑터가 실제로 조회한 키를 반영한다.
    안 읽은 키 = 전체 키 − 읽은 키 − 라우팅 키. 승격 후보 발굴에 쓴다.
    """
    unmapped_keys = set(tracked) - tracked.accessed - routing_keys
    if not unmapped_keys:
        return
    # dict.__getitem__ 로 값을 읽어 accessed 를 오염시키지 않는다.
    unmapped = {key: dict.__getitem__(tracked, key) for key in unmapped_keys}
    reporter.report(
        DiagnosticEvent(
            issue_type="unmapped_fields",
            adapter=adapter,
            event_name=event_name,
            source_record_id=source_record_id,
            signal=signal,
            source_values=unmapped,
            message="source keys present but not read by adapter",
        )
    )


def report_empty_mapping(
    reporter: DiagnosticReporter,
    *,
    adapter: str,
    event_name: str,
    target_field: str,
    source_record_id: str,
    signal: str,
    timestamp: float,
    source_values: Mapping[str, Any],
) -> None:
    """이벤트는 인식했는데 target_field 를 통째로 못 뽑은 경우(완전 실패)를 기록.

    예: LLM 호출인데 토큰이 하나도 안 잡힘(billable == 0). 어댑터가 그 상황을
    감지했을 때 호출한다. 무엇이 있었는지 보라고 source_values 를 함께 남기되,
    빈 값(None/"")은 걸러 노이즈를 줄인다.
    """
    # 빈 값은 제외 — 실제로 값이 있던 키만 남겨 원인 추적을 돕는다.
    non_empty = {
        key: value
        for key, value in source_values.items()
        if value is not None and value != ""
    }
    reporter.report(
        DiagnosticEvent(
            issue_type="mapping_miss",
            adapter=adapter,
            event_name=event_name,
            target_field=target_field,
            source_record_id=source_record_id,
            signal=signal,
            timestamp=timestamp,
            source_values=non_empty,
        )
    )


def report_invariant_failure(
    reporter: DiagnosticReporter,
    *,
    adapter: str,
    event_name: str,
    source_record_id: str,
    signal: str,
    timestamp: float,
    message: str,
    source_values: Mapping[str, Any],
) -> None:
    """매핑은 됐지만 값들이 서로 안 맞는(모순) 경우를 기록.

    예: 토큰 합계 검산 실패(reconciles() is False). mapping_miss 와 달리 값은
    있으므로 걸러내지 않고 관련 값 전부를 source_values 로 남기고, 무엇이
    어긋났는지는 message 로 설명한다.
    """
    reporter.report(
        DiagnosticEvent(
            issue_type="invariant_failure",
            adapter=adapter,
            event_name=event_name,
            source_record_id=source_record_id,
            signal=signal,
            timestamp=timestamp,
            source_values=dict(source_values),
            message=message,
        )
    )
