#!/usr/bin/env python3
"""retrieval_eval.py — retrieval evaluation layer (separate from patch evaluation).

Given a repository and a task set (JSONL: id, task_type, query, anchor_files,
given_files, gold_files, optional gold_regions), run the retrieval router per task and
compute: Recall@K, MRR, gold coverage under token budget (BCY@B), precision@K, and —
when gold_regions are provided — region coverage and useful/delivered line ratio.
Results are broken down per task type. Signal ablation via --signals (e.g. compare
lexical-only vs the full hybrid). Token counts are estimates (chars/4) and labeled so.

Scope discipline (Agent Retrieval Bench): claims are component-level — retrieval
quality changes acquired context and its cost; we do NOT claim end-to-end patch
causality. No calibrated abstention scores are produced (ARB negative result).

Exit codes: 0 ok, 2 usage, 3 error.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import retrieval_router as rr  # noqa: E402


def bcyn(ranked_paths: list[str], gold: set[str], corpus_files: dict[str, str], budget_tokens: int) -> float:
    """Budgeted Context Yield: fraction of gold files exposed after packing
    ranked files (whole files, estimated tokens) into the budget."""
    used = 0
    exposed = set()
    skipped_oversized = []
    for p in ranked_paths:
        t = len(corpus_files.get(p, "")) // 4
        if t > budget_tokens:
            skipped_oversized.append(p)  # cannot fit even alone; packing moves on
            continue
        if used + t > budget_tokens:
            break
        used += t
        exposed.add(p)
        if gold and gold.issubset(exposed):
            break
    if not gold:
        return 0.0
    if skipped_oversized:
        bcyn.last_skipped = skipped_oversized
    return len(gold & exposed) / len(gold)


def region_metrics(delivered: list[str], gold_regions: list[dict],
                   corpus_files: dict[str, str]) -> dict:
    """gold_regions: [{path, lines: 'a-b'}]. Delivered files are read whole here for
    line accounting; ratios are estimates."""
    total_gold_lines = delivered_gold_lines = 0
    regions_hit = 0
    for g in gold_regions:
        a, _, b = g["lines"].partition("-")
        a, b = int(a), int(b or a)
        total_gold_lines += b - a + 1
        if g["path"] in delivered:
            regions_hit += 1
            delivered_gold_lines += b - a + 1
    delivered_lines = sum(len(corpus_files.get(p, "").splitlines()) for p in delivered)
    return {
        "region_coverage": round(regions_hit / len(gold_regions), 3) if gold_regions else None,
        "useful_lines_over_delivered": round(delivered_gold_lines / delivered_lines, 3)
        if delivered_lines else 0.0,
        "note": "delivered = whole file when a file is delivered; span-level delivery "
                "is a packing decision, approximated here",
    }


def evaluate(args) -> int:
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print("error: %s is not a directory" % repo, file=sys.stderr)
        return 3
    corpus = rr.Corpus(repo)
    tasks = []
    for line in Path(args.tasks).read_text().splitlines():
        if line.strip():
            tasks.append(json.loads(line))

    ks = [int(x) for x in args.top_k.split(",")]
    per_task_rows = []
    for task in tasks:
        gold = set(task.get("gold_files", [])) - set(task.get("given_files", []))
        report = rr.route(str(repo), task["query"], task.get("task_type", "issue2code"),
                          args.signals, args.rank_depth, 2, 50)
        ranked = [c["path"] for c in report["candidates"]]
        mrr = 0.0
        for i, p in enumerate(ranked, 1):
            if p in gold:
                mrr = 1.0 / i
                break
        row = {
            "id": task["id"], "task_type": task.get("task_type", "issue2code"),
            "gold": sorted(gold), "ranked_top": ranked[:5],
            "mrr": round(mrr, 3),
            "recall": {("@" + str(k)): round(
                len(gold & set(ranked[:k])) / len(gold), 3) if gold else 0.0 for k in ks},
            "bcy": {"@%d" % args.budget_tokens: round(
                bcyn(ranked, gold, corpus.files, args.budget_tokens), 3)},
            "delivered_tokens_est": sum(len(corpus.files.get(p, "")) // 4
                                        for p in ranked[:args.rank_depth]),
        }
        if gold and ranked[:ks[-1]]:
            hit_k = ks[-1]
            row["precision@%d" % hit_k] = round(
                len(gold & set(ranked[:hit_k])) / min(hit_k, len(ranked)), 3)
        if task.get("gold_regions"):
            row.update(region_metrics(ranked[:args.rank_depth], task["gold_regions"], corpus.files))
        if args.gold_in_top and gold and not (gold & set(ranked)):
            row["note"] = "gold missed entirely — inspect routing"
        per_task_rows.append(row)

    def agg(rows):
        out = {}
        for m in ("mrr",):
            vals = [r[m] for r in rows]
            out["MRR"] = round(statistics.mean(vals), 3) if vals else 0.0
        for k in ks:
            vals = [r["recall"]["@%d" % k] for r in rows]
            out["Recall@%d" % k] = round(statistics.mean(vals), 3) if vals else 0.0
        vals = [r["bcy"]["@%d" % args.budget_tokens] for r in rows]
        out["BCY@%d" % args.budget_tokens] = round(statistics.mean(vals), 3) if vals else 0.0
        out["delivered_tokens_est_mean"] = round(
            statistics.mean([r["delivered_tokens_est"] for r in rows]), 1) if rows else 0
        return out

    by_type: dict[str, list] = {}
    for r in per_task_rows:
        by_type.setdefault(r["task_type"], []).append(r)
    summary = {"aggregate": agg(per_task_rows), "per_task_type": {}}
    for t, rows in sorted(by_type.items()):
        summary["per_task_type"][t] = agg(rows)

    print(json.dumps({
        "repository": str(repo), "tasks": len(per_task_rows),
        "signals": args.signals or "all (hybrid)",
        "rank_depth": args.rank_depth, "budget_tokens": args.budget_tokens,
        "summary": summary,
        "rows": per_task_rows,
        "scope_note": "component-level retrieval metrics; not end-to-end patch causality; "
                      "token counts are estimates (chars/4)",
    }, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Retrieval evaluation over a task JSONL.")
    ap.add_argument("repo")
    ap.add_argument("--tasks", required=True, help="tasks JSONL")
    ap.add_argument("--top-k", default="5,10,20")
    ap.add_argument("--budget-tokens", type=int, default=8000)
    ap.add_argument("--rank-depth", type=int, default=20,
                    help="candidates the router returns per task")
    ap.add_argument("--signals", help="comma subset for ablation, e.g. lexical,path")
    ap.add_argument("--gold-in-top", action="store_true")
    args = ap.parse_args()
    if args.signals:
        args.signals = [s.strip() for s in args.signals.split(",")]
    return evaluate(args)


if __name__ == "__main__":
    raise SystemExit(main())
