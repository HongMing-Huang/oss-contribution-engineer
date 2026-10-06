#!/usr/bin/env python3
"""V5.3 closure tests: rules-reading receipts, complexity delta, two hats.

Run: python3 -m pytest tests/test_v53_closure.py -q
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import contribution_session as cs  # noqa: E402

SESSION = SCRIPTS / "contribution_session.py"
SCAN = SCRIPTS / "contribution_rules_scan.py"
SCOPE = SCRIPTS / "diff_scope_check.py"
GOAL = SCRIPTS / "goal_compiler.py"


def run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/env", "python3", str(script), *args],
                          capture_output=True, text=True, shell=False)


def git(repo: Path, *args: str) -> str:
    p = subprocess.run(["/usr/bin/env", "git", "-C", str(repo), *args],
                       capture_output=True, text=True, shell=False)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def _args(**kw):
    class A:
        pass
    a = A()
    for k, v in kw.items():
        setattr(a, k, v)
    return a


@pytest.fixture()
def repo(tmp_path: Path):
    subprocess.run(["/usr/bin/env", "git", "init", "-q", str(tmp_path)],
                   capture_output=True)
    git(tmp_path, "config", "user.email", "t@t.co")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "CONTRIBUTING.md").write_text(
        "# Contributing\n\nAll patches need a test. Sign your commits.\n")
    (tmp_path / "mod.py").write_text("def target():\n    return 1\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def compiled_goal(repo: Path, task: str) -> str:
    r = subprocess.run(
        ["/usr/bin/env", "python3", str(GOAL), str(repo), "compile",
         "--task-id", task, "--intent", "fix target", "--done-when", "run: true",
         "--repository", cs.repository_identity(repo)],
        capture_output=True, text=True, shell=False)
    assert r.returncode == 0, r.stderr
    goals = sorted((repo / ".oss-contrib-evidence" / "goals").glob("*.json"))
    return str(goals[-1])


def binding_manifest(repo: Path) -> tuple[str, dict]:
    r = subprocess.run(["/usr/bin/env", "python3", str(SCAN), "binding-manifest",
                        str(repo)], capture_output=True, text=True, shell=False)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip(), json.loads(r.stdout)


def read_receipt(repo: Path, manifest_path: str,
                 claimed: list[str]) -> subprocess.CompletedProcess:
    args = ["read-receipt", str(repo), "--manifest", manifest_path]
    for c in claimed:
        args += ["--claimed", c]
    return subprocess.run(["/usr/bin/env", "python3", str(SCAN), *args],
                          capture_output=True, text=True, shell=False)


def record_discovered(repo: Path, manifest_out: str) -> None:
    assert cs.cmd_record(repo, _args(kind="rules-discovered",
                                     file=[manifest_out], conclusion=None,
                                     reason=None)) == 0


def record_read(repo: Path, receipt_path: str) -> None:
    assert cs.cmd_record(repo, _args(kind="rules-read", file=[receipt_path],
                                     conclusion=None, reason=None)) == 0


def full_rules_flow(repo: Path) -> Path:
    r = subprocess.run(
        ["/usr/bin/env", "python3", str(GOAL), str(repo), "compile",
         "--task-id", "t1", "--intent", "fix target", "--done-when", "run: true",
         "--repository", cs.repository_identity(repo)],
        capture_output=True, text=True, shell=False)
    assert r.returncode == 0, r.stderr
    goal = sorted((repo / ".oss-contrib-evidence" / "goals").glob("*.json"))[-1]
    r = run(SESSION, str(repo), "init", "--task-id", "t1", "--goal", str(goal))
    assert r.returncode == 0, r.stderr
    manifest_out, _ = binding_manifest(repo)
    p = repo / "rules-discovered.json"
    p.write_text(manifest_out)
    record_discovered(repo, str(p))
    # recon artifact is also required at CANDIDATE (V5.2 gate)
    base = git(repo, "rev-parse", "HEAD")
    repo_id = cs.repository_identity(repo)
    body = {"type": "REPOSITORY_RECON", "schema_version": 1,
            "repository": repo_id, "repository_id": repo_id,
            "base_sha": base, "generated_by": "test",
            "created_at": "2026-10-06T00:00:00Z"}
    body["digest"] = hashlib.sha256(
        json.dumps(body, sort_keys=True).encode()).hexdigest()
    recon = repo / "recon.json"
    recon.write_text(json.dumps(body, indent=2))
    assert cs.cmd_record(repo, _args(kind="recon", file=[str(recon)],
                                     conclusion=None, reason=None)) == 0
    return p


def advance(repo: Path, to: str) -> int:
    return cs.cmd_advance(repo, _args(to=to))


def advance_through(repo: Path, states):
    for st in states:
        assert advance(repo, st) == 0, st


# ------------------------------------------------- 1. rules receipts
def test_rules_discovered_without_read_blocks_candidate(repo):
    full_rules_flow(repo)
    assert advance(repo, "RECON") == 0
    assert advance(repo, "CANDIDATE") == 1
    s = cs.load_session(repo)
    assert any("not proven fully read" in b for b in s["blockers"])


def test_rules_read_receipt_unblocks_candidate(repo):
    full_rules_flow(repo)
    assert advance(repo, "RECON") == 0
    manifest_out, _ = binding_manifest(repo)
    mf = repo / "rules-manifest.json"
    mf.write_text(manifest_out)
    rr = read_receipt(repo, str(mf),
                      ["CONTRIBUTING.md::root::governs all patches"])
    assert rr.returncode == 0, rr.stderr
    receipt_path = repo / "rules-read.json"
    receipt_path.write_text(rr.stdout)
    record_read(repo, str(receipt_path))
    assert advance(repo, "CANDIDATE") == 0
    s = cs.load_session(repo)
    assert s["artifacts"]["rules_read"]


def test_changed_binding_doc_detected_on_fresh_read(repo):
    p = full_rules_flow(repo)
    assert advance(repo, "RECON") == 0
    (repo / "CONTRIBUTING.md").write_text("# Contributing\n\nCHANGED rules.\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "rules change")
    # the recorded RULES_DISCOVERED digest binds the pre-change content; a fresh
    # read-receipt against the CHANGED content carries a different digest, so
    # the runtime's coverage check (digest equality) refuses the stale claim
    rr = read_receipt(repo, p, ["CONTRIBUTING.md::root::stale claim"])
    receipt = json.loads(rr.stdout)
    # SECURE: the doc changed after the scan — the OLD manifest's digest no
    # longer matches, so the claim is refused (not covered). Recovery is
    # re-scan + re-read, never a silent stale pass.
    assert receipt["covered"] == [], \
        "a claim against a changed doc must not be covered by the stale manifest"
    assert any("changed since the scan" in pr for pr in receipt.get("problems", [])), \
        "the receipt must name the digest mismatch"
    # recovery: re-scan produces a fresh manifest bound to the new content
    manifest_out2, _ = binding_manifest(repo)
    mf2 = repo / "rules-manifest-2.json"
    mf2.write_text(manifest_out2)
    rr2 = read_receipt(repo, str(mf2),
                       ["CONTRIBUTING.md::root::re-read after change"])
    receipt2 = json.loads(rr2.stdout)
    current = hashlib.sha256((repo / "CONTRIBUTING.md").read_bytes()).hexdigest()
    covered2 = {c["path"]: c["digest"] for c in receipt2["covered"]}
    assert covered2.get("CONTRIBUTING.md") == current, \
        "after re-scan + re-read the claim binds to the changed content"


def test_ack_and_gate_flow(repo):
    full_rules_flow(repo)
    assert advance(repo, "RECON") == 0
    manifest_out, _ = binding_manifest(repo)
    mf = repo / "rules-manifest.json"
    mf.write_text(manifest_out)
    rr = read_receipt(repo, str(mf),
                      ["CONTRIBUTING.md::root::governs all patches"])
    receipt_path = repo / "rules-read.json"
    receipt_path.write_text(rr.stdout)
    record_read(repo, str(receipt_path))
    assert advance(repo, "CANDIDATE") == 0


# ------------------------------------------------- 3/4. delta + two hats
def scope_json(repo: Path, hats: str = "") -> dict:
    r = subprocess.run(
        ["/usr/bin/env", "python3", str(SCOPE), str(repo), "--base", "HEAD",
         "--hats", hats, "--show-hats", "--show-delta", "--json"],
        capture_output=True, text=True, shell=False)
    assert r.returncode in (0, 1), r.stderr
    return json.loads(r.stdout)


def test_complexity_delta_counts_new_concepts(repo):
    (repo / "mod.py").write_text(
        "def target():\n    return 1\n\n\ndef new_helper(x):\n"
        "    if x:\n        return 2\n    return 3\n")
    r = scope_json(repo)
    d = r["complexity_delta"]
    assert d["new_symbols"] >= 1, "new def must be counted (new_helper; target is retained context)"
    assert d["new_branches"] >= 1, "new if branch must be counted"
    assert d["added_lines_production"] > 0


def test_two_hats_classification(repo):
    # committed baseline first
    (repo / "target.py").write_text("def target():\n    return 1\n")
    (repo / "test_target.py").write_text("def test_target():\n    assert True\n")
    (repo / "style.py").write_text("x=1\n")
    (repo / "newmod.py").write_text("placeholder\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "sources")
    # working tree: whitespace tweak, test tweak, reformat, new symbols
    (repo / "target.py").write_text("def target():\n    return 1  \n")
    (repo / "test_target.py").write_text("def test_target():\n    assert True\n\n")
    (repo / "style.py").write_text("x = 1\n")
    (repo / "newmod.py").write_text("def brand_new():\n    return 2\n")
    r = scope_json(repo, hats="newmod.py=REFACTOR")
    hats = {h["path"]: h.get("hat") for h in r["hats"]}
    print("HATS:", hats)
    assert hats["test_target.py"] == "TEST"
    assert hats["style.py"] == "MECHANICAL"
