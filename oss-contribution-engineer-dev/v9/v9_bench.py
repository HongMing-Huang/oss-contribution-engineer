#!/usr/bin/env python3
"""v9_bench.py — V9 benchmark: blind tasks, equal units, snapshot reuse.

Differences from the V8 runner (all evidence-driven, see V9 goal):
  §1  task text comes from v9_tasks.json — verbatim pre-fix source material
      (issue/PR-title), never manual root-cause summaries.
  §3  one task-scoped repository snapshot per run: the symbol graph artifact
      and the warm corpus are built ONCE and reused by the router AND the
      two-stage localizer (localize(stage1_result=...) skips its internal
      re-route; graph artifact persists across arms). Every stage is timed
      separately and the report carries p50/p95/max — never only a mean.
  §5  the two-stage exits are STOPPED_EVIDENCE_FOUND / STOPPED_BUDGET /
      STOPPED_NO_EVIDENCE with a structured stop_evidence record.
  §6  every arm delivers LINE/SPAN context through one inspection-span protocol
      (matching lines ±5, capped; identical token estimator chars/4 and a hard
      400-line budget), so whole-file arms are never compared against span arms.
  §7  baseline A is a competent workflow: exact identifier search → inspect
      nearby source → import-linked tests → one bounded follow-up search.

Arms: A2 (strong grep) · B (symbol-only) · C (router, no graph) ·
      D (full pipeline + two-stage) · W (D through the warm corpus cache).

Usage: python3 v9_bench.py --arms A2,B,C,D --out runs/v9-r1.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_SCRIPTS = HERE.parent.parent / "oss-contribution-engineer" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

import retrieval_router as rr          # noqa: E402
import router_cache                    # noqa: E402
import symbol_backend as sb            # noqa: E402
import localize_two_stage as loc       # noqa: E402

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
INSPECT_WINDOW = 5          # lines around a matching line
INSPECT_CAP = 60            # max delivered lines per file (span protocol)
HEAD_LINES = 40             # fallback when an arm selects a file with no hit
LINE_BUDGET = 400           # hard equal budget across arms
TEST_WINDOW = 5


def est_tokens(text: str) -> int:
    return len(text) // 4


def query_identifiers(task: dict) -> list[str]:
    raw = task["query"] + " " + task.get("body_excerpt", "")
    seen, out = set(), []
    for t in sorted(TOKEN_RE.findall(raw), key=lambda x: (-len(x), x.lower())):
        k = t.lower()
        if k not in seen:
            seen.add(k)
            out.append(t)
        if len(out) >= 6:
            break
    return out


def _all_files(repo: Path):
    for p in sorted(repo.rglob("*")):
        rel = p.relative_to(repo)
        if any(part in rr.SKIP_DIRS or part.startswith(".") for part in rel.parts[:-1]):
            continue
        if p.is_file() and not p.name.startswith(".") and p.suffix in {
                ".py", ".go", ".rs", ".ts", ".js", ".mjs", ".cjs", ".tsx", ".jsx"} \
                and p.stat().st_size <= rr.MAX_FILE_BYTES:
            yield p


def inspection_spans(lines: list[str], ids: list[str]) -> tuple[list[tuple[int, int]], bool]:
    """§6 protocol: matching lines ±5, merged, capped at INSPECT_CAP; False when
    nothing matched (caller may fall back to the head-lines protocol)."""
    hit_lines = [i for i, ln in enumerate(lines, 1)
                 if any(i.lower() in ln.lower() for i in ids)]
    if not hit_lines:
        return [], False
    ranges: list[tuple[int, int]] = []
    for h in hit_lines:
        a, b = max(1, h - INSPECT_WINDOW), min(len(lines), h + INSPECT_WINDOW)
        if ranges and a <= ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], b))
        else:
            ranges.append((a, b))
    merged: list[tuple[int, int]] = []
    used = 0
    for a, b in ranges:
        if used + (b - a + 1) > INSPECT_CAP:
            break
        merged.append((a, b))
        used += b - a + 1
    return merged, True


def deliver_spans(repo: Path, files: list[str], ids: list[str],
                  window: int = INSPECT_WINDOW) -> tuple[list[tuple], int, int]:
    """Equal-unit delivery for every arm: file list → inspection spans under a
    shared line budget. Returns (spans, delivered_lines, token_estimate)."""
    spans: list[tuple] = []
    total_lines = 0
    tokens = 0
    for rel in files:
        p = repo / rel
        if not p.exists():
            continue
        lines = p.read_text(errors="replace").splitlines()
        ranges, matched = inspection_spans(lines, ids)
        if not matched:
            ranges = [(1, min(HEAD_LINES, len(lines)))]
        for a, b in ranges:
            if total_lines + (b - a + 1) > LINE_BUDGET:
                return spans, total_lines, tokens
            spans.append((rel, a, b))
            total_lines += b - a + 1
            tokens += est_tokens("\n".join(lines[a - 1:b]))
    return spans, total_lines, tokens


# ---------------------------------------------------------------- snapshot (§3)
class Snapshot:
    """One task-scoped repository snapshot reused by every stage: warm corpus,
    symbol graph artifact, spans index. Built once; every stage reads it."""

    def __init__(self, repo: Path):
        self.stage_ms: dict[str, int] = {}
        t0 = time.monotonic()
        self.corpus = router_cache.build_corpus(repo)     # scan+tokenize+cache
        self.stage_ms["scan_tokenize"] = int((time.monotonic() - t0) * 1000)
        t0 = time.monotonic()
        self.spans_art = sb.build_index(repo, "python-ast")  # symbol indexing
        (repo / sb.ARTIFACT).parent.mkdir(parents=True, exist_ok=True)
        (repo / sb.ARTIFACT).write_text(json.dumps(self.spans_art))
        self.stage_ms["symbol_index"] = int((time.monotonic() - t0) * 1000)
        t0 = time.monotonic()
        self.graph = sb.load_graph(repo) or sb.build_graph(repo)
        if not sb.load_graph(repo):
            (repo / sb.GRAPH_ARTIFACT).parent.mkdir(parents=True, exist_ok=True)
            (repo / sb.GRAPH_ARTIFACT).write_text(json.dumps(self.graph))
        self.stage_ms["graph_build"] = int((time.monotonic() - t0) * 1000)


# ---------------------------------------------------------------- arms
def arm_a2(repo: Path, task: dict, snap: Snapshot) -> dict:
    """§7 competent grep workflow (deterministic, bounded)."""
    stage: dict[str, int] = {}
    ids = query_identifiers(task)
    t0 = time.monotonic()
    texts: dict[str, list[str]] = {}
    counts: dict[str, int] = {}
    for p in _all_files(repo):
        rel = p.relative_to(repo).as_posix()
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        low = text.lower()
        c = sum(low.count(i.lower()) for i in ids[:3])
        if c:
            counts[rel] = c
        texts[rel] = text.splitlines()
    stage["search_exact"] = int((time.monotonic() - t0) * 1000)
    ranked = sorted(counts, key=lambda k: -counts[k])[:4]
    ops = 2
    files = ranked
    t1 = time.monotonic()
    tests = []
    for rel in files:
        stem = rr.module_stem(rel)
        for cand in texts:
            if rr.is_test_path(cand) and stem and stem in cand:
                tests.append(cand)
    stage["related_tests"] = int((time.monotonic() - t1) * 1000)
    ops += 1
    # one bounded follow-up: second identifier drawn from inspected gold-adjacent code
    t2 = time.monotonic()
    follow = [f for f in ranked[1:3] if f not in files][:1]
    files = files + follow
    stage["followup_search"] = int((time.monotonic() - t2) * 1000)
    ops += 1
    spans, lines, tokens = deliver_spans(repo, files, ids)
    return {"files": files, "tests": tests[:4], "spans": spans,
            "delivered_lines": lines, "context_tokens": tokens, "ops": ops,
            "stage_ms": stage, "graph_expansions": 0,
            "backend": "grep-protocol"}


def arm_b(repo: Path, task: dict, snap: Snapshot) -> dict:
    ids = query_identifiers(task)
    t0 = time.monotonic()
    files, span_rows = [], []
    for ident in ids[:4]:
        for mode, want in (("method", ident), ("class", ident)):
            res = sb.search_api(repo, mode, want, None, None, None)
            for r in res["results"]:
                span_rows.append((r["path"], r["start_line"], r["end_line"]))
                if r["path"] not in files:
                    files.append(r["path"])
    stage = {"symbol_search": int((time.monotonic() - t0) * 1000)}
    spans, lines, tokens = deliver_spans(repo, files, ids) if not span_rows \
        else (span_rows[:40], sum(b - a + 1 for _, a, b in span_rows[:40]),
              sum(est_tokens("\n".join(
                  (repo / p).read_text(errors="replace").splitlines()[a - 1:b]))
                  for p, a, b in span_rows[:40] if (repo / p).exists()))
    return {"files": files, "tests": [], "spans": spans,
            "delivered_lines": lines, "context_tokens": tokens, "ops": 5,
            "stage_ms": stage, "graph_expansions": 0, "backend": "python-ast"}


def arm_c(repo: Path, task: dict, snap: Snapshot) -> dict:
    C_SIGNALS = ["lexical", "path", "symbol", "test", "history", "cognition",
                 "symbol_backend"]
    t0 = time.monotonic()
    report = rr.route(str(repo), task["query"] + " " + task.get("body_excerpt", "")[:400],
                      "issue2code", list(C_SIGNALS), 8, 0, 0)
    stage = {"route_nograph": int((time.monotonic() - t0) * 1000)}
    files = [c["path"] for c in report["candidates"]]
    ids = query_identifiers(task)
    spans, lines, tokens = deliver_spans(repo, files, ids)
    return {"files": files, "tests": [], "spans": spans,
            "delivered_lines": lines, "context_tokens": tokens, "ops": 1,
            "stage_ms": stage, "graph_expansions": 0,
            "backend": report["backend"]["kind"]}


def arm_d(repo: Path, task: dict, snap: Snapshot, warm: bool = False,
          expand: bool = True) -> dict:
    stage = dict(snap.stage_ms)
    if warm:
        rr.CORPUS_BUILDER = router_cache.build_corpus
    try:
        t0 = time.monotonic()
        report = rr.route(str(repo),
                          task["query"] + " " + task.get("body_excerpt", "")[:400],
                          "issue2code", None, 8, 2, 50)
        stage["route"] = int((time.monotonic() - t0) * 1000)
        files = [c["path"] for c in report["candidates"]]
        t1 = time.monotonic()
        loc_res = loc.localize(repo, task["query"] + " " + task.get("body_excerpt", "")[:400],
                               "issue2code", 3, expand=expand, stage1_result={
                                   "files": files[:loc.STAGE1_MAX_FILES],
                                   "router_backend": report["backend"]["kind"],
                                   "router_backends_used": report.get("backends", {}),
                                   "candidates_considered": len(report["candidates"]),
                                   "used_direct_class": any(
                                       c["evidence_class"] == "direct"
                                       for c in report["candidates"])})
        stage["two_stage"] = int((time.monotonic() - t1) * 1000)
    finally:
        if warm:
            rr.CORPUS_BUILDER = None
    for f in loc_res["stage1"]["files"]:
        if f not in files:
            files.append(f)
    expansions = sum(1 for c in report["candidates"]
                     if any(e["family"] == "graph" for e in c["evidence"]))
    spans = [(f["path"], f["start_line"], f["end_line"]) for f in loc_res["functions"]]
    if spans:
        lines = sum(b - a + 1 for _, a, b in spans)
        tokens = sum(est_tokens("\n".join(
            (repo / p).read_text(errors="replace").splitlines()[a - 1:b]))
            for p, a, b in spans if (repo / p).exists())
    else:
        ids = query_identifiers(task)
        spans, lines, tokens = deliver_spans(repo, files, ids)
    return {"files": files[:10], "tests": [], "spans": spans,
            "delivered_lines": lines, "context_tokens": tokens, "ops": 2,
            "stage_ms": stage, "graph_expansions": expansions,
            "backend": report["backend"]["kind"] + ("+warm" if warm else ""),
            "exit_reason": loc_res["exit_reason"],
            "span_precision_hint": None,
            "stop_evidence": loc_res.get("stop_evidence")}


# ---------------------------------------------------------------- scoring
def score(task: dict, arm: str, res: dict, snap: Snapshot) -> dict:
    gold_files = set(task["gold_prod_files"])
    gold_spans = task["gold_spans"]
    files = res.get("files", [])
    spans = res.get("spans", [])
    row = {
        "task_id": task["task_id"], "arm": arm,
        "repo_slug": task["repo_slug"], "base_sha": task["base_sha"],
        "source_level": task["source_level"],
        "gold_file_recall": round(len([f for f in files if f in gold_files])
                                  / len(gold_files), 3) if gold_files else None,
        "gold_file_hit_ranks": [files.index(f) + 1 for f in gold_files if f in files],
        "irrelevant_files": sum(1 for f in files if f not in gold_files),
        "context_tokens": res.get("context_tokens"),
        "delivered_lines": res.get("delivered_lines"),
        "ops": res.get("ops"),
        "latency_ms": sum(res.get("stage_ms", {}).values()),
        "stage_ms": res.get("stage_ms", {}),
        "graph_expansions": res.get("graph_expansions", 0),
        "backend": res.get("backend"),
        "exit_reason": res.get("exit_reason"),
    }
    if spans and gold_spans:
        want = {p: [(a, b) for a, b in rs] for p, rs in gold_spans.items()}
        gold_total = sum(b - a + 1 for rs in want.values() for a, b in rs)
        covered: set[tuple[str, int]] = set()
        delivered = in_gold = 0
        for path, a, b in spans:
            for ln in range(a, b + 1):
                delivered += 1
                if path in want and any(a0 <= ln <= b0 for a0, b0 in want[path]):
                    covered.add((path, ln))
                    in_gold += 1
        row["gold_span_recall"] = round(len(covered) / gold_total, 3) if gold_total else None
        row["span_precision"] = round(in_gold / delivered, 3) if delivered else 0.0
        row["irrelevant_lines_delivered"] = delivered - in_gold
    else:
        row["gold_span_recall"] = row["span_precision"] = None
        row["irrelevant_lines_delivered"] = None
    return row


ARMS = {"A2": arm_a2, "B": arm_b, "C": arm_c}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="A2,B,C,D")
    ap.add_argument("--tasks", default=str(HERE / "v9_tasks.json"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--task-filter", default=None)
    args = ap.parse_args()
    tasks = json.loads(Path(args.tasks).read_text())
    if args.task_filter:
        tasks = [t for t in tasks if args.task_filter in t["task_id"]]
    arms = args.arms.split(",")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as fh:
        for task in tasks:
            repo = Path(task["worktree"])
            if not repo.is_dir():
                p = run(["/usr/bin/env", "git", "-C", task["repo_dir"], "worktree",
                         "add", "--detach", task["worktree"], task["base_sha"]])
                if p.returncode != 0:
                    print("SKIP %s (worktree: %s)" % (task["task_id"], p.stderr[-80:]))
                    continue
            snap = Snapshot(repo)   # §3: one snapshot per task, reused by all arms
            for arm in arms:
                t0 = time.monotonic()
                if arm == "D":
                    res = arm_d(repo, task, snap)
                elif arm == "W":
                    res = arm_d(repo, task, snap, warm=True)
                elif arm == "D1":
                    res = arm_d(repo, task, snap, expand=False)
                else:
                    res = ARMS[arm](repo, task, snap)
                res["stage_ms"]["total"] = int((time.monotonic() - t0) * 1000)
                row = score(task, arm, res, snap)
                fh.write(json.dumps({"type": "BENCH_RESULT_V9", **row,
                                     "generated_at": datetime.now(
                                         timezone.utc).isoformat()}) + "\n")
                fh.flush()
                print("%-34s %-3s recall=%s span=%s/%s tok=%s lat=%sms" % (
                    task["task_id"], arm, row["gold_file_recall"],
                    row["gold_span_recall"], row["span_precision"],
                    row["context_tokens"], row["latency_ms"]))
    return 0


def run(cmd: list[str]):
    import subprocess
    return subprocess.run(cmd, capture_output=True, text=True, shell=False)


if __name__ == "__main__":
    raise SystemExit(main())
