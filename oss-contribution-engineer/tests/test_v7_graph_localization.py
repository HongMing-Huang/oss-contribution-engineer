#!/usr/bin/env python3
"""V7 acceptance tests: structural graph, search API, two-stage localization.

Run: python3 -m pytest tests/test_v7_graph_localization.py -q
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

SYM = SCRIPTS / "symbol_backend.py"
LOC = SCRIPTS / "localize_two_stage.py"
ROUTER = SCRIPTS / "retrieval_router.py"
GRAPH_ARTIFACT = ".oss-contrib-evidence/symbol_graph.json"


def run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/env", "python3", str(script), *args],
                          capture_output=True, text=True, shell=False, timeout=180)


def out_json(script: Path, *args: str, ok=(0, 4)) -> dict:
    p = run(script, *args)
    assert p.returncode in ok, p.stderr
    return json.loads(p.stdout)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    (r / "src").mkdir(parents=True)
    (r / "src" / "base.py").write_text(
        "class Base:\n    def area(self):\n        return 0\n")
    (r / "src" / "shape.py").write_text(
        "from src.base import Base\n\n\n"
        "class Shape(Base):\n"
        "    def __init__(self, scale):\n"
        "        self.scale = scale\n\n"
        "    def area(self):\n"
        "        return self.scale * base_area()\n\n\n"
        "def base_area():\n    return 1\n")
    assert run(SYM, "graph", "--repo", str(r)).returncode == 0
    assert run(SYM, "index", "--repo", str(r)).returncode == 0
    return r


# ------------------------------------------------- 1. graph edges (LocAgent taxonomy)
def test_graph_edges_follow_locagent_taxonomy(repo):
    g = json.loads((repo / GRAPH_ARTIFACT).read_text())
    assert g["artifact_type"] == "SYMBOL_GRAPH"
    kinds = {}
    for e in g["edges"]:
        kinds.setdefault(e["kind"], []).append((e["src"], e["dst"], e["resolution"]))
    assert ("file:src/base.py", "class:src/base.py::Base", "exact") in kinds["contains"]
    assert ("file:src/shape.py", "file:src/base.py", "module-stem") in kinds["imports"]
    assert any(src == "class:src/shape.py::Shape" and dst == "class:src/base.py::Base"
               and res == "name-match"
               for src, dst, res in kinds["inherits"]), "Shape inherits Base"
    assert any(src == "func:src/shape.py::area" and dst == "func:src/shape.py::base_area"
               and res == "name-match"
               for src, dst, res in kinds["calls"]), "area calls base_area"
    assert any("name-match" in n for n in g["resolution_notes"]), \
        "candidate-edge limitation must be recorded, not hidden"


# ------------------------------------------------- 2. bounded trace
def test_trace_is_bounded_and_follows_semantic_edges(repo):
    res = out_json(SYM, "trace", "--repo", str(repo), "--name", "area",
                   "--max-depth", "2", "--json")
    assert res["found"] is True
    nodes = [v["node"] for v in res["visited"]]
    assert "func:src/shape.py::area" in nodes
    assert "func:src/shape.py::base_area" in nodes, "calls edge reachable"
    assert all(v["depth"] <= 2 for v in res["visited"])
    assert len(res["visited"]) <= 60
    # tight budget stops at BUDGET with an honest exit reason
    tight = out_json(SYM, "trace", "--repo", str(repo), "--name", "area",
                     "--max-depth", "2", "--max-nodes", "3", "--json")
    assert tight["exit_reason"] == "BUDGET"
    assert len(tight["visited"]) == 3


# ------------------------------------------------- 3. AutoCodeRover-style search API
def test_search_api_exact_spans(repo):
    res = out_json(SYM, "search", "--repo", str(repo), "--mode", "method-in-class",
                   "--name", "area", "--class-name", "Shape", "--json")
    assert res["ok"] and res["results"] == [{
        "path": "src/shape.py", "symbol": "area", "kind": "method",
        "start_line": 8, "end_line": 9,
        "source_digest": res["results"][0]["source_digest"],
        "relation": "contains", "backend": "python-ast"}]
    code = out_json(SYM, "search", "--repo", str(repo), "--mode", "code",
                    "--pattern", "base_area", "--json")
    lines = [(r["path"], r["start_line"]) for r in code["results"]]
    assert ("src/shape.py", 9) in lines and ("src/shape.py", 12) in lines
    assert all(r["kind"] == "code_line" for r in code["results"])


# ------------------------------------------------- 4. two-stage exit semantics
def test_two_stage_sufficient_and_no_evidence_exits(repo):
    res = out_json(LOC, "--repo", str(repo),
                   "--query", "where does Shape compute area scaling", "--json", ok=(0,))
    assert res["artifact_type"] == "LOCALIZATION_RESULT"
    # V9 §5: the exit name no longer implies correctness — it is a stopping
    # decision plus an explicit evidence record
    assert res["exit_reason"] == "STOPPED_EVIDENCE_FOUND"
    syms = {(f["path"], f["symbol"]) for f in res["functions"]}
    assert ("src/shape.py", "area") in syms
    assert ("src/shape.py", "Shape") in syms
    assert res["stage1"]["files"], "stage-1 shortlist recorded"
    assert res["stage2"]["iterations_used"] >= 1
    assert all(f["source_digest"] for f in res["functions"])
    se = res["stop_evidence"]
    assert se["question"] and se["direct_evidence"] and se["unresolved"]
    assert se["why_stop"]
    miss = out_json(LOC, "--repo", str(repo),
                    "--query", "unrelated zanzibar quantumentropy", "--json", ok=(0,))
    assert miss["exit_reason"] == "STOPPED_NO_EVIDENCE"
    assert miss["functions"] == []
    assert miss["stage2"]["visited"] == []
    assert miss["stop_evidence"]["why_stop"]


# ------------------------------------------------- 5. router consumes structural edges
def test_router_expansion_follows_structural_edges(repo):
    sys.path.insert(0, str(ROUTER.parent))
    import retrieval_router as rr  # noqa: E402
    corpus = rr.Corpus(repo)
    # lifted file-level edges exist (imports + calls between the two files)
    targets = {t for t, _ in corpus.structural_adj.get("src/shape.py", [])}
    assert "src/base.py" in targets
    expanded = rr.graph_expand(corpus, [("src/shape.py", 1.0)], max_depth=2, max_nodes=10)
    reached = {p for p, _, _, _ in expanded}
    assert "src/base.py" in reached, "expansion must traverse the semantic edge"
    via = {v for p, _, v, _ in expanded if p == "src/base.py"}
    assert any(("imports" in v or "calls" in v or "inherits" in v) for v in via), \
        "the expansion records the relation that carried it"
