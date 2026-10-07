#!/usr/bin/env python3
"""repository_intelligence.py — the production orchestrator for repository
intelligence (V10 Skill-integration goal).

Composes the existing capability modules; the caller (the Skill workflow, i.e.
`contribution_session.py investigate`) never needs to know which one ran:

    prepare(repo, task_text, task_type) -> snapshot + backend selection
    locate(prepare, task_text)          -> routed candidates + localization
    context(repo, locate, anchors)      -> Context Pack + verified provenance
    refresh(repo, prepare_result)       -> what changed since prepare
    status(repo)                        -> backend availability / staleness

Backend selection is AUTOMATIC and EXPLICIT: every candidate backend appears in
`backends[]` with used/skipped and a reason — downgrades are never silent.

    official aligned AOCI runtime receipt -> AOCI cognition
    SERENA_MCP_COMMAND configured         -> Serena/LSP resolved symbols
    Python repo                           -> python-ast semantic spans
    otherwise                             -> lexical/lightweight fallback

No backend is source truth: every delivered span carries WHY / RELATION /
BACKEND / SOURCE(digest) provenance, and digests are verified against current
bytes at context time.

CLI (debug/expert use only — the Agent surface is `contribution_session.py`):
    repository_intelligence.py status   --repo R
    repository_intelligence.py prepare  --repo R --task-text "..." [--task-type T]
    repository_intelligence.py locate   --repo R --task-text "..." [--task-type T]
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import retrieval_router as rr            # noqa: E402
import router_cache                      # noqa: E402
import symbol_backend as sb              # noqa: E402
import localize_two_stage as loc         # noqa: E402

AOCI_SESSION = ".oss-contrib-evidence/aoci_runtime_session.json"
SKILL_SCRIPTS = SCRIPTS


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _head(repo: Path) -> str:
    p = subprocess.run(["/usr/bin/env", "git", "-C", str(repo), "rev-parse", "HEAD"],
                       capture_output=True, text=True, shell=False)
    return p.stdout.strip() if p.returncode == 0 else ""


def _digest(repo: Path, rel: str) -> str:
    p = repo / rel
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else ""


# ---------------------------------------------------------------- backends
def select_backends(repo: Path) -> dict:
    """Detect every candidate backend and decide which runs. Skipped ones stay
    visible with the reason — silent downgrade is forbidden."""
    candidates = []

    # 1. AOCI runtime (a real runtime session receipt, COMPLETE cognition)
    sess = None
    sp = repo / AOCI_SESSION
    if sp.exists():
        try:
            sess = json.loads(sp.read_text())
        except (json.JSONDecodeError, OSError):
            sess = None
    if sess and not sess.get("fallback") and sess.get("cognition_state") == "COMPLETE":
        candidates.append({"backend": "AOCI_RUNTIME", "status": "used",
                           "detail": "runtime cognition receipt %s @ generation %s"
                                     % ((sess.get("index_identity") or "?")[:12],
                                        sess.get("generation")),
                           "session_artifact": AOCI_SESSION})
    elif sess:
        candidates.append({"backend": "AOCI_RUNTIME", "status": "skipped",
                           "reason": "session artifact present but cognition %s / fallback %s"
                                     % (sess.get("cognition_state"),
                                        bool(sess.get("fallback")))})
    else:
        candidates.append({"backend": "AOCI_RUNTIME", "status": "skipped",
                           "reason": "no runtime session (AOCI_MCP_COMMAND not "
                                     "configured / never run)"})

    # 2. AOCI file volumes (explicit fallback target of the runtime)
    aoci_file = (repo / "aoci.code.txt").exists() or (repo / "aoci.txt").exists()
    if aoci_file:
        state, detail = rr.aoci_alignment(repo)
        candidates.append({"backend": "AOCI_FILE", "status": "used" if state == "aligned"
                           else "degraded",
                           "detail": "file volumes, alignment=%s (%s)" % (state, detail)})
    else:
        candidates.append({"backend": "AOCI_FILE", "status": "skipped",
                           "reason": "no aoci volumes in repo"})

    # 3. Serena/LSP
    serena_argv = sb.serena_command(repo)
    if serena_argv:
        candidates.append({"backend": "SERENA_LSP", "status": "available",
                           "detail": "SERENA_MCP_COMMAND configured"})
    else:
        candidates.append({"backend": "SERENA_LSP", "status": "skipped",
                           "reason": "SERENA_MCP_COMMAND not configured"})

    # 4. python-ast semantic backend (works when there is anything to parse)
    py_files = sum(1 for _ in sb.iter_py_files(repo))
    if py_files:
        candidates.append({"backend": "PYTHON_AST", "status": "used",
                           "detail": "%d python files; spans/refs/inheritance via "
                                     "CPython ast (name-match resolution)" % py_files})
    else:
        candidates.append({"backend": "PYTHON_AST", "status": "skipped",
                           "reason": "no python files"})

    # 5. lexical/lightweight is always available
    candidates.append({"backend": "LEXICAL_LIGHTWEIGHT", "status": "used",
                       "detail": "BM25/path/history/test relations; deterministic"})

    limitations = []
    if not serena_argv:
        limitations.append("no LSP: references/inheritance are name-match "
                           "candidates on Python only; non-Python tasks get "
                           "lexical context only")
    if not (sess and sess.get("cognition_state") == "COMPLETE"):
        limitations.append("no AOCI runtime cognition: architecture-level "
                           "responsibilities come from file scan only")
    return {"backends": candidates, "limitations": limitations,
            "selected": [c["backend"] for c in candidates if c["status"] == "used"]}


# ---------------------------------------------------------------- prepare
def prepare(repo: Path, task_text: str, task_type: str = "issue2code") -> dict:
    """Build the task-scoped snapshot once; record backend selection + stage
    timings. Everything downstream reads this snapshot."""
    t0 = time.monotonic()
    snap_stage = {}
    corpus = router_cache.build_corpus(repo)
    snap_stage["scan_tokenize"] = int((time.monotonic() - t0) * 1000)
    t0 = time.monotonic()
    spans_art = sb.build_index(repo, "python-ast")
    (repo / sb.ARTIFACT).parent.mkdir(parents=True, exist_ok=True)
    (repo / sb.ARTIFACT).write_text(json.dumps(spans_art))
    snap_stage["symbol_index"] = int((time.monotonic() - t0) * 1000)
    t0 = time.monotonic()
    graph = sb.load_graph(repo) or sb.build_graph(repo)
    if not sb.load_graph(repo):
        (repo / sb.GRAPH_ARTIFACT).parent.mkdir(parents=True, exist_ok=True)
        (repo / sb.GRAPH_ARTIFACT).write_text(json.dumps(graph))
    snap_stage["graph_build"] = int((time.monotonic() - t0) * 1000)
    backends = select_backends(repo)
    return {
        "prepared_at": now(), "repo": str(repo), "head": _head(repo),
        "task_type": task_type, "stage_ms": snap_stage,
        "backends": backends,
        "files_scanned": len(corpus.files),
        "graph_counts": graph["counts"],
    }


# ---------------------------------------------------------------- locate
def locate(repo: Path, task_text: str, task_type: str = "issue2code",
           prepare_result: dict | None = None) -> dict:
    """Route + localize on the prepared snapshot; attach provenance."""
    query = task_text
    report = rr.route(str(repo), query, task_type, None, 8, 2, 50)
    files = [c["path"] for c in report["candidates"]]
    loc_res = loc.localize(repo, query, task_type, 3, stage1_result={
        "files": files[:loc.STAGE1_MAX_FILES],
        "router_backend": report["backend"]["kind"],
        "router_backends_used": report.get("backends", {}),
        "candidates_considered": len(report["candidates"]),
        "used_direct_class": any(c["evidence_class"] == "direct"
                                 for c in report["candidates"])})
    for f in loc_res["stage1"]["files"]:
        if f not in files:
            files.append(f)
    # provenance per located function (WHY / BACKEND / SOURCE)
    provenance = []
    for f in loc_res["functions"]:
        prov = {"path": f["path"], "symbol": f["symbol"],
                "span": [f["start_line"], f["end_line"]],
                "why": loc_res["stop_evidence"]["question"]
                + " — exact identifier match inside the stage-1 shortlist",
                "relation": "definition",
                "backend": "python-ast+router",
                "source_digest": f["source_digest"],
                "digest_state": "CURRENT" if _digest(repo, f["path"]) == f["source_digest"]
                else "CHANGED"}
        provenance.append(prov)
    return {"query": query, "router": report, "localization": loc_res,
            "candidate_files": files, "provenance": provenance,
            "exit_reason": loc_res["exit_reason"],
            "stop_evidence": loc_res.get("stop_evidence")}


# ---------------------------------------------------------------- context
def context(repo: Path, locate_result: dict, anchors: str = "") -> dict:
    """Build the Context Pack through the real planner CLI, then verify digests
    and attach per-span provenance (WHY / DIRECT EVIDENCE / RELATION / BACKEND /
    SOURCE)."""
    ev = repo / ".oss-contrib-evidence"
    ev.mkdir(parents=True, exist_ok=True)
    goal_tmp = ev / "ri_goal.json"
    goal_tmp.write_text(json.dumps({"intent": locate_result["query"]}))
    (ev / "ri_retrieval.json").write_text(json.dumps(locate_result["router"]))
    p1 = subprocess.run(["/usr/bin/env", "python3", str(SKILL_SCRIPTS / "context_planner.py"),
                         str(repo), "plan", "--goal", str(goal_tmp),
                         "--retrieval", str(ev / "ri_retrieval.json")],
                        capture_output=True, text=True, shell=False, timeout=300)
    if p1.returncode != 0:
        return {"ok": False, "error": "context plan failed: %s" % p1.stderr[-200:]}
    (ev / "ri_plan.json").write_text(p1.stdout)
    p2 = subprocess.run(["/usr/bin/env", "python3", str(SKILL_SCRIPTS / "context_planner.py"),
                         str(repo), "pack", "--goal", str(goal_tmp),
                         "--plan", str(ev / "ri_plan.json"),
                         "--anchor-symbols", anchors],
                        capture_output=True, text=True, shell=False, timeout=300)
    if p2.returncode != 0:
        return {"ok": False, "error": "context pack failed: %s" % p2.stderr[-200:]}
    pack_p = ev / "ri_pack.json"
    pack_p.write_text(p2.stdout)
    try:
        pack = json.loads(p2.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "pack output not JSON"}

    # verify every packed source range against current bytes; attach provenance
    router_why = {c["path"]: c.get("reason", "")
                  for c in locate_result["router"].get("candidates", [])}
    verified, changed = [], []
    for s in pack.get("source_ranges", []) + pack.get("test_ranges", []):
        rel = s.get("path")
        if not rel:
            continue
        digest = _digest(repo, rel)
        row = {"path": rel, "start_line": s.get("start_line"),
               "end_line": s.get("end_line"),
               "why": router_why.get(rel, "packed by planner (no direct router "
                                       "reason recorded)"),
               "relation": s.get("relation", ""),
               "backend": "planner/pack",
               "source_digest": digest, "head": _head(repo)}
        # locate()-level provenance may override WHY for the same file
        for lp in locate_result.get("provenance", []):
            if lp["path"] == rel:
                row["why"] = lp["why"]
                row["backend"] = lp["backend"]
                row["relation"] = lp["relation"]
                break
        row["digest_state"] = "CURRENT" if digest else "MISSING"
        if any(lp["path"] == rel and lp["digest_state"] == "CHANGED"
               for lp in locate_result.get("provenance", [])):
            row["digest_state"] = "CHANGED"
        verified.append(row)
    return {"ok": True, "pack_file": str(pack_p),
            "pack_digest": hashlib.sha256(p2.stdout.encode()).hexdigest()[:16],
            "provenance": verified, "digest_state": "CURRENT",
            "changed_files": changed}


# ---------------------------------------------------------------- refresh/status
def refresh(repo: Path, prepare_result: dict | None = None) -> dict:
    """Re-detect what changed since prepare; tell the caller exactly what must
    be refreshed."""
    now_backends = select_backends(repo)
    head = _head(repo)
    out = {"checked_at": now(), "head": head,
           "head_changed": bool(prepare_result and prepare_result.get("head")
                                and prepare_result["head"] != head)}
    if prepare_result:
        old_sel = set(prepare_result.get("backends", {}).get("selected", []))
        new_sel = set(now_backends["selected"])
        out["backend_changes"] = sorted(old_sel ^ new_sel) or []
    sb_art = repo / sb.ARTIFACT
    gp_art = repo / sb.GRAPH_ARTIFACT
    out["artifacts_stale"] = {
        "symbol_index": not sb_art.exists(),
        "symbol_graph": not gp_art.exists(),
    }
    return out


def status(repo: Path) -> dict:
    head = _head(repo)
    sess_ok = False
    sp = repo / AOCI_SESSION
    if sp.exists():
        try:
            sess = json.loads(sp.read_text())
            sess_ok = (not sess.get("fallback")
                       and sess.get("cognition_state") == "COMPLETE")
        except (json.JSONDecodeError, OSError):
            sess_ok = False
    return {
        "repo": str(repo), "head": head,
        "backends": select_backends(repo),
        "artifacts": {
            "symbol_index": (repo / sb.ARTIFACT).exists(),
            "symbol_graph": (repo / sb.GRAPH_ARTIFACT).exists(),
            "router_cache": (repo / router_cache.CACHE_PATH).exists(),
            "aoci_runtime_session": sp.exists(),
        },
        "aoci_runtime_cognition_complete": sess_ok,
    }


# ---------------------------------------------------------------- CLI (debug)
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Repository intelligence orchestrator (Agent surface: contribution_session.py).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("status", "prepare", "locate"):
        p = sub.add_parser(name)
        p.add_argument("--repo", required=True)
        if name != "status":
            p.add_argument("--task-text", required=True)
            p.add_argument("--task-type", default="issue2code")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print("error: %s is not a directory" % repo, file=sys.stderr)
        return 3
    if args.cmd == "status":
        print(json.dumps(status(repo), indent=2))
        return 0
    if args.cmd == "prepare":
        print(json.dumps(prepare(repo, args.task_text, args.task_type), indent=2))
        return 0
    print(json.dumps(locate(repo, args.task_text, args.task_type), indent=2)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
