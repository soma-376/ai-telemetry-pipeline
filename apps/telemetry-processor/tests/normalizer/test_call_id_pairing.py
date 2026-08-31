"""tool_decision ↔ tool_call 페어링(`pair_call_ids`)의 현행 동작 고정.

"AI 제안 수락률" KPI 가 이 조인에 걸려 있다. 이벤트는 손으로 만든 dict 가 아니라
`build_envelope` + `finalize` 를 태워 만든다 — record_id 까지 실제 경로와 같게
재현해야 페어링이 키를 흔드는지 아닌지를 볼 수 있기 때문이다.
"""
from __future__ import annotations

import unittest

from normalizer.common.call_id import pair_call_ids, synth_call_id
from normalizer.common.context import IngestContext
from normalizer.common.envelope import build_envelope, build_ingest, finalize
from normalizer.model import (
    Client,
    Decision,
    DecisionScope,
    DecisionSource,
    Identity,
    LogKind,
    NormalizedLog,
    SignalType,
    Surface,
    ToolCall,
    ToolDecision,
)

_ADAPTER = "claude_code"
_ADAPTER_VERSION = 3


def _tool_event(
    *,
    kind: LogKind,
    tool_name: str,
    session: str = "sess-1",
    ts: float = 1000.0,
    sequence: int | None = 1,
    inferred: bool = True,
    tenant: str = "acme",
) -> NormalizedLog:
    """어댑터가 만드는 것과 같은 순서로 tool 이벤트 하나를 조립한다."""
    ctx = IngestContext(
        tenant_id=tenant,
        raw_record_id=f"raw-{session}-{sequence}-{tool_name}",
        signal_type=SignalType.LOG,
    )
    ingest = build_ingest(
        ctx=ctx, adapter=_ADAPTER, adapter_version=_ADAPTER_VERSION
    )
    ingest.call_id_inferred = inferred
    envelope = build_envelope(
        client=Client(product="claude_code", surface=Surface.CLI),
        identity=Identity(tenant_id=tenant),
        session_id=session,
        ts=ts,
        ingest=ingest,
    )
    event = NormalizedLog(envelope=envelope, sequence=sequence)
    if kind is LogKind.TOOL_DECISION:
        event.type = LogKind.TOOL_DECISION
        event.payload = ToolDecision(
            decision=Decision.ACCEPT,
            decided_by=DecisionSource.USER,
            scope=DecisionScope.ONCE,
            tool_name=tool_name,
        )
    else:
        event.type = LogKind.TOOL_CALL
        event.payload = ToolCall(tool_name=tool_name, success=True)
    # 어댑터와 같은 합성 키를 먼저 붙인 뒤 finalize 한다.
    event.call_id = synth_call_id(session, sequence, ts, tool_name)
    return finalize(event)


def _decision(**overrides) -> NormalizedLog:
    return _tool_event(kind=LogKind.TOOL_DECISION, **overrides)


def _call(**overrides) -> NormalizedLog:
    return _tool_event(kind=LogKind.TOOL_CALL, **overrides)


