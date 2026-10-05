#!/usr/bin/env python3
"""Black-box lifecycle tests: run the PUBLIC runtime interface (the
contribution_session.py CLI as a subprocess) against disposable repositories.

No internal functions are imported or mocked — this proves externally observable
behavior: the happy contribution path and the negative scenarios.

Run: python3 -m pytest tests/test_black_box_lifecycle.py -q
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
SESSION = SCRIPTS / "contribution_session.py"
EVIDENCE = SCRIPTS / "evidence_manifest.py"


def run(repo: Path, script: Path, *args: str) -> subprocess.CompletedProcess:
    # argv list with a literal loader head + shell=False (no shell ever parses it)
    return subprocess.run(["/usr/bin/env", "python3", str(script), str(repo), *args],
                          capture_output=True, text=True, shell=False)


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
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def goal_file(repo: Path) -> str:
    g = repo / "goal.json"
    g.write_text(json.dumps({
        "contract_version": 1, "task_id": "bb", "intent": "fix target",
        "done_when": [{"criterion": "run: true", "observable": True,
                       "how_observed": "run"}],
        "digest": "bb-digest",
    }))
    return str(g)


def legal_next(repo: Path) -> str | None:
    out = run(repo, SESSION, "status").stdout
    for line in out.splitlines():
        if line.startswith("next legal:"):
            return line.split("next legal:")[1].strip()
    return None


def evidence(repo: Path, purpose: str, *extra: str, ok: bool = True) -> subprocess.CompletedProcess:
    return run(repo, EVIDENCE, "record", "--purpose", purpose, *extra, "--",
               "/usr/bin/env", "python3", "-c",
               "pass" if ok else "raise SystemExit(1)")


def record(repo: Path, kind: str, *file: str) -> subprocess.CompletedProcess:
    args = ["record", "--kind", kind]
    for f in file:
        args += ["--file", f]
    return run(repo, SESSION, *args)


def test_full_happy_path_to_pr_ready(repo):
    r = run(repo, SESSION, "init", "--task-id", "bb1", "--goal", goal_file(repo))
    assert r.returncode == 0, r.stderr
    assert legal_next(repo) == "RECON"

    marker = repo / "recon.json"
    marker.write_text("{}")
    assert record(repo, "recon", str(marker)).returncode == 0
    assert run(repo, SESSION, "advance", "--to", "RECON").returncode == 0
    assert record(repo, "dedupe", str(marker)).returncode == 0
    assert run(repo, SESSION, "advance", "--to", "CANDIDATE").returncode == 0
    assert run(repo, SESSION, "set-classification",
               "--classification", "GOOD_CANDIDATE").returncode == 0
    assert run(repo, SESSION, "advance", "--to", "DEDUPLICATE").returncode == 0
    assert run(repo, SESSION, "advance", "--to", "PROVE").returncode == 0

    # PROVE → RED needs reproduction evidence through the witness script
    assert run(repo, SESSION, "advance", "--to", "RED").returncode == 1
    assert evidence(repo, "reproduce the bug: actual behavior").returncode == 0
    assert run(repo, SESSION, "advance", "--to", "RED").returncode == 0

    # RED → PATCH needs an expect-fail witness AND granted WORKTREE_EDIT
    r = run(repo, SESSION, "advance", "--to", "PATCH")
    assert r.returncode == 1
    assert evidence(repo, "RED: test fails on unmodified upstream",
                    "--expect-fail", ok=False).returncode == 0
    r = run(repo, SESSION, "set-authority", "--grant", "worktree_edit",
            "--evidence-ref", "user said ok in chat", "--by-user", "user")
    assert r.returncode == 0, r.stderr
    assert run(repo, SESSION, "advance", "--to", "PATCH").returncode == 0

    assert record(repo, "patch-intent", str(marker)).returncode == 0
    (repo / "mod.py").write_text("def target():\n    return 2\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "fix target")
    assert evidence(repo, "GREEN: regression passes after fix",
                    "--head-bound").returncode == 0
    assert run(repo, SESSION, "advance", "--to", "GREEN").returncode == 0
    assert run(repo, SESSION, "advance", "--to", "REGRESSION").returncode == 0
    assert run(repo, SESSION, "advance",
               "--to", "CONTRIBUTOR_UNDERSTANDING").returncode == 0
    # the agent cannot mark UNDERSTOOD; DEFERRED is legal without a human name
    r = run(repo, SESSION, "set-understanding", "--status", "UNDERSTOOD")
    assert r.returncode == 2
    assert run(repo, SESSION, "set-understanding",
               "--status", "DEFERRED").returncode == 0
    assert run(repo, SESSION, "advance", "--to", "REVIEW").returncode == 0
    assert run(repo, SESSION, "record", "--kind", "scope-audit",
               "--conclusion", "WITHIN_SCOPE").returncode == 0
    assert run(repo, SESSION, "advance", "--to", "PR_READY").returncode == 0
    assert "PR_READY" in run(repo, SESSION, "status").stdout


def test_skip_red_is_refused(repo):
    run(repo, SESSION, "init", "--task-id", "bb2", "--goal", goal_file(repo))
    marker = repo / "r.json"
    marker.write_text("{}")
    record(repo, "recon", str(marker))
    run(repo, SESSION, "advance", "--to", "RECON")
    record(repo, "dedupe", str(marker))
    run(repo, SESSION, "advance", "--to", "CANDIDATE")
    run(repo, SESSION, "set-classification", "--classification", "GOOD_CANDIDATE")
    run(repo, SESSION, "advance", "--to", "DEDUPLICATE")
    run(repo, SESSION, "advance", "--to", "PROVE")
    # jump straight toward the patch side: RED refused without reproduction
    r = run(repo, SESSION, "advance", "--to", "RED")
    assert r.returncode == 1
    assert "reproduction evidence" in r.stderr
    # and the session state did not move
    assert "state: PROVE" in run(repo, SESSION, "status").stdout


def test_scope_drift_blocks_pr_ready(repo):
    run(repo, SESSION, "init", "--task-id", "bb3", "--goal", goal_file(repo))
    marker = repo / "r.json"
    marker.write_text("{}")
    record(repo, "recon", str(marker))
    run(repo, SESSION, "advance", "--to", "RECON")
    record(repo, "dedupe", str(marker))
    run(repo, SESSION, "advance", "--to", "CANDIDATE")
    run(repo, SESSION, "set-classification", "--classification", "GOOD_CANDIDATE")
    run(repo, SESSION, "advance", "--to", "DEDUPLICATE")
    run(repo, SESSION, "advance", "--to", "PROVE")
    evidence(repo, "reproduce the bug")
    run(repo, SESSION, "advance", "--to", "RED")
    evidence(repo, "RED: test fails on unmodified upstream",
             "--expect-fail", ok=False)
    run(repo, SESSION, "set-authority", "--grant", "worktree_edit",
        "--evidence-ref", "ok", "--by-user", "u")
    run(repo, SESSION, "advance", "--to", "PATCH")
    record(repo, "patch-intent", str(marker))
    (repo / "mod.py").write_text("def target():\n    return 2\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "fix")
    evidence(repo, "GREEN: passes", "--head-bound")
    run(repo, SESSION, "advance", "--to", "GREEN")
    run(repo, SESSION, "advance", "--to", "REGRESSION")
    run(repo, SESSION, "advance", "--to", "CONTRIBUTOR_UNDERSTANDING")
    run(repo, SESSION, "set-understanding", "--status", "DEFERRED")
    run(repo, SESSION, "advance", "--to", "REVIEW")
    # scope drift recorded as SCOPE_FINDINGS and never acknowledged
    run(repo, SESSION, "record", "--kind", "scope-audit",
        "--conclusion", "SCOPE_FINDINGS")
    r = run(repo, SESSION, "advance", "--to", "PR_READY")
    assert r.returncode == 1
    assert "SCOPE_FINDINGS" in r.stderr


def test_duplicate_stops_black_box(repo):
    run(repo, SESSION, "init", "--task-id", "bb4", "--goal", goal_file(repo))
    marker = repo / "r.json"
    marker.write_text("{}")
    record(repo, "recon", str(marker))
    run(repo, SESSION, "advance", "--to", "RECON")
    record(repo, "dedupe", str(marker))
    run(repo, SESSION, "advance", "--to", "CANDIDATE")
    run(repo, SESSION, "set-classification", "--classification", "PR_EXISTS")
    run(repo, SESSION, "advance", "--to", "DEDUPLICATE")
    run(repo, SESSION, "advance", "--to", "PROVE")
    evidence(repo, "reproduce the bug")
    r = run(repo, SESSION, "advance", "--to", "RED")
    assert r.returncode == 1
    assert "stopping outcome" in r.stderr


def test_closed_not_merged_black_box(repo):
    run(repo, SESSION, "init", "--task-id", "bb5", "--goal", goal_file(repo))
    sf = repo / ".oss-contrib-evidence" / "session.json"
    s = json.loads(sf.read_text())
    s["state"] = "PR_READY"
    s["scope_audit"] = {"conclusion": "WITHIN_SCOPE"}
    s["understanding"] = {"status": "DEFERRED"}
    s["authority"]["remote_write"] = True
    sf.write_text(json.dumps(s))
    pr = repo / "pr.json"
    pr.write_text(json.dumps({"pr": {"number": 5, "state": "closed", "merged": False,
                                     "user": {"login": "a"}}, "reviews": [],
                              "timeline": []}))
    r = run(repo, SESSION, "upstream", "--pr-json", str(pr))
    assert r.returncode == 0
    assert "CLOSED_NOT_MERGED" in r.stdout
    assert "NOT a merged contribution" in r.stdout
    r = run(repo, SESSION, "advance", "--to", "IN_REVIEW")
    assert r.returncode == 0
    out = run(repo, SESSION, "status").stdout
    assert "CLOSED_NOT_MERGED" in out


def test_reconstruct_after_restart_black_box(repo):
    run(repo, SESSION, "init", "--task-id", "bb6", "--goal", goal_file(repo))
    r = run(repo, SESSION, "reconstruct")
    assert r.returncode == 0
    assert "RECONSTRUCTED" in r.stdout and "DISCOVER" in r.stdout
