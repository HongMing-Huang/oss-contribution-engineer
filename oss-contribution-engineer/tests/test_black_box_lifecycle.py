#!/usr/bin/env python3
"""V5.1 black-box lifecycle tests: the public CLI against disposable repos.

Only subprocess calls to scripts/contribution_session.py,
evidence_manifest.py and budget_governor.py — no internal imports, no direct
session.json edits. Proves externally observable behavior.

Run: python3 -m pytest tests/test_black_box_lifecycle.py -q
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
SESSION = SCRIPTS / "contribution_session.py"
EVIDENCE = SCRIPTS / "evidence_manifest.py"
GOVERNOR = SCRIPTS / "budget_governor.py"


def run(script: Path, repo: Path | None, *args: str) -> subprocess.CompletedProcess:
    """Run a skill CLI. Every argv is a list with a literal loader head and
    shell=False — nothing is ever parsed by a shell. repo=None for
    repo-independent tools (budget_governor)."""
    argv = ["/usr/bin/env", "python3", str(script)]
    if repo is not None:
        argv.append(str(repo))
    argv += list(args)
    return subprocess.run(argv, capture_output=True, text=True, shell=False)


def git(repo: Path, *args: str) -> str:
    p = subprocess.run(["/usr/bin/env", "git", "-C", str(repo), *args],
                       capture_output=True, text=True, shell=False)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@t.co")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "mod.py").write_text("def target():\n    return 1\n")
    (tmp_path / "test_mod.py").write_text(
        "def test_target():\n    assert target() is not None\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def goal_file(repo: Path) -> str:
    g = repo / "goal.json"
    g.write_text(json.dumps({"contract_version": 1, "task_id": "bb",
                             "intent": "fix target", "digest": "bb-digest"}))
    return str(g)


def structured_artifact(repo: Path, name: str, a_type: str,
                        extra: dict | None = None) -> str:
    body = {"type": a_type, "schema_version": 1, "repository": "r",
            "base_sha": "a" * 40, "generated_by": "test-script",
            "created_at": "2026-10-06T00:00:00Z"}
    body.update(extra or {})
    body["digest"] = hashlib.sha256(
        json.dumps(body, sort_keys=True).encode()).hexdigest()
    p = repo / name
    p.write_text(json.dumps(body, indent=2))
    return str(p)


def evidence(repo: Path, purpose: str, etype: str, *extra: str, ok: bool = True,
             regression_id: str | None = None) -> subprocess.CompletedProcess:
    args = ["record", "--purpose", purpose, "--evidence-type", etype]
    if regression_id:
        args += ["--regression-id", regression_id]
    args += list(extra)
    args += ["--", "/usr/bin/env", "python3", "-c",
             "pass" if ok else "raise SystemExit(1)"]
    return run(EVIDENCE, str(repo), *args)


def init_and_reach(repo: Path, task: str, state: str, artifacts=True):
    run(SESSION, str(repo), "init", "--task-id", task, "--goal", goal_file(repo))
    if artifacts:
        run(SESSION, str(repo), "record", "--kind", "recon",
            "--file", structured_artifact(repo, "recon.json", "REPOSITORY_RECON"))
        run(SESSION, str(repo), "record", "--kind", "dedupe",
            "--file", structured_artifact(repo, "dedupe.json", "DUPLICATE_WORK_EVIDENCE"))
    for st in ("RECON", "CANDIDATE"):
        run(SESSION, str(repo), "advance", "--to", st)
    if artifacts:
        run(SESSION, str(repo), "advance", "--to", "DEDUPLICATE")
        run(SESSION, str(repo), "set-classification",
            "--classification", "GOOD_CANDIDATE")
        run(SESSION, str(repo), "advance", "--to", "PROVE")


def test_happy_path_to_pr_ready_with_typed_evidence(repo):
    init_and_reach(repo, "bb1", "PROVE")
    # general-typed reproduction does not satisfy the RED gate
    assert evidence(repo, "reproduce the bug", "GENERAL").returncode == 0
    assert run(SESSION, str(repo), "advance", "--to", "RED").returncode == 1
    assert evidence(repo, "reproduce the bug", "REPRODUCTION").returncode == 0
    assert run(SESSION, str(repo), "advance", "--to", "RED").returncode == 0
    # RED → PATCH needs typed RED witness + production unmodified + authority
    assert evidence(repo, "RED: fails on unmodified upstream", "RED_REGRESSION",
                    "--expect-fail", "--regression-id", "R1", "--test-file",
                    str(repo / "test_mod.py"), ok=False).returncode == 0
    assert run(SESSION, str(repo), "advance", "--to", "PATCH").returncode == 1
    assert run(SESSION, str(repo), "set-authority", "--grant", "worktree_edit",
               "--evidence-ref", "user ok", "--by-user", "user").returncode == 0
    assert run(SESSION, str(repo), "advance", "--to", "PATCH").returncode == 0
    marker = repo / "plan.md"
    marker.write_text("intent")
    run(SESSION, str(repo), "record", "--kind", "patch-intent", "--file", str(marker))
    (repo / "mod.py").write_text("def target():\n    return 2\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "fix")
    # wrong regression id accepted into GREEN but refused at REGRESSION
    assert evidence(repo, "GREEN wrong id", "GREEN_REGRESSION", "--head-bound",
                    "--regression-id", "R-other",
                    "--test-file", str(repo / "test_mod.py")).returncode == 0
    assert run(SESSION, str(repo), "advance", "--to", "GREEN").returncode == 0
    assert run(SESSION, str(repo), "advance", "--to", "REGRESSION").returncode == 1
    assert evidence(repo, "GREEN for R1", "GREEN_REGRESSION", "--head-bound",
                    "--regression-id", "R1",
                    "--test-file", str(repo / "test_mod.py")).returncode == 0
    assert run(SESSION, str(repo), "advance", "--to", "REGRESSION").returncode == 0
    assert run(SESSION, str(repo), "advance",
               "--to", "CONTRIBUTOR_UNDERSTANDING").returncode == 0
    run(SESSION, str(repo), "set-understanding", "--status", "DEFERRED")
    assert run(SESSION, str(repo), "advance", "--to", "REVIEW").returncode == 0
    sa = structured_artifact(repo, "scope.json", "SCOPE_AUDIT",
                             {"conclusion": "WITHIN_SCOPE"})
    run(SESSION, str(repo), "record", "--kind", "scope-audit", "--file", sa,
        "--conclusion", "WITHIN_SCOPE")
    assert run(SESSION, str(repo), "advance", "--to", "PR_READY").returncode == 0
    assert "PR_READY" in run(SESSION, str(repo), "status").stdout


def test_production_edit_before_red_rejected(repo):
    init_and_reach(repo, "bb2", "PROVE")
    evidence(repo, "reproduce the bug", "REPRODUCTION")
    run(SESSION, str(repo), "advance", "--to", "RED")
    evidence(repo, "RED: fails", "RED_REGRESSION", "--expect-fail",
             "--regression-id", "R1", ok=False)
    (repo / "mod.py").write_text("def target():\n    return 99\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "premature edit")
    run(SESSION, str(repo), "set-authority", "--grant", "worktree_edit",
        "--evidence-ref", "ok", "--by-user", "u")
    r = run(SESSION, str(repo), "advance", "--to", "PATCH")
    assert r.returncode == 1
    assert "already modified" in r.stderr


def test_invalid_recon_and_dedupe_artifacts_rejected(repo):
    run(SESSION, str(repo), "init", "--task-id", "bb3", "--goal", goal_file(repo))
    junk = repo / "junk.json"
    junk.write_text("{}")
    r = run(SESSION, str(repo), "record", "--kind", "recon", "--file", str(junk))
    assert r.returncode == 0, "recording junk is allowed; the gate rejects it"
    assert run(SESSION, str(repo), "advance", "--to", "RECON").returncode == 0
    r = run(SESSION, str(repo), "advance", "--to", "CANDIDATE")
    assert r.returncode == 1
    assert "not a structured artifact" in r.stderr
    good = structured_artifact(repo, "recon.json", "REPOSITORY_RECON")
    run(SESSION, str(repo), "record", "--kind", "recon", "--file", good)
    assert run(SESSION, str(repo), "advance", "--to", "CANDIDATE").returncode == 0
    junk2 = repo / "dedupe-junk.json"
    junk2.write_text("{}")
    run(SESSION, str(repo), "record", "--kind", "dedupe", "--file", str(junk2))
    r = run(SESSION, str(repo), "advance", "--to", "DEDUPLICATE")
    assert r.returncode == 1
    assert "not a structured artifact" in r.stderr


def test_captured_pr_grants_no_authorization(repo):
    init_and_reach(repo, "bb6", "PROVE", artifacts=False)
    run(SESSION, str(repo), "advance", "--to", "DEDUPLICATE")
    pr = repo / "pr.json"
    pr.write_text(json.dumps({"pr": {"number": 9, "state": "open",
                                     "user": {"login": "a"}},
                              "reviews": [], "timeline": []}))
    r = run(SESSION, str(repo), "upstream", "--pr-json", str(pr))
    assert r.returncode == 0
    assert "grants no remote authorization" in r.stdout
    sf = repo / ".oss-contrib-evidence" / "session.json"
    s = json.loads(sf.read_text())
    assert s["upstream"]["observed"] is True
    assert s["authority"].get("remote_write") is None
    assert s["authority"]["actions"] == []
    # observation changed nothing about authority; workflow still linear
    assert "state: RECON" in run(SESSION, str(repo), "status").stdout
    s2 = json.loads(sf.read_text())
    assert s2["state"] == "RECON"
    assert s2["authority"]["actions"] == []


def test_deferred_cannot_reach_in_review(repo):
    init_and_reach(repo, "bb7", "PROVE")
    evidence(repo, "reproduce the bug", "REPRODUCTION")
    run(SESSION, str(repo), "advance", "--to", "RED")
    evidence(repo, "RED: fails", "RED_REGRESSION", "--expect-fail",
             "--regression-id", "R1", "--test-file", str(repo / "test_mod.py"),
             ok=False)
    run(SESSION, str(repo), "set-authority", "--grant", "worktree_edit",
        "--evidence-ref", "ok", "--by-user", "u")
    run(SESSION, str(repo), "advance", "--to", "PATCH")
    marker = repo / "p.md"; marker.write_text("i")
    run(SESSION, str(repo), "record", "--kind", "patch-intent", "--file", str(marker))
    (repo / "mod.py").write_text("def target():\n    return 2\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "fix")
    evidence(repo, "GREEN passes", "GREEN_REGRESSION", "--head-bound",
             "--regression-id", "R1", "--test-file", str(repo / "test_mod.py"))
    run(SESSION, str(repo), "advance", "--to", "GREEN")
    run(SESSION, str(repo), "advance", "--to", "REGRESSION")
    run(SESSION, str(repo), "advance", "--to", "CONTRIBUTOR_UNDERSTANDING")
    run(SESSION, str(repo), "set-understanding", "--status", "DEFERRED")
    run(SESSION, str(repo), "advance", "--to", "REVIEW")
    sa = structured_artifact(repo, "scope.json", "SCOPE_AUDIT",
                             {"conclusion": "WITHIN_SCOPE"})
    run(SESSION, str(repo), "record", "--kind", "scope-audit", "--file", sa,
        "--conclusion", "WITHIN_SCOPE")
    assert run(SESSION, str(repo), "advance", "--to", "PR_READY").returncode == 0
    r = run(SESSION, str(repo), "advance", "--to", "IN_REVIEW")
    assert r.returncode == 1
    assert "UNDERSTOOD" in r.stderr


def test_budget_govern_cli(repo):
    # real span costs: hub 1-100 → 1000 est, a 10-20 → 110 est; total 1110 < soft
    # 12000, so nothing is pruned and the digest/accounting only get normalized.
    # To exercise pruning we make the structural span dominate: 1-1500 → 15000 est.
    pack = {"pack_version": 2, "type": "CONTEXT_PACK", "schema_version": 1,
            "token_accounting": {"source_used_est": 15110, "test_used_est": 0},
            "source_ranges": [
                {"path": "hub.py", "symbol": "hub", "lines": "1-1500",
                 "evidence": [{"family": "repomap", "rank": 1}]},
                {"path": "a.py", "symbol": "a", "lines": "10-20",
                 "evidence": [{"family": "lexical", "rank": 1}]},
            ],
            "tests": [], "excluded": [], "no_regret": {"displaced_direct": []}}
    body = {k: v for k, v in pack.items() if k != "pack_digest"}
    pack["pack_digest"] = hashlib.sha256(
        json.dumps(body, sort_keys=True).encode()).hexdigest()
    pf = repo / "pack.json"
    pf.write_text(json.dumps(pack, indent=2))
    old_digest = pack["pack_digest"]
    out = repo / "governed.json"
    r = run(GOVERNOR, "govern", str(pf), "--out", str(out))
    assert r.returncode == 0, r.stderr
    governed = json.loads(out.read_text())
    # structural-only hub (15000 est) pruned first; direct span preserved
    assert [s["path"] for s in governed["source_ranges"]] == ["a.py"]
    assert governed["no_regret"]["displaced_direct"] == []
    assert "hub.py" in [e.get("path") for e in governed["excluded"]]
    # accounting recomputed from spans: (20-10+1) lines * 40 / 4 = 110
    assert governed["token_accounting"]["source_used_est"] == 110
    # digest regenerated after pruning
    assert governed["pack_digest"] != old_digest
    # audit mode still works as its own surface
    r = run(GOVERNOR, "audit", str(out))
    assert r.returncode == 0


def test_govern_blocked_on_non_source_overflow(repo):
    # goal: BLOCKED is reachable — non-source category overflow cannot be pruned
    pack = {"pack_version": 2, "type": "CONTEXT_PACK", "schema_version": 1,
            "token_accounting": {"source_used_est": 0, "test_used_est": 50000},
            "source_ranges": [],
            "tests": [{"path": "tests/test_x.py", "lines": "1-100000"}],
            "excluded": [], "no_regret": {"displaced_direct": []}}
    pf = repo / "pack.json"
    pf.write_text(json.dumps(pack, indent=2))
    r = run(GOVERNOR, "govern", str(pf))
    assert r.returncode == 3  # BLOCKED
    assert "BLOCKED" in r.stdout
    assert r.returncode == 3  # BLOCKED
    assert "BLOCKED" in r.stdout


def test_reconstruct_after_restart(repo):
    run(SESSION, str(repo), "init", "--task-id", "bb8", "--goal", goal_file(repo))
    r = run(SESSION, str(repo), "reconstruct")
    assert r.returncode == 0
    assert "RECONSTRUCTED" in r.stdout and "DISCOVER" in r.stdout
