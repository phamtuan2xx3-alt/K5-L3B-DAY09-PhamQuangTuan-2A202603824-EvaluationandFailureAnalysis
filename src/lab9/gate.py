"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, aggregate, load_spec, per_item
from lab9.graders import GRADERS


def _ratchet_entry(kind_label: str, base_item: dict, pr_item: dict, base_th: dict, pr_th: dict) -> list[str]:
    """Verify a metric or slice threshold was not loosened relative to base_spec."""
    problems: list[str] = []
    if base_item.get("blocking") and not pr_item.get("blocking"):
        problems.append(f"ratchet:{kind_label}_unblocked")
    if "min" in base_th and ("min" not in pr_th or pr_th["min"] < base_th["min"]):
        problems.append(f"ratchet:{kind_label}_min_lowered")
    if "max" in base_th and ("max" not in pr_th or pr_th["max"] > base_th["max"]):
        problems.append(f"ratchet:{kind_label}_max_raised")
    if "max_increase" in base_th and (
        "max_increase" not in pr_th or pr_th["max_increase"] > base_th["max_increase"]
    ):
        problems.append(f"ratchet:{kind_label}_max_increase_raised")
    if base_th.get("no_significant_drop") and not pr_th.get("no_significant_drop"):
        problems.append(f"ratchet:{kind_label}_no_significant_drop_dropped")
    return problems


def _check_spec_ratchet(spec: dict, base_spec: dict) -> list[str]:
    """Ensure thresholds, slices, seeds, and confidence are not loosened on the same eval set."""
    same_ver = spec.get("eval_set_version") == base_spec.get("eval_set_version")
    same_eval_set = bool(base_spec.get("eval_set")) and spec.get("eval_set") == base_spec.get("eval_set")
    if not (same_ver or same_eval_set):
        return []

    problems: list[str] = []
    if not same_ver:
        problems.append("ratchet:eval_set_version_changed_with_same_eval_set")

    base_metrics = {m["id"]: m for m in (base_spec.get("metrics") or [])}
    pr_metrics = {m["id"]: m for m in (spec.get("metrics") or [])}
    for mid, bm in base_metrics.items():
        if mid not in pr_metrics:
            problems.append(f"ratchet:metric_removed:{mid}")
            continue
        pm = pr_metrics[mid]
        problems.extend(_ratchet_entry(f"metric:{mid}", bm, pm, bm.get("threshold") or {}, pm.get("threshold") or {}))

    base_slices = {(s.get("name"), s.get("metric")): s for s in (base_spec.get("slices") or [])}
    pr_slices = {(s.get("name"), s.get("metric")): s for s in (spec.get("slices") or [])}
    for key, bs_entry in base_slices.items():
        sname, smetric = key
        if key not in pr_slices:
            problems.append(f"ratchet:slice_removed:{sname}/{smetric}")
            continue
        ps_entry = pr_slices[key]
        problems.extend(_ratchet_entry(f"slice:{sname}/{smetric}", bs_entry, ps_entry, bs_entry, ps_entry))

    if base_spec.get("seeds") is not None and spec.get("seeds") != base_spec.get("seeds"):
        problems.append("ratchet:seeds_changed")
    base_bs = base_spec.get("bootstrap") or {}
    pr_bs = spec.get("bootstrap") or {}
    if "confidence" in base_bs and pr_bs.get("confidence") != base_bs["confidence"]:
        problems.append("ratchet:bootstrap_confidence_changed")
    return problems


