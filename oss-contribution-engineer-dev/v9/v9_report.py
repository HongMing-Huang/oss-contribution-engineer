#!/usr/bin/env python3
"""v9_report.py — V9 round summary with p50/p95/max (never mean-only)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def pct(xs, p):
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round((len(xs) - 1) * p))))
    return xs[k]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", default="runs/v9-r1.jsonl")
    ap.add_argument("--ledger", default=str(Path(__file__).parent / "EXPERIMENT-LEDGER.md"))
    args = ap.parse_args()
    rows = [json.loads(l) for l in Path(args.jsonl).read_text().splitlines() if l.strip()]
    arms = sorted({r["arm"] for r in rows})
    out = ["", "## V9 round summary (blind tasks, equal span units, snapshot reuse)", "",
           "| arm | n | file_recall | span_recall | span_prec | tok p50 | lat p50 | lat p95 | lat max |",
           "|---|---|---|---|---|---|---|---|---|"]
    for arm in arms:
        rs = [r for r in rows if r["arm"] == arm]
        fr = [r["gold_file_recall"] for r in rs if r["gold_file_recall"] is not None]
        sr = [r["gold_span_recall"] for r in rs if r["gold_span_recall"] is not None]
        sp = [r["span_precision"] for r in rs if r["span_precision"] is not None]
        tk = [r["context_tokens"] or 0 for r in rs]
        lat = [r["latency_ms"] for r in rs]
        f = lambda xs: round(sum(xs) / len(xs), 3) if xs else None
        out.append("| %s | %d | %s | %s | %s | %d | %d | %d | %d |" % (
            arm, len(rs), f(fr), f(sr), f(sp),
            pct(tk, 0.5), pct(lat, 0.5), pct(lat, 0.95), max(lat)))
    # stage percentiles for the full arm (§3: per-stage, not just means)
    for arm in ("D",):
        rs = [r for r in rows if r["arm"] == arm]
        stages: dict[str, list[int]] = {}
        for r in rs:
            for k, v in (r.get("stage_ms") or {}).items():
                stages.setdefault(k, []).append(v)
        out += ["", "### %s stage latencies (ms, p50/p95/max)" % arm, "",
                "| stage | p50 | p95 | max |", "|---|---|---|---|"]
        for k in sorted(stages):
            v = stages[k]
            out.append("| %s | %d | %d | %d |" % (k, pct(v, 0.5), pct(v, 0.95), max(v)))
    Path(args.ledger).open("a").write("\n".join(out) + "\n")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
