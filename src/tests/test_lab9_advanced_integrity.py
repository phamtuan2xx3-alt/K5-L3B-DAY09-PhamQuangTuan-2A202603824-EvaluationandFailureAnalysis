"""M7 integrity & ratchet checks on hidden-trap patterns (runs under `-k advanced`)."""
from __future__ import annotations

import copy

import pytest

pytestmark = pytest.mark.student

ROWS = [
    {"item_id": f"E-{i:03d}", "seed": s, "pass_rate": True, "cost": 1.0, "slices": ["denial"] if i < 2 else []}
    for i in range(4)
    for s in (1, 2)
]
SPEC = {
    "eval_set_version": "v2",
    "eval_set": "data/eval/eval_set_v2.jsonl",
    "seeds": [1, 2],
    "bootstrap": {"n_resamples": 1000, "rng": 2027, "confidence": 0.95},
    "metrics": [
        {
            "id": "pass_rate",
            "kind": "capability",
            "blocking": True,
            "threshold": {"min": 0.8, "no_significant_drop": True},
        },
        {
            "id": "cost_per_success",
            "kind": "system",
            "blocking": False,
            "threshold": {"max_increase": 0.10},
        },
    ],
    "slices": [
        {"name": "denial", "metric": "pass_rate", "min": 0.9, "no_significant_drop": True, "blocking": True},
    ],
}


def _report(rows, metrics, *, items=4, seeds=(1, 2), failures=()):
    return {
        "manifest": {"eval_set_sha": "x", "items": items, "seeds": list(seeds)},
        "rows": rows,
        "metrics": metrics,
        "evaluator_failures": list(failures),
    }


def test_clean_report_and_spec_pass_integrity():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0, "cost_per_success": 1.0})
    assert gate.integrity_check(base, base, SPEC, SPEC) == []


def test_integrity_catches_duplicate_item_seed_rows():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0, "cost_per_success": 1.0})
    dup_rows = copy.deepcopy(ROWS[:-1]) + [copy.deepcopy(ROWS[0])]
    pr = _report(dup_rows, {"pass_rate": 1.0, "cost_per_success": 1.0})
    assert gate.integrity_check(pr, base, SPEC)


def test_integrity_catches_evaluator_failures_on_green_run():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0, "cost_per_success": 1.0})
    pr = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0, "cost_per_success": 1.0}, failures=["E-000@1:TrialPass:err"])
    assert gate.integrity_check(pr, base, SPEC)


def test_integrity_catches_none_row_metric_on_passing_report():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0, "cost_per_success": 1.0})
    rows = copy.deepcopy(ROWS)
    rows[0]["pass_rate"] = None
    pr = _report(rows, {"pass_rate": 1.0, "cost_per_success": 1.0})
    assert gate.integrity_check(pr, base, SPEC)


def test_integrity_catches_tampered_slice_tags():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0, "cost_per_success": 1.0})
    rows = copy.deepcopy(ROWS)
    rows[0]["slices"] = []
    pr = _report(rows, {"pass_rate": 1.0, "cost_per_success": 1.0})
    assert gate.integrity_check(pr, base, SPEC)


def test_integrity_catches_tampered_summary_metrics():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0, "cost_per_success": 1.0})
    rows = copy.deepcopy(ROWS)
    rows[0]["pass_rate"] = False
    pr = _report(rows, {"pass_rate": 1.0, "cost_per_success": 1.0})
    assert gate.integrity_check(pr, base, SPEC)


def test_integrity_catches_ratchet_loosened_slices_and_dropped_ci():
    from lab9 import gate

    base = _report(copy.deepcopy(ROWS), {"pass_rate": 1.0, "cost_per_success": 1.0})

    dropped_metric_ci = copy.deepcopy(SPEC)
    dropped_metric_ci["metrics"][0]["threshold"].pop("no_significant_drop")
    assert gate.integrity_check(base, base, dropped_metric_ci, SPEC)

    dropped_slice_ci = copy.deepcopy(SPEC)
    dropped_slice_ci["slices"][0].pop("no_significant_drop")
    assert gate.integrity_check(base, base, dropped_slice_ci, SPEC)

    lowered_slice_min = copy.deepcopy(SPEC)
    lowered_slice_min["slices"][0]["min"] = 0.7
    assert gate.integrity_check(base, base, lowered_slice_min, SPEC)

    unblocked_slice = copy.deepcopy(SPEC)
    unblocked_slice["slices"][0]["blocking"] = False
    assert gate.integrity_check(base, base, unblocked_slice, SPEC)

    bumped_version_same_eval = copy.deepcopy(SPEC)
    bumped_version_same_eval["eval_set_version"] = "v3"
    assert gate.integrity_check(base, base, bumped_version_same_eval, SPEC)