class PairCallIdsTest(unittest.TestCase):
    def test_returns_none_and_mutates_in_place(self) -> None:
        """반환값 없이 리스트의 이벤트를 직접 바꾸는 in-place 함수인지 검증한다."""
        decision = _decision(tool_name="Edit", ts=1.0, sequence=1)
        call = _call(tool_name="Edit", ts=2.0, sequence=2)

        self.assertIsNone(pair_call_ids([decision, call]))
        self.assertEqual(call.call_id, decision.call_id)

    def test_pairs_decision_to_following_call_of_same_tool(self) -> None:
        """같은 세션·같은 도구명의 직전 결정 키를 실행이 물려받는지 검증한다."""
        decision = _decision(tool_name="Edit", ts=1.0, sequence=1)
        call = _call(tool_name="Edit", ts=2.0, sequence=2)
        original = decision.call_id

        pair_call_ids([decision, call])

        self.assertEqual(decision.call_id, original)
        self.assertEqual(call.call_id, original)

    def test_leaves_orphan_decision_untouched(self) -> None:
        """실행이 따라오지 않는 결정은 자기 합성 키를 그대로 유지하는지 검증한다."""
        decision = _decision(tool_name="Read", ts=1.0, sequence=1)
        original = decision.call_id

        pair_call_ids([decision])

        self.assertEqual(decision.call_id, original)

    def test_leaves_call_without_prior_decision_untouched(self) -> None:
        """앞선 결정이 없는 실행은 물려받을 키가 없어 합성 키를 유지하는지 검증한다."""
        call = _call(tool_name="Grep", ts=1.0, sequence=1)
        original = call.call_id

        pair_call_ids([call])

        self.assertEqual(call.call_id, original)

    def test_does_not_pair_across_sessions(self) -> None:
        """세션이 다르면 같은 도구명이어도 짝짓지 않는지 검증한다."""
        decision = _decision(tool_name="Edit", session="sess-a", ts=1.0, sequence=1)
        call = _call(tool_name="Edit", session="sess-b", ts=2.0, sequence=2)
        original = call.call_id

        pair_call_ids([decision, call])

        self.assertEqual(call.call_id, original)
        self.assertNotEqual(call.call_id, decision.call_id)

    def test_does_not_pair_across_tool_names(self) -> None:
        """도구명이 다르면 같은 세션이어도 짝짓지 않는지 검증한다."""
        decision = _decision(tool_name="Edit", ts=1.0, sequence=1)
        call = _call(tool_name="Bash", ts=2.0, sequence=2)
        original = call.call_id

        pair_call_ids([decision, call])

        self.assertEqual(call.call_id, original)

    def test_skips_events_whose_call_id_was_not_inferred(self) -> None:
        """tool_use_id 를 받은 이벤트(inferred=False)는 건드리지 않는지 검증한다.

        claude_code 가 tool_use_id 를 실어 보내면 어댑터가 그 값을 그대로 쓰고
        call_id_inferred 를 False 로 둔다 — 그 경우 이 패스는 무개입이다.
        """
        decision = _decision(tool_name="Edit", ts=1.0, sequence=1, inferred=False)
        call = _call(tool_name="Edit", ts=2.0, sequence=2, inferred=False)
        original = call.call_id

        pair_call_ids([decision, call])

        self.assertEqual(call.call_id, original)
        self.assertNotEqual(call.call_id, decision.call_id)

    def test_one_decision_is_consumed_by_one_call(self) -> None:
        """한 결정은 한 실행에만 물려주고, 뒤따르는 실행은 자기 키를 유지하는지 검증한다."""
        decision = _decision(tool_name="Edit", ts=1.0, sequence=1)
        first = _call(tool_name="Edit", ts=2.0, sequence=2)
        second = _call(tool_name="Edit", ts=3.0, sequence=3)
        second_original = second.call_id

        pair_call_ids([decision, first, second])

        self.assertEqual(first.call_id, decision.call_id)
        self.assertEqual(second.call_id, second_original)

    def test_orders_by_timestamp_not_list_position(self) -> None:
        """리스트 순서가 아니라 (timestamp, sequence) 순으로 짝짓는지 검증한다."""
        call = _call(tool_name="Edit", ts=2.0, sequence=2)
        decision = _decision(tool_name="Edit", ts=1.0, sequence=1)
        call_original = call.call_id

        # 실행을 먼저 넣어도 시간순으로는 결정이 앞선다.
        pair_call_ids([call, decision])

        self.assertEqual(call.call_id, decision.call_id)
        self.assertNotEqual(call.call_id, call_original)

    def test_call_before_decision_in_time_is_not_paired(self) -> None:
        """실행이 결정보다 먼저 일어났으면 짝짓지 않는지 검증한다."""
        call = _call(tool_name="Edit", ts=1.0, sequence=1)
        decision = _decision(tool_name="Edit", ts=2.0, sequence=2)
        original = call.call_id

        pair_call_ids([decision, call])

        self.assertEqual(call.call_id, original)

    def test_ignores_events_without_a_call_id(self) -> None:
        """call_id 가 없는 이벤트(예: user_prompt)는 후보에서 빠지는지 검증한다."""
        decision = _decision(tool_name="Edit", ts=1.0, sequence=1)
        call = _call(tool_name="Edit", ts=2.0, sequence=2)
        bare = _call(tool_name="Edit", ts=1.5, sequence=None)
        bare.call_id = None

        pair_call_ids([decision, bare, call])

        self.assertIsNone(bare.call_id)
        self.assertEqual(call.call_id, decision.call_id)

    def test_record_id_is_not_recomputed_after_pairing(self) -> None:
        """페어링이 record_id 를 바꾸지 않는 현행 동작을 고정한다.

        finalize()가 페어링 **이전** 에 돌아 합성 키로 discriminator 를 굳히므로,
        call_id 가 뒤에 바뀌어도 record_id 는 그대로다. 즉 record_id 는 "그
        레코드 자체"를 가리키고 이후 mutation 에 흔들리지 않는다.
        """
        decision = _decision(tool_name="Edit", ts=1.0, sequence=1)
        call = _call(tool_name="Edit", ts=2.0, sequence=2)
        before = call.envelope.record_id

        pair_call_ids([decision, call])

        self.assertEqual(call.envelope.record_id, before)
        self.assertNotEqual(call.envelope.record_id, decision.envelope.record_id)


class SynthCallIdTest(unittest.TestCase):
    def test_is_deterministic_for_the_same_inputs(self) -> None:
        """같은 (세션, 도구, 순번, 시각)이면 같은 합성 키인지 검증한다."""
        self.assertEqual(
            synth_call_id("s", 1, 1.0, "Edit"),
            synth_call_id("s", 1, 1.0, "Edit"),
        )

    def test_has_syn_prefix_and_fixed_width(self) -> None:
        """합성 키가 'syn-' + 12자 hex 형태인지 검증한다."""
        value = synth_call_id("s", 1, 1.0, "Edit")
        self.assertTrue(value.startswith("syn-"))
        self.assertEqual(len(value), len("syn-") + 12)

    def test_differs_per_record(self) -> None:
        """세션·도구·순번·시각 중 하나만 달라도 다른 키가 되는지 검증한다."""
        base = synth_call_id("s", 1, 1.0, "Edit")
        self.assertNotEqual(base, synth_call_id("t", 1, 1.0, "Edit"))
        self.assertNotEqual(base, synth_call_id("s", 2, 1.0, "Edit"))
        self.assertNotEqual(base, synth_call_id("s", 1, 2.0, "Edit"))
        self.assertNotEqual(base, synth_call_id("s", 1, 1.0, "Bash"))

    def test_none_sequence_is_part_of_the_key(self) -> None:
        """sequence 가 None 이어도 키를 만들며 0 과 구분되는지 검증한다."""
        self.assertNotEqual(
            synth_call_id("s", None, 1.0, "Edit"),
            synth_call_id("s", 0, 1.0, "Edit"),
        )


if __name__ == "__main__":
    unittest.main()
