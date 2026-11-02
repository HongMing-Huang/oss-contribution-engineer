#!/usr/bin/env python3
"""v8_ablate.py — V8 mechanism ablations from existing bench JSONL rows.

Produces an ablation summary (markdown + JSON) comparing:
  graph:        arm C (no graph/structural artifacts) vs arm D (full pipeline)
  symbol:       arm B (symbol-only) vs its absence — interpretive, plus C's
                symbol_backend family visible via arm C ranks
  two-stage:    D's spans (two-stage output) vs C's lack of spans
  aoci:         runs/bench-aoci-on.jsonl (fixture cognition) vs D rows without
  cache:        arm W (warm corpus cache) vs D cold

No single accuracy score is computed; every row keeps its own metrics.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 3) if xs else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--r1", default="runs/bench-r1.jsonl")
    ap.add_argument("--r2", default="runs/bench-r2.jsonl")
    ap.add_argument("--aoci", default="runs/bench-aoci-on.jsonl")
    ap.add_argument("--out", default="runs/ablations.json")
    args = ap.parse_args()
    r1 = load(Path(args.r1))
    r2 = load(Path(args.r2))
    aoci = load(Path(args.aoci)) if Path(args.aoci).exists() else []
    by = lambda rows: {(r["task_id"], r["arm"]): r for r in rows}

    def agg(rows, arm, field):
        return mean([r.get(field) for r in rows if r["arm"] == arm])

    out: dict = {"ablation_type": "V8_MECHANISM_ABLATIONS"}

    # graph ablation (r1: identical pipeline code except graph off in C)
    out["graph_expansion"] = {
        "config": "C = router without graph expansion (r1 frozen code); "
                  "D = full pipeline with graph + structural artifacts",
        "C_mean_file_recall": agg(r1, "C", "gold_file_recall"),
        "D_mean_file_recall": agg(r1, "D", "gold_file_recall"),
        "C_mean_latency_ms": agg(r1, "C", "latency_ms"),
        "D_mean_latency_ms": agg(r1, "D", "latency_ms"),
        "per_task_delta": {},
    }
    b1 = by(r1)
    for (tid, arm), row in b1.items():
        if arm != "D":
            continue
        c = b1.get((tid, "C"))
        if c:
            out["graph_expansion"]["per_task_delta"][tid] = {
                "D_minus_C_recall": round(
                    (row.get("gold_file_recall") or 0) - (c.get("gold_file_recall") or 0), 3)}

    # two-stage (spans exist only via two-stage in D)
    out["two_stage_localization"] = {
        "config": "TWO_STAGE_LOCALIZATION_EXPERIMENT: D delivers function spans "
                  "from the two-stage skeleton; C delivers file pointers only; "
                  "span recall is only measurable on D",
        "D_mean_span_recall": agg(r1, "D", "gold_span_recall"),
        "D_mean_span_precision": agg(r1, "D", "span_precision"),
        "C_span_recall": None,
        "note": "SUFFICIENT_EVIDENCE is an internal stopping decision, not "
                "correctness evidence; span precision carries the noise signal",
    }

    # symbol backend (B-only arm; C/D consume the spans artifact)
    out["symbol_backend"] = {
        "config": "B = symbol search only; A = grep baseline",
        "B_mean_file_recall": agg(r1, "B", "gold_file_recall"),
        "A_mean_file_recall": agg(r1, "A", "gold_file_recall"),
        "B_mean_latency_ms": agg(r1, "B", "latency_ms"),
        "note": "python-ast covers Python tasks only; TS/Go/Rust tasks "
                "honestly return nothing from the symbol arm",
    }

    # AOCI cognition (fixture, click tasks)
    if aoci:
        off = {(r["task_id"]): r for r in (r1 + r2) if r["arm"] == "D"
               and "click" in r["task_id"]}
        pairs = {}
        for r in aoci:
            off_row = off.get(r["task_id"])
            if off_row:
                pairs[r["task_id"]] = {
                    "with_aoci": {"recall": r.get("gold_file_recall"),
                                  "tokens": r.get("context_tokens"),
                                  "latency_ms": r.get("latency_ms")},
                    "without_aoci": {"recall": off_row.get("gold_file_recall"),
                                     "tokens": off_row.get("context_tokens"),
                                     "latency_ms": off_row.get("latency_ms")}}
        out["aoci_cognition"] = {
            "config": "fixture AOCI_FILE volumes (mechanical placeholder F lines) "
                      "vs none — measures whether a fixture-grade cognition map "
                      "changes routing, NOT whether AOCI helps real work",
            "pairs": pairs,
            "verdict_note": "fixture cognition is not model-authored; no benefit "
                            "may be claimed from this cell",
        }

    # warm corpus cache (r2 W vs r2 D)
    out["corpus_cache"] = {
        "config": "W = route() through router_cache (warm) vs D cold (r2)",
        "D_cold_mean_latency_ms": agg(r2, "D", "latency_ms"),
        "W_warm_mean_latency_ms": agg(r2, "W", "latency_ms"),
        "D_cold_mean_recall": agg(r2, "D", "gold_file_recall"),
        "W_warm_mean_recall": agg(r2, "W", "gold_file_recall"),
    }

    Path(args.out).write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2)[:2400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
