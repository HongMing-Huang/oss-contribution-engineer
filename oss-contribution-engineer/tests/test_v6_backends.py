#!/usr/bin/env python3
"""V6 backend-integration acceptance tests: AOCI_RUNTIME + symbol backend.

Run: python3 -m pytest tests/test_v6_backends.py -q
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

CONF = SCRIPTS / "aoci_conformance_server.py"
AOCI = SCRIPTS / "aoci_runtime.py"
SYM = SCRIPTS / "symbol_backend.py"
ROUTER = SCRIPTS / "retrieval_router.py"
SESSION_ARTIFACT = ".oss-contrib-evidence/aoci_runtime_session.json"


def run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/env", "python3", str(script), *args],
                          capture_output=True, text=True, shell=False, timeout=180)


def out_json(script: Path, *args: str) -> dict:
    p = run(script, *args)
    assert p.returncode in (0, 4), p.stderr
    return json.loads(p.stdout)


def srv(repo: Path, *flags: str) -> str:
    return "python3 %s serve --repo %s %s" % (CONF, repo, " ".join(flags))


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("AOCI_MCP_COMMAND", "SERENA_MCP_COMMAND"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def indexed_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "helper.py").write_text("def helper():\n    return 1\n")
    (repo / "src" / "app.py").write_text(
        "from src.helper import helper\n\n\ndef main():\n    return helper()\n")
    r = run(CONF, "build", "--repo", str(repo))
    assert r.returncode == 0, r.stderr
    return repo


def artifact(repo: Path) -> dict:
    return json.loads((repo / SESSION_ARTIFACT).read_text())


# ------------------------------------------------- 1. partial overview ≠ cognition
def test_partial_overview_cannot_masquerade_complete_cognition(indexed_repo):
    res = out_json(AOCI, "session", "--repo", str(indexed_repo),
                   "--mcp-command", srv(indexed_repo, "--fail-chunk", "1"))
    # a transport failure mid-chain is an EXPLICIT fallback: runtime attempted,
    # never used, cognition never claimed complete
    assert res["cognition_state"] == "FALLBACK"
    assert res["runtime_used"] is False
    fb = res["fallback"]
    assert fb["runtime_attempted"] is True and fb["runtime_used"] is False
    assert "incomplete" in fb["reason"]
    art = artifact(indexed_repo)
    assert art["cognition_state"] == "FALLBACK"
    assert art["index_identity"] is None
    # a surface that is not the pinned AOCI tool set is refused by name
    res2 = out_json(AOCI, "session", "--repo", str(indexed_repo),
                    "--mcp-command", srv(indexed_repo, "--no-tools"))
    assert res2["fallback"]["runtime_used"] is False
    assert "pinned AOCI contract" in res2["fallback"]["reason"]
    # and a search against the fallback session stays refused — the runtime was
    # never used, so nothing may pretend it was
    s = out_json(AOCI, "search", "--repo", str(indexed_repo), "--keyword", "helper",
                 "--mcp-command", srv(indexed_repo))
    assert s["ok"] is False and s["runtime_used"] is False


# ------------------------------------------------- 2. identity drift invalidates
def test_aoci_identity_drift_invalidates_receipt(indexed_repo):
    res = out_json(AOCI, "session", "--repo", str(indexed_repo),
                   "--mcp-command", srv(indexed_repo))
    assert res["cognition_state"] == "COMPLETE"
    assert res["attestation"]["challenge_passed"] is True
    good_identity = res["identity"]
    assert len(good_identity) == 64
    # mid-session drift on the read response → receipt invalidated, read refused
    d = out_json(AOCI, "search", "--repo", str(indexed_repo), "--keyword", "helper",
                 "--mcp-command", srv(indexed_repo, "--drift-generation"))
    assert d["ok"] is False and d.get("drift") is True
    assert "invalidated" in d["reason"]
    art = artifact(indexed_repo)
    assert art["cognition_state"] == "INVALIDATED_DRIFT"
    assert art["alignment_state"] == "drifted"
    assert art["receipt_digest"] is None


# ------------------------------------------------- 3. refs from the semantic backend
def test_symbol_references_come_from_selected_semantic_backend(indexed_repo):
    res = out_json(SYM, "find-references", "--repo", str(indexed_repo),
                   "--name", "helper", "--json")
    assert res["ok"] is True
    assert res["meta"]["selected_backend"] == "python-ast"
    rows = res["results"]
    assert rows, "helper is called in app.py"
    for r in rows:
        assert r["backend"] == "python-ast"
        assert r["relation"] in ("reference", "attribute_reference", "inherits")
        assert r["path"] == "src/app.py"
        # spans are exact AST positions, and the digest binds them to bytes
        assert r["source_digest"] == hashlib.sha256(
            (indexed_repo / "src" / "app.py").read_bytes()).hexdigest()
    # `from src.helper import helper` is an alias binding, not a Name Load, so
    # the ONLY real reference is the call at line 5 — exact AST semantics
    assert [(r["relation"], r["start_line"]) for r in rows] == [("reference", 5)]
    # definition side: exact span for helper()
    defs = out_json(SYM, "find-symbol", "--repo", str(indexed_repo),
                    "--name", "helper", "--json")["results"]
    assert defs == [{"path": "src/helper.py", "symbol": "helper", "kind": "function",
                     "start_line": 1, "end_line": 2,
                     "source_digest": defs[0]["source_digest"],
                     "relation": "definition", "backend": "python-ast"}]


# ------------------------------------------------- 4. source digest drift detected
def test_source_digest_drift_detected(indexed_repo):
    r = run(SYM, "index", "--repo", str(indexed_repo))
    assert r.returncode == 0
    q1 = out_json(SYM, "query-index", "--repo", str(indexed_repo),
                  "--name", "helper", "--json")
    assert all(v == "CURRENT" for v in q1["verification"].values())
    (indexed_repo / "src" / "helper.py").write_text(
        "def helper():\n    return 1  # changed after indexing\n")
    q2 = out_json(SYM, "query-index", "--repo", str(indexed_repo),
                  "--name", "helper", "--json")
    assert q2["verification"]["src/helper.py"] == "CHANGED"
    assert q2["verification"]["src/app.py"] == "CURRENT"


# ------------------------------------------------- 5. explicit fallback, no backend
def test_fallback_when_external_backend_unavailable(tmp_path):
    repo = tmp_path / "plain"
    repo.mkdir()
    (repo / "util.py").write_text("def util():\n    return 2\n")
    res = out_json(AOCI, "session", "--repo", str(repo))
    assert res["cognition_state"] == "FALLBACK"
    fb = res["fallback"]
    assert fb["runtime_attempted"] is False and fb["runtime_used"] is False
    assert "configured" in fb["reason"]
    # the router falls through honestly: no runtime receipt is upgradeable
    p = run(ROUTER, str(repo), "find util", "--task-type", "issue2code", "--json")
    assert p.returncode == 0
    report = json.loads(p.stdout)
    assert report["backend"]["kind"] == "LIGHTWEIGHT_FALLBACK"
    assert report["candidates"], "plain lexical routing still works"
    assert "symbol_backend" not in report["backends"]


# ------------------------------------------------- 6. router consumes both backends
def test_router_consumes_backend_provenance(indexed_repo):
    assert run(SYM, "index", "--repo", str(indexed_repo)).returncode == 0
    res = out_json(AOCI, "session", "--repo", str(indexed_repo),
                   "--mcp-command", srv(indexed_repo))
    assert res["cognition_state"] == "COMPLETE"
    p = run(ROUTER, str(indexed_repo), "where is helper defined",
            "--task-type", "issue2code", "--json")
    report = json.loads(p.stdout)
    assert report["backend"]["kind"] == "AOCI_RUNTIME"
    assert report["backend"]["identity"] == res["identity"]
    assert report["backends"]["symbol_backend"]["backend"] == "python-ast"
    assert report["backends"]["cognition"]["kind"] == "AOCI_RUNTIME"
    top = report["candidates"][0]
    reason = " ".join(c["reason"] for c in report["candidates"])
    assert "python-ast" in reason and "aoci-runtime@" in reason
    sb = [e for c in report["candidates"] for e in c["evidence"]
          if e["family"] == "symbol_backend"]
    assert sb and all(e["backend"] == "python-ast" for e in sb)
    assert any(e.get("source_digest_state") == "CURRENT" for e in sb)
    cog = [e for c in report["candidates"] for e in c["evidence"]
           if e["family"] == "cognition"]
    assert any(e.get("backend", "").startswith("aoci-runtime@") for e in cog)
