#!/usr/bin/env python3
"""localize_two_stage.py — CoSIL-inspired two-stage localization, deterministic core.

Composition of the real backends (no new retrieval algorithm; every stage reuses
existing machinery):

  stage 1 — module/file BREADTH: retrieval_router.route() shortlists candidate
            files (direct-evidence class first, AOCI cognition and symbol-backend
            provenance preserved in the router report).
  stage 2 — function-level ITERATIVE DEPTH: for each shortlisted file, match
            definitions from the symbol backend (exact identifier equality),
            expanding 1 hop through the structural graph (symbol_graph.json:
            calls/imports/inheritance) only while the iteration budget lasts and
            only while each expansion has a reason (a prior iteration produced
            nothing); every stop records WHY (CoSIL's explicit-exit idea,
            deterministic form: SUFFICIENT_EVIDENCE | BUDGET | NO_EVIDENCE).

This is NOT the CoSIL agent loop (no LLM, no relevance sub-agent, no dynamic
graph construction) — it is the deterministic skeleton over our backends, named
as such. Upstream: ZhonghaoJiang/CoSIL CoSIL/fl/CoSIL.py (two-stage, bounded
iterations, explicit exit tool).

Exit codes: 0 ok (including honest NO_EVIDENCE), 2 usage, 3 repo error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import retrieval_router as rr                      # noqa: E402
import symbol_backend as sb                        # noqa: E402

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
STAGE1_MAX_FILES = 3
ARTIFACT = ".oss-contrib-evidence/localization_result.json"


def identifiers(query: str) -> list[str]:
    return [t for t in dict.fromkeys(
        raw for raw in TOKEN_RE.findall(query)
        if len(raw) >= 4 and any(c.isalpha() for c in raw))]


def stage1_breadth(repo: Path, query: str, task_type: str) -> dict:
    report = rr.route(str(repo), query, task_type, None, 10, 2, 50)
    direct = [c for c in report["candidates"] if c["evidence_class"] == "direct"]
    fallback = [c for c in report["candidates"] if c["evidence_class"] != "direct"]
    shortlist = [c["path"] for c in (direct or fallback)[:STAGE1_MAX_FILES]]
    return {"files": shortlist,
            "router_backend": report["backend"]["kind"],
            "router_backends_used": report.get("backends", {}),
            "candidates_considered": len(report["candidates"]),
            "used_direct_class": bool(direct)}


def _defs_in(repo: Path, path: str) -> list[dict]:
    rows, _ = sb.ast_file_symbols(repo, path)
    return rows


def stage2_depth(repo: Path, query: str, shortlist: list[str],
                 max_iterations: int, expand: bool = False) -> dict:
    """V9 §5 simplification (evidence: on 10 blind tasks the neighbor-hop
    expansion produced ZERO additional exact matches — D≡D1 identical in
    runs/v9-r1.jsonl — only extra visited nodes): the default is now
    definition matching inside the stage-1 shortlist ONLY. expand=True keeps
    the old iterative behavior for the experiment record."""
    ids = [i.lower() for i in identifiers(query)]
    graph = sb.load_graph(repo)
    adj_out: dict[str, list[str]] = {}
    adj_in: dict[str, list[str]] = {}
    if graph:
        for e in graph["edges"]:
            if e["kind"] in ("calls", "imports", "inherits"):
                adj_out.setdefault(e["src"], []).append(e["dst"])
                adj_in.setdefault(e["dst"], []).append(e["src"])

    visited: list[dict] = []
    exact: list[dict] = []
    frontier_files = list(shortlist)
    seen_nodes: set[str] = set()
    relations_covered: set[str] = set()

    for iteration in range(max_iterations):
        matched_this_iter = 0
        next_files: list[str] = []
        for ps in frontier_files:
            for d in _defs_in(repo, ps):
                nid = "%s:%s::%s" % ("class" if d["kind"] == "class" else "function",
                                     ps, d["symbol"])
                if nid in seen_nodes:
                    continue
                seen_nodes.add(nid)
                sym = d["symbol"].lower()
                hit = None
                if sym in ids:
                    hit = ("exact", 3.0)
                elif any(i in sym or sym in i for i in ids):
                    hit = ("partial", 1.0)
                visited.append({"node": nid, "iteration": iteration,
                                "match": hit[0] if hit else None,
                                "path": ps, "kind": d["kind"],
                                "start_line": d["start_line"],
                                "end_line": d["end_line"],
                                "source_digest": d["source_digest"]})
                if hit:
                    matched_this_iter += 1
                    if hit[0] == "exact":
                        exact.append({**visited[-1], "match": "exact"})
        if exact:
            return {"visited": visited, "exact_matches": exact,
                    "iterations_used": iteration + 1,
                    "exit_reason": "STOPPED_EVIDENCE_FOUND",
                    "stop_evidence": _stop_evidence(
                        query, exact, relations_covered, visited,
                        "direct identifier matches located inside the "
                        "stage-1 shortlist")}
        # expansion has a reason only if this iteration found partial leads or we
        # haven't looked at any neighborhood yet; expand 1 hop from visited nodes
        if expand and iteration + 1 < max_iterations and \
                (matched_this_iter or iteration == 0):
            for v in [x for x in visited if x["iteration"] == iteration]:
                for nb in adj_out.get(v["node"], []) + adj_in.get(v["node"], []):
                    if nb.startswith("file:"):
                        f = nb[5:]
                        relations_covered.add(v["node"] + " -> " + nb)
                        if f not in next_files and f not in shortlist:
                            next_files.append(f)
            frontier_files = next_files[:STAGE1_MAX_FILES]
            if not frontier_files:
                break
        else:
            break
    return {"visited": visited, "exact_matches": [],
            "iterations_used": max_iterations,
            "exit_reason": "STOPPED_NO_EVIDENCE" if not visited
            else "STOPPED_BUDGET",
            "stop_evidence": _stop_evidence(
                query, [], relations_covered, visited,
                "budget/iteration limit reached without an exact identifier "
                "match" if visited else
                "no definitions in the shortlist matched the query identifiers")}


def _stop_evidence(query: str, exact: list[dict], relations_covered: set[str],
                   visited: list[dict], why_stop: str) -> dict:
    """V9 §5: an explicit, correctness-neutral stopping record. The old name
    SUFFICIENT_EVIDENCE implied unproven correctness; STOPPED_EVIDENCE_FOUND is
    a stopping decision plus the evidence that justified STOPPING — nothing
    more."""
    return {
        "question": "which functions/classes does this query's identifier "
                    "evidence point at, inside the stage-1 shortlist?",
        "direct_evidence": [{"path": m["path"],
                             "symbol": m.get("node", "").split("::")[-1],
                             "line": m.get("start_line")} for m in exact],
        "relations_covered": sorted(relations_covered)[:20],
        "nodes_visited": len(visited),
        "unresolved": ["semantic correctness of each match (name-match, not "
                       "proven call resolution)",
                       "whether the located code is where a maintainer would "
                       "change behavior"],
        "why_stop": why_stop,
    }


def localize(repo: Path, query: str, task_type: str, max_iterations: int,
             stage1_result: dict | None = None,
             expand: bool = False) -> dict:
    """stage1_result: pass a previously computed stage-1 (V9 §3 task-scoped
    snapshot reuse) to avoid a second router/Corpus build per localizer run.
    expand=False: simplified stage-2 (shortlist definitions only, no hops)."""
    t0 = datetime.now(timezone.utc)
    reused = stage1_result is not None
    s1 = stage1_result or stage1_breadth(repo, query, task_type)
    s2 = stage2_depth(repo, query, s1["files"], max_iterations, expand=expand) \
        if s1["files"] else \
        {"visited": [], "exact_matches": [], "iterations_used": 0,
         "exit_reason": "STOPPED_NO_EVIDENCE",
         "stop_evidence": _stop_evidence(query, [], set(), [],
                                         "empty stage-1 shortlist")}
    result = {
        "artifact_type": "LOCALIZATION_RESULT",
        "repository_root": str(repo),
        "query": query,
        "task_type": task_type,
        "generated_at": t0.isoformat(),
        "stage1": s1,
        "stage1_reused": reused,
        "expand": expand,
        "stage2": s2,
        "functions": [{"path": m["path"], "symbol": m.get("node", "").split("::")[-1],
                       "kind": m["kind"], "start_line": m["start_line"],
                       "end_line": m["end_line"],
                       "source_digest": m["source_digest"],
                       "relation": "definition", "backend": "python-ast+router"}
                      for m in s2["exact_matches"]],
        "exit_reason": s2["exit_reason"],
        "stop_evidence": s2.get("stop_evidence"),
        "latency_ms": int((datetime.now(timezone.utc) - t0).total_seconds() * 1000),
    }
    out = repo / ARTIFACT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    return result


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Two-stage deterministic localization (router breadth → symbol depth).")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--task-type", default="issue2code", choices=list(rr.ROUTING_POLICIES))
    ap.add_argument("--max-iterations", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print("error: %s is not a directory" % repo, file=sys.stderr)
        return 3
    res = localize(repo, args.query, args.task_type, args.max_iterations)
    if args.json:
        print(json.dumps(res, indent=2))
        return 0
    print("stage1 files: %s (router backend: %s)" % (res["stage1"]["files"],
                                                     res["stage1"]["router_backend"]))
    print("stage2 visited: %d nodes in %d iteration(s)" % (
        len(res["stage2"]["visited"]), res["stage2"]["iterations_used"]))
    print("exit: %s" % res["exit_reason"])
    for f in res["functions"]:
        print("  → %s::%s (L%s-%s, %s)" % (f["path"], f["symbol"],
                                           f["start_line"], f["end_line"],
                                           f["source_digest"][:12]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