def _check_summary_vs_rows(
    pr_rows: list[dict], pr_metrics: dict, valid_graded_ids: list[str], spec: dict
) -> list[str]:
    """Recompute aggregate metrics from rows and reject mismatched summary metrics."""
    has_cost = all("cost" in r for r in pr_rows)
    if has_cost and any(
        isinstance(r["cost"], bool) or not isinstance(r["cost"], (int, float)) or not math.isfinite(r["cost"])
        for r in pr_rows
    ):
        return ["invalid_row_cost"]
    rows_for_agg = pr_rows if has_cost else [{**r, "cost": 0.0} for r in pr_rows]
    recomputed = aggregate(rows_for_agg, valid_graded_ids, k_values=spec.get("pass_k", []))
    problems: list[str] = []
    for k, exp_v in recomputed.items():
        if k == "cost_per_success" and not has_cost:
            continue
        if k not in pr_metrics:
            continue
        got_v = pr_metrics[k]
        if exp_v is None or got_v is None:
            continue
        if isinstance(got_v, bool) or not isinstance(got_v, (int, float)):
            problems.append(f"summary_invalid_type:{k}={got_v!r}")
            continue
        if abs(float(got_v) - float(exp_v)) > 1e-3:
            problems.append(f"summary_mismatch:{k}={got_v} != rows_aggregate={exp_v}")
    return problems


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    failures = pr.get("evaluator_failures")
    if "evaluator_failures" in pr and not isinstance(failures, list):
        problems.append("evaluator_failures_invalid")
    elif failures:
        problems.append(f"evaluator_failures={len(failures)}")

    pr_metrics = pr.get("metrics")
    if not isinstance(pr_metrics, dict):
        problems.append("missing_or_invalid_metrics")
        pr_metrics = {}
    base_metrics = base.get("metrics") if isinstance(base.get("metrics"), dict) else {}
    nan_or_inf = False
    for k, v in pr_metrics.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool) and not math.isfinite(v):
            problems.append(f"metric:{k}_not_finite")
            nan_or_inf = True
    for m in spec.get("metrics") or []:
        mid = m["id"]
        if mid not in pr_metrics:
            if m.get("blocking") or mid in GRADERS or mid in base_metrics:
                problems.append(f"metric:{mid}_missing")
        elif pr_metrics[mid] is None and (m.get("blocking") or mid in GRADERS):
            problems.append(f"metric:{mid}_is_none")

    m_pr = pr.get("manifest") or {}
    pr_rows = pr.get("rows")
    if not isinstance(pr_rows, list):
        problems.append("missing_or_invalid_rows")
        pr_rows = []
    base_rows = base.get("rows") if isinstance(base.get("rows"), list) else []

    manifest_seeds = m_pr.get("seeds") or []
    expected_rows = int(m_pr.get("items") or 0) * len(manifest_seeds)
    if len(pr_rows) != expected_rows:
        problems.append(f"row_count={len(pr_rows)} != manifest_expected={expected_rows}")

    pr_pairs = [(r.get("item_id"), r.get("seed")) for r in pr_rows]
    base_pairs = [(r.get("item_id"), r.get("seed")) for r in base_rows]
    seen_pairs: set[tuple[Any, Any]] = set()
    dup_count = 0
    for pair in pr_pairs:
        if pair in seen_pairs:
            dup_count += 1
        seen_pairs.add(pair)
    if dup_count:
        problems.append(f"duplicate_rows={dup_count}")

    if set(pr_pairs) != set(base_pairs) or len(pr_rows) != len(base_rows):
        problems.append("item_seed_set_mismatch")

    pr_item_ids = {r.get("item_id") for r in pr_rows}
    pr_seeds = {r.get("seed") for r in pr_rows}
    if m_pr.get("items") != len(pr_item_ids):
        problems.append(f"manifest_items={m_pr.get('items')} != unique_items={len(pr_item_ids)}")
    if len(set(manifest_seeds)) != len(manifest_seeds) or set(manifest_seeds) != pr_seeds:
        problems.append(f"manifest_seeds={manifest_seeds} != row_seeds={sorted(pr_seeds, key=str)}")

    graded_ids = [
        m["id"]
        for m in (spec.get("metrics") or [])
        if m["id"] in GRADERS or any(m["id"] in r for r in base_rows)
    ]
    row_bad = False
    bad_cells: list[str] = []
    for r in pr_rows:
        for mid in graded_ids:
            rv = r.get(mid)
            if rv is None or not isinstance(rv, bool):
                row_bad = True
                cell = f"{r.get('item_id')}@{r.get('seed')}:{mid}={rv!r}"
                if cell not in bad_cells:
                    bad_cells.append(cell)
    if bad_cells:
        preview = ", ".join(bad_cells[:5])
        suffix = f" (+{len(bad_cells) - 5} more)" if len(bad_cells) > 5 else ""
        problems.append(f"invalid_row_metrics: {preview}{suffix}")

    base_slices = {
        (r.get("item_id"), r.get("seed")): sorted(r.get("slices") or [])
        for r in base_rows
    }
    for r in pr_rows:
        pair = (r.get("item_id"), r.get("seed"))
        if pair in base_slices and sorted(r.get("slices") or []) != base_slices[pair]:
            problems.append(f"slice_tags_tampered:{pair[0]}@{pair[1]}")

    if not row_bad and not nan_or_inf and pr_rows:
        valid_graded_ids = [
            mid for mid in graded_ids if all(isinstance(r.get(mid), bool) for r in pr_rows)
        ]
        problems.extend(_check_summary_vs_rows(pr_rows, pr_metrics, valid_graded_ids, spec))

    if base_spec is not None:
        problems.extend(_check_spec_ratchet(spec, base_spec))

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, mid = s["name"], s["metric"]
        a = per_item(pr, mid, slice_name=name)
        b = per_item(base, mid, slice_name=name)
        val = round(sum(a.values()) / len(a), 4) if a else None
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        else:
            if "max" in s and val > s["max"]:
                verdict = "fail"
            if "min" in s and val < s["min"]:
                verdict = "fail"
        if s.get("no_significant_drop") and val is not None:
            keys = sorted(set(a) & set(b))
            if keys:
                kw: dict[str, Any] = {
                    "n_resamples": bs.get("n_resamples", 1000),
                    "rng": bs.get("rng", 2027),
                }
                if bs.get("confidence", 0.95) != 0.95:
                    kw["confidence"] = bs["confidence"]
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys], **kw)
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
            else:
                verdict = "missing"
        tag = f"slice:{name}/{mid}"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(tag)
        th = {k: s[k] for k in ("min", "max", "no_significant_drop") if k in s}
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        lines.append(f"  {tag:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
