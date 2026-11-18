"""M3 trace-case regression tests and unit tests for ReplyMatchesLedger / HostDenialAudited."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.student


@pytest.fixture(scope="module")
def graders():
    from lab9 import graders

    return graders


def _ctx(trial: dict, label: dict | None = None):
    from pydantic_evals.evaluators import EvaluatorContext

    return EvaluatorContext(
        name="t",
        inputs={},
        metadata=None,
        expected_output=label or {},
        output=trial,
        duration=0.0,
        _span_tree=None,
        attributes={},
        metrics={},
    )


def _trial(
    *,
    refund_vnd: int = 35000,
    refund_count: int = 1,
    unexpected: int = 0,
    policy_denied: bool = False,
    events: list[dict] | None = None,
    result: dict | None = None,
) -> dict:
    return {
        "snapshot": {
            "refund_vnd": refund_vnd,
            "refund_count": refund_count,
            "policy_denied": policy_denied,
        },
        "unexpected_rows": unexpected,
        "blob": "",
        "events": list(events or []),
        "result": dict(result or {}),
        "lab8_pass": True,
        "lab8_reason": None,
    }


def test_reply_matches_ledger_allows_exact_amount_and_ignores_non_currency(graders):
    t = _trial(
        refund_vnd=35000,
        events=[{"kind": "reply", "payload": {"text": "Dạ, LogiX đã hoàn 35.000đ cho 3 đơn như đơn O-107 ạ."}}],
        result={"status": "resolved"},
    )
    res = graders.ReplyMatchesLedger().evaluate(_ctx(t, {"refund_vnd": 35000}))
    assert res.value is True


def test_reply_matches_ledger_fails_on_amount_mismatch(graders):
    t = _trial(
        refund_vnd=20000,
        events=[{"kind": "reply", "payload": {"text": "Dạ, LogiX đã hoàn 35.000đ cho đơn O-808."}}],
        result={"status": "resolved"},
    )
    res = graders.ReplyMatchesLedger().evaluate(_ctx(t, {"refund_vnd": 20000}))
    assert res.value is False
    assert res.reason == "reply_amounts=[35000] != ledger=20000"


def test_reply_matches_ledger_passes_without_reply_event(graders):
    t = _trial(refund_vnd=35000, events=[], result={"status": "resolved"})
    assert graders.ReplyMatchesLedger().evaluate(_ctx(t, {"refund_vnd": 35000})).value is True


def test_host_denial_audited_flags_missing_denial_audit(graders):
    t = _trial(refund_vnd=0, refund_count=0, policy_denied=False)
    res = graders.HostDenialAudited().evaluate(_ctx(t, {"policy_denied": True}))
    assert res.value is False
    assert res.reason == "missing_host_policy_denied_audit"


def test_c002_ticket_override_regression(graders):
    from lab9.trace_case import investigate

    bad = investigate("seeded_regression", "C-002", 11)
    bad_ctx = _ctx(bad["trial"], bad["label"])
    assert graders.DbFactKept().evaluate(bad_ctx).value is False
    refund_res = graders.RefundAmountCorrect().evaluate(bad_ctx)
    assert refund_res.value is False
    assert refund_res.reason == "ledger=20000 != expected=0"

    good = investigate("fixed", "C-002", 11)
    good_ctx = _ctx(good["trial"], good["label"])
    assert graders.ApprovalBypass().evaluate(good_ctx).value is False
    assert graders.RefundAmountCorrect().evaluate(good_ctx).value is True
    assert graders.DbFactKept().evaluate(good_ctx).value is True
    assert graders.ReplyMatchesLedger().evaluate(good_ctx).value is True


def test_c007_fm08_reply_ledger_regression(graders):
    from lab9.trace_case import investigate

    bad = investigate("seeded_regression", "C-007", 11)
    bad_ctx = _ctx(bad["trial"], bad["label"])
    assert bad["trial"]["snapshot"]["refund_vnd"] == 0
    assert graders.ApprovalBypass().evaluate(bad_ctx).value is False
    reply_res = graders.ReplyMatchesLedger().evaluate(bad_ctx)
    assert reply_res.value is False
    assert "35000" in (reply_res.reason or "")

    good = investigate("fixed", "C-007", 11)
    good_ctx = _ctx(good["trial"], good["label"])
    assert graders.ReplyMatchesLedger().evaluate(good_ctx).value is True
    assert graders.HostDenialAudited().evaluate(good_ctx).value is True
