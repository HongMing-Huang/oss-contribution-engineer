#!/usr/bin/env python3
"""retrieval_eval.py — retrieval evaluation layer (separate from patch evaluation).

Given a repository and a task set (JSONL: id, task_type, query, anchor_files,
given_files, gold_files, optional gold_regions), run the retrieval router per task and
compute, per arm:
  - Recall@K, MRR (retrieval quality — rank-based, packing-independent)
  - BCY@B for B in 4k/8k/16k (packing quality — budgeted context yield)
  - final packet tokens, files delivered, gold files displaced by packing (eval-only)
  - retrieval latency (from the router's routing_decision)

`--regret` adds the ROUTING REGRET diagnostic: for each sample, compare the
policy-routed strategy against the best single arm tested. Evaluation-only — the
production router never sees gold labels.

Scope discipline (Agent Retrieval Bench): claims are component-level — retrieval
quality changes acquired context and its cost; we do NOT claim end-to-end patch
causality. No calibrated abstention scores are produced. Embedding arm stays
UNAVAILABLE by design (no model dependency).

Exit codes: 0 ok, 2 usage, 3 error.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import retrieval_router as rr  # noqa: E402

ARM_SIGNALS = {
    "lexical-only": ["lexical"],
    "repomap-only": ["repomap"],
    "symbol+test-only": ["symbol", "test"],
    # "router" runs the workflow policy (no signal override)
}


def bcyn(ranked_paths: list[str], gold: set[str], corpus_files: dict[str, str],
         budget_tokens: int) -> float:
    """Budgeted Context Yield: fraction of gold files exposed after packing ranked
    files (whole files, estimated tokens) into the budget. Oversized single files
    are skipped by the packer (cannot fit even alone)."""
    used = 0
    exposed: set[str] = set()
    for p in ranked_paths:
        t = len(corpus_files.get(p, "")) // 4
        if t > budget_tokens:
            continue
        if used + t > budget_tokens:
            break
        used += t
        exposed.add(p)
        if gold and gold.issubset(exposed):
            break
    if not gold:
        return 0.0
    return len(gold & exposed) / len(gold)


def region_metrics(delivered: list[str], gold_regions: list[dict],
                   corpus_files: dict[str, str]) -> dict:
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
    }


def run_arm(corpus, repo: Path, task: dict, arm: str, rank_depth: int) -> dict:
    signals = ARM_SIGNALS.get(arm)
    t0 = time.perf_counter()
    report = rr.route(str(repo), task["query"], task.get("task_type", "issue2code"),
                      signals, rank_depth, 2, 50)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return report, elapsed_ms


def evaluate_arm_tasks(corpus, repo: Path, tasks: list[dict], arm: str,
                       ks: list[int], budgets: list[int], rank_depth: int) -> list[dict]:
    rows = []
    for task in tasks:
        gold = set(task.get("gold_files", [])) - set(task.get("given_files", []))
        report, elapsed_ms = run_arm(corpus, repo, task, arm, rank_depth)
        ranked = [c["path"] for c in report["candidates"]]
        mrr = 0.0
        for i, p in enumerate(ranked, 1):
            if p in gold:
                mrr = 1.0 / i
                break
        row = {
            "id": task["id"], "task_type": task.get("task_type", "issue2code"),
            "arm": arm,
            "mrr": round(mrr, 3),
            "recall": {("@%d" % k): round(len(gold & set(ranked[:k])) / len(gold), 3)
                       if gold else 0.0 for k in ks},
            "bcy": {"@%d" % b: round(bcyn(ranked, gold, corpus.files, b), 3)
                    for b in budgets},
            "files_delivered": min(len(ranked), rank_depth),
            "packet_tokens_est": sum(len(corpus.files.get(p, "")) // 4
                                     for p in ranked[:rank_depth]),
            "latency_ms": elapsed_ms,
        }
        if gold:
            packed_gold = len(gold & set(ranked)) and sum(
                1 for g in gold if g in ranked)  # reached by retrieval
            exposed = set()
            used = 0
            for p in ranked:
                t = len(corpus.files.get(p, "")) // 4
                if t > budgets[-1]:
                    continue
                if used + t > budgets[-1]:
                    break
                used += t
                exposed.add(p)
            row["gold_displaced_by_packing"] = len((gold & set(ranked)) - exposed)
        if task.get("gold_regions"):
            row.update(region_metrics(ranked[:rank_depth], task["gold_regions"],
                                      corpus.files))
        rows.append(row)
    return rows


def agg(rows: list[dict], ks: list[int], budgets: list[int]) -> dict:
    out: dict = {}
    if not rows:
        return out
    out["MRR"] = round(statistics.mean(r["mrr"] for r in rows), 3)
    for k in ks:
        out["Recall@%d" % k] = round(statistics.mean(r["recall"]["@%d" % k] for r in rows), 3)
    for b in budgets:
        out["BCY@%d" % b] = round(statistics.mean(r["bcy"]["@%d" % b] for r in rows), 3)
    out["packet_tokens_est_mean"] = round(statistics.mean(r["packet_tokens_est"] for r in rows), 1)
    out["files_delivered_mean"] = round(statistics.mean(r["files_delivered"] for r in rows), 1)
    out["latency_ms_mean"] = round(statistics.mean(r["latency_ms"] for r in rows), 1)
    out["gold_displaced_by_packing_total"] = sum(r.get("gold_displaced_by_packing", 0)
                                                 for r in rows)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Retrieval evaluation over a task JSONL.")
    ap.add_argument("repo")
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--top-k", default="5,10,20")
    ap.add_argument("--budgets", default="4000,8000,16000")
    ap.add_argument("--rank-depth", type=int, default=20)
    ap.add_argument("--arms", default="router",
                    help="comma set: router,lexical-only,repomap-only,symbol+test-only "
                         "(multiple arms enable the routing-regret diagnostic)")
    ap.add_argument("--regret-budget", type=int, default=8000,
                    help="budget at which routing regret is computed (default 8000)")
    ap.add_argument("--config-out", help="also write full per-task rows to this JSON")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print("error: %s is not a directory" % repo, file=sys.stderr)
        return 3
    ks = [int(x) for x in args.top_k.split(",")]
    budgets = [int(x) for x in args.budgets.split(",")]
    arms = [a.strip() for a in args.arms.split(",")]
    for a in arms:
        if a != "router" and a not in ARM_SIGNALS:
            print("error: unknown arm %s" % a, file=sys.stderr)
            return 2

    corpus = rr.Corpus(repo)
    tasks = [json.loads(l) for l in Path(args.tasks).read_text().splitlines() if l.strip()]

    all_rows: list[dict] = []
    for arm in arms:
        all_rows.extend(evaluate_arm_tasks(corpus, repo, tasks, arm, ks, budgets, rank_depth=args.rank_depth))

    # per-arm aggregate
    summary = {"per_arm": {}, "per_task_type_per_arm": {}}
    for arm in arms:
        rows = [r for r in all_rows if r["arm"] == arm]
        summary["per_arm"][arm] = agg(rows, ks, budgets)

    # routing regret (only meaningful with router + at least one comparison arm)
    regret: dict | None = None
    if "router" in arms and len(arms) > 1:
        by_task: dict[str, dict[str, float]] = {}
        for r in all_rows:
            by_task.setdefault(r["id"], {})[r["arm"]] = r["bcy"]["@%d" % args.regret_budget]
        per_sample = []
        for tid, arms_bcy in by_task.items():
            if "router" not in arms_bcy:
                continue
            best_arm = max(arms_bcy, key=arms_bcy.get)
            regret_val = round(arms_bcy[best_arm] - arms_bcy["router"], 3)
            per_sample.append({"id": tid, "router_bcy": arms_bcy["router"],
                               "best_arm": best_arm, "best_bcy": arms_bcy[best_arm],
                               "regret": regret_val})
        per_sample.sort(key=lambda s: -s["regret"])
        regret = {
            "budget": args.regret_budget,
            "mean_regret": round(statistics.mean(s["regret"] for s in per_sample), 3)
            if per_sample else 0.0,
            "samples_with_regret": sum(1 for s in per_sample if s["regret"] > 0),
            "n": len(per_sample),
            "worst_samples": per_sample[:5],
            "note": "ROUTING REGRET = best tested arm BCY - policy-routed BCY; "
                    "evaluation-only diagnostic, the production router never sees gold",
        }

    by_type_arm: dict[tuple, list] = {}
    for r in all_rows:
        by_type_arm.setdefault((r["task_type"], r["arm"]), []).append(r)
    for (t, a), rows in sorted(by_type_arm.items()):
        summary["per_task_type_per_arm"]["%s/%s" % (t, a)] = agg(rows, ks, budgets)

    print(json.dumps({
        "repository": str(repo), "tasks": len(tasks), "arms": arms,
        "rank_depth": args.rank_depth, "budgets": budgets,
        "summary": summary, "routing_regret": regret,
        "rows": all_rows,
        "scope_note": "component-level retrieval/packing metrics; not end-to-end "
                      "patch causality; token counts are estimates (chars/4); "
                      "embedding arm UNAVAILABLE by design",
    }, indent=2))
    if args.config_out:
        Path(args.config_out).write_text(json.dumps(
            {"routing_policies": rr.ROUTING_POLICIES, "rows": all_rows,
             "summary": summary, "routing_regret": regret}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
