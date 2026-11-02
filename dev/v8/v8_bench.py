#!/usr/bin/env python3
"""v8_bench.py — V8 four-arm benchmark over frozen real-repository tasks.

ARMS (same frozen query per task; gold never visible to any arm):
  A grep        — competent grep workflow: identifier scan over the repo tree,
                  inspect matching lines ±10, then sibling test files.
  B symbol      — symbol backend only: index build + method/class/code search,
                  deliver symbol spans ±5.
  C router-nograph — retrieval_router hybrid WITHOUT graph expansion and WITHOUT
                  structural artifacts (ablation override, no structural families);
                  delivers file pointers (whole-file token cost — this arm simply
                  does not produce spans, recorded honestly as null).
  D full        — full pipeline: spans artifact + structural graph + router WITH
                  graph expansion + two-stage localization; delivers files AND
                  function spans ±5.

The measured unit is the CONTEXT-ACQUISITION LAYER, not an LLM: each arm is a
deterministic competent protocol. All four use the same token estimator
(chars/4), the same gold (frozen from the fixing commit), and report the same
metric set per the V8 goal (recalls, span precision, irrelevant files, tokens,
tool ops, graph expansions, time-to-first-useful-file/symbol, phase latencies,
backend/fallback). No single "accuracy" score is computed.

Usage:
  python3 v8_bench.py --arm A --out runs/bench-r1.jsonl
  python3 v8_bench.py --arm all --out runs/bench-r1.jsonl
  python3 v8_bench.py --arm D --aoci conformance   (D + AOCI cognition via runtime)
  python3 v8_bench.py --arm D --aoci file          (D + AOCI_FILE fixture cognition)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_SCRIPTS = HERE.parent.parent / "oss-contribution-engineer" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

import retrieval_router as rr          # noqa: E402
import symbol_backend as sb            # noqa: E402
import localize_two_stage as loc       # noqa: E402

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
CONTEXT_WINDOW = 10        # lines of context for grep-style inspection
SPAN_WINDOW = 5            # lines around a symbol span


def est_tokens(text: str) -> int:
    return len(text) // 4


def query_identifiers(query: str, body: str) -> list[str]:
    raw = TOKEN_RE.findall(query + " " + body)
    seen, out = set(), []
    for t in sorted(raw, key=lambda x: (-len(x), x.lower())):
        k = t.lower()
        if len(k) >= 4 and k not in seen and any(c.isalpha() for c in k):
            seen.add(k)
            out.append(t)
        if len(out) >= 6:
            break
    return out


def span_payload(repo: Path, path: str, start: int, end: int, window: int) -> tuple[str, int, int]:
    p = repo / path
    if not p.exists():
        return "", start, end
    lines = p.read_text(errors="replace").splitlines()
    a = max(1, start - window)
    b = min(len(lines), end + window)
    return "\n".join(lines[a - 1:b]), a, b


# ---------------------------------------------------------------- arm A: grep
def arm_a(repo: Path, task: dict) -> dict:
    steps, ops = [], 0
    t0 = time.monotonic()
    ids = query_identifiers(task["query"], task["body_excerpt"])[:4]
    # step 1: one full-tree scan (grep analog), case-insensitive, per-file hit counts
    hits: dict[str, int] = {}
    texts: dict[str, list[str]] = {}
    t1 = time.monotonic()
    for p in _all_files(repo):
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        rel = p.relative_to(repo).as_posix()
        texts[rel] = text.splitlines()
        low = text.lower()
        c = sum(low.count(i.lower()) for i in ids)
        if c:
            hits[rel] = c
    scan_ms = int((time.monotonic() - t1) * 1000)
    ops += 1
    ranked = sorted(hits, key=lambda k: -hits[k])
    steps.append({"op": "grep_scan", "files": ranked[:10], "ms": scan_ms})
    # step 2: inspect top-3 files — deliver matching lines ± CONTEXT_WINDOW
    delivered_spans, delivered_files = [], []
    t2 = time.monotonic()
    for rel in ranked[:3]:
        delivered_files.append(rel)
        lines = texts.get(rel) or (repo / rel).read_text(errors="replace").splitlines()
        for i, ln in enumerate(lines, 1):
            if any(i.lower() in ln.lower() for i in ids):
                a, b = max(1, i - CONTEXT_WINDOW), min(len(lines), i + CONTEXT_WINDOW)
                delivered_spans.append((rel, a, b))
        ops += 1
    inspect_ms = int((time.monotonic() - t2) * 1000)
    steps.append({"op": "inspect", "files": delivered_files, "ms": inspect_ms})
    # step 3: direct tests (naming convention): test paths mentioning a delivered file's stem
    stems = {rr.module_stem(d) for d in delivered_files}
    tests = []
    for p in _all_files(repo):
        rel = p.relative_to(repo).as_posix()
        if rr.is_test_path(rel) and any(s and s in rel for s in stems):
            tests.append(rel)
    ops += 1
    steps.append({"op": "direct_tests", "files": tests[:5], "ms": 0})
    return {"steps": steps, "ops": ops, "files": delivered_files,
            "spans": delivered_spans, "tests": tests,
            "scan_files": len(texts), "latency_ms": int((time.monotonic() - t0) * 1000),
            "scan_ms": scan_ms}


def _all_files(repo: Path):
    for p in sorted(repo.rglob("*")):
        rel = p.relative_to(repo)
        if any(part in rr.SKIP_DIRS or part.startswith(".") for part in rel.parts[:-1]):
            continue
        if p.is_file() and not p.name.startswith(".") and p.suffix in {
                ".py", ".go", ".rs", ".ts", ".js", ".mjs", ".cjs", ".tsx", ".jsx"} \
                and p.stat().st_size <= rr.MAX_FILE_BYTES:
            yield p


# ---------------------------------------------------------------- arm B: symbol
def arm_b(repo: Path, task: dict) -> dict:
    steps, ops = [], 0
    t0 = time.monotonic()
    ids = query_identifiers(task["query"], task["body_excerpt"])
    t1 = time.monotonic()
    artifact = sb.build_index(repo, "python-ast")   # index build counted as ops
    index_ms = int((time.monotonic() - t1) * 1000)
    ops += 1
    steps.append({"op": "index_build", "defs": artifact["counts"]["definitions"],
                  "ms": index_ms})
    delivered_spans, delivered_files = [], []
    t2 = time.monotonic()
    for ident in ids[:4]:
        for mode, want in (("method", ident), ("class", ident)):
            res = sb.search_api(repo, mode, want, None, None, None)
            ops += 1
            for r in res["results"]:
                delivered_spans.append((r["path"], r["start_line"], r["end_line"]))
                if r["path"] not in delivered_files:
                    delivered_files.append(r["path"])
    if not delivered_spans and ids:
        res = sb.search_api(repo, "code", None, None, ids[0], None)
        ops += 1
        for r in res["results"][:20]:
            delivered_spans.append((r["path"], r["start_line"], r["start_line"]))
            if r["path"] not in delivered_files:
                delivered_files.append(r["path"])
    search_ms = int((time.monotonic() - t2) * 1000)
    steps.append({"op": "symbol_search", "ms": search_ms})
    return {"steps": steps, "ops": ops, "files": delivered_files,
            "spans": delivered_spans, "tests": [],
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "index_ms": index_ms, "backend": "python-ast"}


# ---------------------------------------------------------------- arms C / D
C_SIGNALS = ["lexical", "path", "symbol", "test", "history", "cognition",
             "symbol_backend"]


def arm_c(repo: Path, task: dict) -> dict:
    steps, ops = [], 0
    t0 = time.monotonic()
    t1 = time.monotonic()
    corpus = rr.Corpus(repo)
    scan_ms = int((time.monotonic() - t1) * 1000)
    ops += 1
    t2 = time.monotonic()
    report = rr.route(str(repo), task["query"] + " " + task["body_excerpt"][:400],
                      "issue2code", list(C_SIGNALS), 8, 0, 0)
    route_ms = int((time.monotonic() - t2) * 1000)
    ops += 1
    files = [c["path"] for c in report["candidates"]]
    steps.append({"op": "corpus_scan", "ms": scan_ms, "files": len(corpus.files)})
    steps.append({"op": "route_no_graph", "ms": route_ms, "files": files})
    return {"steps": steps, "ops": ops, "files": files, "spans": [], "tests": [],
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "scan_ms": scan_ms, "route_ms": route_ms,
            "backend": report["backend"]["kind"],
            "families": report["provenance"]["families_run"],
            "note": "file pointers only; spans not produced by this arm"}


def arm_d(repo: Path, task: dict, aoci_mode: str | None = None) -> dict:
    steps, ops = [], 0
    t0 = time.monotonic()
    aoci_info = None
    if aoci_mode:
        aoci_info = _aoci_prepare(repo, aoci_mode)
    t1 = time.monotonic()
    corpus = rr.Corpus(repo)
    scan_ms = int((time.monotonic() - t1) * 1000)
    ops += 1
    t2 = time.monotonic()
    report = rr.route(str(repo), task["query"] + " " + task["body_excerpt"][:400],
                      "issue2code", None, 8, 2, 50)
    route_ms = int((time.monotonic() - t2) * 1000)
    ops += 1
    files = [c["path"] for c in report["candidates"]]
    expansions = sum(1 for c in report["candidates"]
                     if any(e["family"] == "graph" for e in c["evidence"]))
    steps.append({"op": "corpus_scan", "ms": scan_ms})
    steps.append({"op": "route_full", "ms": route_ms, "files": files})
    t3 = time.monotonic()
    loc_res = loc.localize(repo, task["query"] + " " + task["body_excerpt"][:400],
                           "issue2code", 3)
    loc_ms = int((time.monotonic() - t3) * 1000)
    ops += 1
    steps.append({"op": "two_stage", "ms": loc_ms,
                  "exit": loc_res["exit_reason"],
                  "functions": [(f["path"], f["symbol"]) for f in loc_res["functions"]]})
    delivered_spans = [(f["path"], f["start_line"], f["end_line"])
                       for f in loc_res["functions"]]
    if loc_res["stage1"]["files"]:
        for f in loc_res["stage1"]["files"]:
            if f not in files:
                files.append(f)
    return {"steps": steps, "ops": ops, "files": files[:10], "spans": delivered_spans,
            "tests": [], "graph_expansions": expansions,
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "scan_ms": scan_ms, "route_ms": route_ms, "loc_ms": loc_ms,
            "backend": report["backend"]["kind"],
            "aoci": aoci_info,
            "exit_reason": loc_res["exit_reason"]}


def _aoci_prepare(repo: Path, mode: str) -> dict:
    """Build the AOCI fixture on the worktree; for 'conformance' also run a real
    runtime session through the conformance service (per-connection lifecycle)."""
    import aoci_conformance_server as acs
    import aoci_runtime as art
    info: dict = {"mode": mode}
    try:
        args = type("A", (), {"repo": str(repo)})()
        acs.build_fixture(args)
        info["fixture_entries"] = len(acs.Index(Path(repo)).entries)
        if mode == "conformance":
            srv = "python3 %s serve --repo %s" % (
                SKILL_SCRIPTS / "aoci_conformance_server.py", repo)
            argv = art.resolve_mcp_command(Path(repo), srv)
            sess = art.open_session(Path(repo), argv, "all")
            info["cognition_state"] = sess.get("cognition_state")
            info["backend"] = sess.get("backend")
            info["latency_ms"] = sess.get("latency_ms")
            info["fallback"] = sess.get("fallback")
    except Exception as exc:  # fail visibly, never silently
        info["error"] = str(exc)[:300]
    return info


# ---------------------------------------------------------------- scoring
def score(task: dict, arm: str, res: dict) -> dict:
    gold_files = set(task["gold_prod_files"])
    gold_spans = task["gold_spans"]
    files = res.get("files", [])
    hit_files = [f for f in files if f in gold_files]
    row = {
        "task_id": task["task_id"], "arm": arm,
        "gold_file_recall": round(len(set(hit_files)) / len(gold_files), 3) if gold_files else None,
        "gold_file_hit_ranks": [files.index(f) + 1 for f in gold_files if f in files],
        "irrelevant_files": sum(1 for f in files if f not in gold_files),
        "graph_expansions": res.get("graph_expansions", 0),
        "ops": res.get("ops"),
        "latency_ms": res.get("latency_ms"),
        "backend": res.get("backend"),
        "fallbacks": bool(res.get("aoci", {}) and res["aoci"].get("fallback")) if arm == "D" else None,
    }
    # span metrics only for arms that actually deliver spans
    spans = res.get("spans") or []
    if spans and gold_spans:
        want = {p: [(a, b) for a, b in ranges] for p, ranges in gold_spans.items()}
        gold_lines_total = sum(b - a + 1 for rs in want.values() for a, b in rs)
        covered_lines: set[tuple[str, int]] = set()
        delivered_lines = 0
        in_gold = 0
        for path, a, b in spans:
            for ln in range(a, b + 1):
                delivered_lines += 1
                if path in want and any(a0 <= ln <= b0 for a0, b0 in want[path]):
                    covered_lines.add((path, ln))
                    in_gold += 1
        covered = len(covered_lines)   # unique gold lines covered — overlapping
        # delivery windows must not inflate recall
        row["gold_span_recall"] = round(covered / gold_lines_total, 3) if gold_lines_total else None
        row["span_precision"] = round(in_gold / delivered_lines, 3) if delivered_lines else 0.0
        row["irrelevant_lines_delivered"] = delivered_lines - in_gold
        # time to first useful symbol: first delivered span touching gold spans
        ttf_sym = None
        for i, (path, a, b) in enumerate(spans):
            if path in want and any(not (b < a0 or a > b0) for a0, b0 in want[path]):
                ttf_sym = i + 1
                break
        row["first_useful_symbol_step"] = ttf_sym
        payload_tokens = 0
        repo = Path(task["worktree"])
        for path, a, b in spans:
            text, _, _ = span_payload(repo, path, a, b, 0)
            payload_tokens += est_tokens(text)
        row["context_tokens"] = payload_tokens
    else:
        row["gold_span_recall"] = None
        row["span_precision"] = None
        row["irrelevant_lines_delivered"] = None
        repo = Path(task["worktree"])
        row["context_tokens"] = sum(
            est_tokens((repo / f).read_text(errors="replace")) if (repo / f).exists() else 0
            for f in files) if arm == "C" else 0
        if arm == "C":
            row["note"] = "file pointers charged whole-file (the arm's honest output shape)"
    # time to first useful file: first step whose file list touches gold
    ttf_file = None
    for i, s in enumerate(res.get("steps", [])):
        fl = s.get("files", [])
        if isinstance(fl, list) and any(f in gold_files for f in fl):
            ttf_file = i + 1
            break
    row["first_useful_file_step"] = ttf_file
    return row


ARMS = {"A": arm_a, "B": arm_b, "C": arm_c}


def arm_w(repo: Path, task: dict) -> dict:
    """Warm-cache arm: route() through router_cache.build_corpus. The first
    call populates the cache (cold cost included in THIS run's numbers); the
    persisted cache then serves warm queries. Latency column here = warm-ish."""
    import router_cache
    rr.CORPUS_BUILDER = router_cache.build_corpus
    try:
        res = arm_d(repo, task, None)
    finally:
        rr.CORPUS_BUILDER = None
    res["backend"] = (res.get("backend") or "") + "+warm-cache"
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=["A", "B", "C", "D", "W", "all"])
    ap.add_argument("--tasks", default=str(HERE / "tasks.json"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--aoci", choices=["file", "conformance"], default=None)
    ap.add_argument("--task-filter", default=None)
    ap.add_argument("--reuse-raw", action="store_true",
                    help="reuse cached raw arm outputs (runs/raw/) so scoring fixes "
                         "don't require re-running arms; raws are deterministic")
    args = ap.parse_args()
    tasks = json.loads(Path(args.tasks).read_text())
    if args.task_filter:
        tasks = [t for t in tasks if args.task_filter in t["task_id"]]
    arms = ["A", "B", "C", "D"] if args.arm == "all" else [args.arm]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as fh:
        for task in tasks:
            repo = Path(task["worktree"])
            for arm in arms:
                raw_dir = HERE / "runs" / "raw"
                raw_dir.mkdir(parents=True, exist_ok=True)
                raw_path = raw_dir / ("%s__%s__%s.json" % (
                    task["task_id"], arm, args.aoci or "none"))
                if args.reuse_raw and raw_path.exists():
                    res = json.loads(raw_path.read_text())
                else:
                    if arm == "D":
                        res = arm_d(repo, task, args.aoci)
                    elif arm == "W":
                        res = arm_w(repo, task)
                    else:
                        res = ARMS[arm](repo, task)
                    raw_path.write_text(json.dumps(res))
                row = score(task, arm, res)
                row["run_config"] = {"aoci": args.aoci, "repo_slug": task["repo_slug"],
                                     "base_sha": task["base_sha"],
                                     "merge_sha": task["merge_sha"]}
                fh.write(json.dumps({"type": "BENCH_RESULT", **row}) + "\n")
                fh.flush()
                print("%-32s %s gold_file_recall=%s span_recall=%s tokens=%s ops=%s lat=%sms"
                      % (task["task_id"], arm, row["gold_file_recall"],
                         row["gold_span_recall"], row.get("context_tokens"),
                         row["ops"], row["latency_ms"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
