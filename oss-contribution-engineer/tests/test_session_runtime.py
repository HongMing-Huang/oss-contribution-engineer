#!/usr/bin/env python3
"""Integration tests for the V5 runtime spine (contribution_session.py).

These exercise the actual runtime code against disposable git repositories:
gates, authority, staleness, stopping outcomes, restart reconstruction.
Run: python3 -m pytest tests/test_session_runtime.py -q
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import contribution_session as cs  # noqa: E402
import evidence_manifest as em  # noqa: E402


def git(repo: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args],
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


def contract(repo: Path) -> Path:
    g = repo / "goal.json"
    g.write_text(json.dumps({
        "contract_version": 1, "task_id": "t1", "intent": "fix target",
        "done_when": [{"criterion": "run: true", "observable": True,
                       "how_observed": "run"}],
        "digest": "test-digest-not-verified-by-runtime",
    }))
    return g


def init_session(repo: Path) -> dict:
    session = {
        "session_version": 1, "task_id": "t1", "repository": "r",
        "base_sha": git(repo, "rev-parse", "HEAD"),
        "state": "DISCOVER",
        "goal": {"digest": "test-digest", "path": str(contract(repo))},
        "authority": {"read": True, "worktree_edit": False, "remote_write": False,
                      "grants": []},
        "context": {"plan": None, "pack": None, "receipt": None},
        "artifacts": {}, "classification": None,
        "understanding": {"status": None, "confirmed_by": None},
        "scope_audit": {}, "upstream": {}, "blockers": [], "history": [],
    }
    cs.save_session(repo, session)
    return session


def record_artifacts(repo: Path):
    marker = repo / "recon-evidence.json"
    marker.write_text("{}")
    for kind in ("recon", "dedupe"):
        assert cs.cmd_record(repo, _args(kind=kind, file=[str(marker)],
                                          conclusion=None, reason=None)) == 0, kind


def advance_through(repo: Path, states: list[str]):
    for st in states:
        assert advance(repo, st) == 0, st


def to_prove(repo: Path):
    init_session(repo)
    record_artifacts(repo)
    advance_through(repo, ["RECON", "CANDIDATE", "DEDUPLICATE"])
    assert cs.cmd_set_classification(
        repo, _args(classification="GOOD_CANDIDATE")) == 0
    advance_through(repo, ["PROVE"])


def witness(repo: Path, purpose: str, expect_fail=False, head_bound=False,
            status_ok=True) -> dict:
    argv = [sys.executable, "-c", "pass" if status_ok else "raise SystemExit(1)"]
    em.cmd_record(repo, purpose, argv, expect_fail, head_bound)
    return em.load_entries(repo)[-1]


def advance(repo: Path, to: str) -> int:
    return cs.cmd_advance(repo, _args(to=to))


# 1 — cannot PATCH before RED
def test_cannot_patch_before_red(repo):
    to_prove(repo)
    cs.cmd_set_authority(repo, _args(grant="worktree_edit", evidence_ref="user-said-ok",
                                     by_user="user"))
    assert advance(repo, "RED") == 1, "no reproduction evidence yet"
    witness(repo, "reproduce the bug: actual behavior")
    assert advance(repo, "RED") == 0
    assert advance(repo, "PATCH") == 1
    s = cs.load_session(repo)
    assert s["state"] == "RED" and any("RED witness" in b for b in s["blockers"])


# 2/9 — stale head-bound GREEN after HEAD moves blocks advancement
def test_stale_green_after_head_change(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug: actual behavior")
    assert advance(repo, "RED") == 0
    # RED semantics: the command FAILS on unmodified upstream; with --expect-fail
    # that non-zero exit is recorded as PASS (the proof held)
    witness(repo, "RED: regression fails on unmodified upstream", expect_fail=True,
            status_ok=False)
    cs.cmd_set_authority(repo, _args(grant="worktree_edit", evidence_ref="ok", by_user="u"))
    assert advance(repo, "PATCH") == 0
    marker = repo / "patch-intent.md"
    marker.write_text("intent")
    assert cs.cmd_record(repo, _args(kind="patch-intent", file=[str(marker)],
                                     conclusion=None, reason=None)) == 0
    (repo / "mod.py").write_text("def target():\n    return 2\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "fix")
    witness(repo, "GREEN: regression passes after fix", head_bound=True)
    assert advance(repo, "GREEN") == 0
    assert advance(repo, "REGRESSION") == 0
    (repo / "mod.py").write_text("def target():\n    return 3\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "review fix")
    assert advance(repo, "CONTRIBUTOR_UNDERSTANDING") == 1
    s = cs.load_session(repo)
    assert any("STALE" in b for b in s["blockers"])


# 3 — cannot move to PR_READY with unresolved validation blocker
def test_pr_ready_blocked_by_validation_fail(repo):
    s = init_session(repo)
    s["state"] = "REVIEW"
    s["understanding"] = {"status": "DEFERRED", "confirmed_by": None}
    s["scope_audit"] = {"conclusion": "WITHIN_SCOPE"}
    cs.save_session(repo, s)
    witness(repo, "suite run that failed", status_ok=False)
    assert advance(repo, "PR_READY") == 1
    s = cs.load_session(repo)
    assert any("FAIL" in b for b in s["blockers"])


# 4 — duplicate candidate stops (stopping classification blocks patch-side states)
def test_duplicate_classification_stops_run(repo):
    init_session(repo)
    record_artifacts(repo)
    advance_through(repo, ["RECON", "CANDIDATE", "DEDUPLICATE"])
    assert cs.cmd_set_classification(
        repo, _args(classification="PR_EXISTS")) == 0
    assert advance(repo, "PROVE") == 0
    assert advance(repo, "RED") == 1
    s = cs.load_session(repo)
    assert s["state"] == "PROVE" and "stopping outcome" in s["blockers"][0]


# 5 — unconfirmed bug stops (no reproduction evidence → RED unreachable)
def test_unconfirmed_bug_cannot_reach_red(repo):
    to_prove(repo)
    assert advance(repo, "RED") == 1
    s = cs.load_session(repo)
    assert any("reproduction evidence" in b for b in s["blockers"])


# 6 — READ_ONLY cannot mutate (PATCH requires granted worktree_edit)
def test_read_only_cannot_patch(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug")
    assert advance(repo, "RED") == 0
    assert advance(repo, "PATCH") == 1
    s = cs.load_session(repo)
    assert any("worktree_edit" in b for b in s["blockers"])


# 7 — authority requires an explicit attribution artifact; IN_REVIEW requires remote
def test_authority_requires_artifact_and_remote_for_in_review(repo):
    init_session(repo)
    assert cs.cmd_set_authority(repo, _args(grant="worktree_edit", evidence_ref="",
                                            by_user="")) == 2, \
        "grant without evidence ref must fail"
    assert cs.cmd_set_authority(repo, _args(grant="remote_write",
                                            evidence_ref="user-msg-42",
                                            by_user="user")) == 0
    s = cs.load_session(repo)
    assert s["authority"]["remote_write"] is True
    s["state"] = "PR_READY"
    s["scope_audit"] = {"conclusion": "WITHIN_SCOPE"}
    s["understanding"] = {"status": "DEFERRED"}
    cs.save_session(repo, s)
    assert advance(repo, "IN_REVIEW") == 1
    s = cs.load_session(repo)
    assert any("upstream PR identity" in b for b in s["blockers"])


# 8 — closed PR != merged
def test_closed_pr_is_not_merged(repo):
    init_session(repo)
    pr_json = repo / "pr.json"
    pr_json.write_text(json.dumps({
        "pr": {"number": 7, "state": "closed", "merged": False,
               "user": {"login": "someone"}},
        "reviews": [], "timeline": []}))
    assert cs.cmd_upstream(repo, _args(pr_json=str(pr_json))) == 0
    s = cs.load_session(repo)
    assert s["upstream"]["outcome"] == "CLOSED_NOT_MERGED"
    assert s["upstream"]["outcome"] != "MERGED"


# extra — a plain PASS is not a RED witness (expected-fail semantics)
def test_red_requires_expected_fail_witness(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug")
    assert advance(repo, "RED") == 0
    witness(repo, "wrong: plain green run", expect_fail=False)
    cs.cmd_set_authority(repo, _args(grant="worktree_edit", evidence_ref="ok", by_user="u"))
    assert advance(repo, "PATCH") == 1, \
        "a plain PASS must never satisfy the RED gate"
    s = cs.load_session(repo)
    assert any("RED witness" in b for b in s["blockers"])


# 10 — session reconstructs after process restart (fresh load from disk)
def test_session_survives_restart(repo):
    init_session(repo)
    advance(repo, "RECON")
    s2 = cs.load_session(repo)  # raises SystemExit(3) if the file were absent
    assert s2["state"] == "RECON"
    assert s2["goal"]["digest"] == "test-digest"
    assert cs.cmd_reconstruct(repo) == 0


def _args(**kw):
    class A:
        pass
    a = A()
    for k, v in kw.items():
        setattr(a, k, v)
    return a
