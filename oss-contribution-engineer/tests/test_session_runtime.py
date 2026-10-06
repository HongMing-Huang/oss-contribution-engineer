#!/usr/bin/env python3
"""Integration tests for the V5.1 runtime spine (contribution_session.py).

Typed evidence, structured artifacts, action-scoped remote authorization,
RED pre-patch binding, RED↔GREEN regression identity, strict publication
understanding, restart reconstruction. Run: pytest tests/test_session_runtime.py -q
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
import evidence_manifest as em  # noqa: E402


def git(repo: Path, *args: str) -> str:
    p = subprocess.run(["/usr/bin/env", "git", "-C", str(repo), *args],
                       capture_output=True, text=True, shell=False)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def artifact(path: Path, a_type: str, extra: dict | None = None) -> str:
    """Write a well-formed structured artifact (correct envelope + digest)."""
    body = {"type": a_type, "schema_version": 1, "repository": "r",
            "base_sha": "a" * 40, "generated_by": "test", "created_at": "2026-10-06T00:00:00Z"}
    body.update(extra or {})
    body["digest"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    path.write_text(json.dumps(body, indent=2))
    return str(path)


@pytest.fixture()
def repo(tmp_path: Path):
    subprocess.run(["/usr/bin/env", "git", "init", "-q", str(tmp_path)], capture_output=True)
    git(tmp_path, "config", "user.email", "t@t.co")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "mod.py").write_text("def target():\n    return 1\n")
    (tmp_path / "test_mod.py").write_text("def test_target():\n    assert target() is not None\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def contract(repo: Path) -> Path:
    g = repo / "goal.json"
    g.write_text(json.dumps({"contract_version": 1, "task_id": "t1",
                             "intent": "fix target", "digest": "goal-digest-1"}))
    return g


def init_session(repo: Path) -> dict:
    session = {
        "session_version": 1, "task_id": "t1", "repository": "r",
        "base_sha": git(repo, "rev-parse", "HEAD"),
        "state": "DISCOVER",
        "goal": {"digest": "goal-digest-1", "path": str(contract(repo))},
        "authority": {"read": True, "worktree_edit": False, "grants": [], "actions": []},
        "context": {"plan": None, "pack": None, "receipt": None},
        "artifacts": {}, "classification": None,
        "understanding": {"status": None, "confirmed_by": None},
        "scope_audit": {}, "upstream": {"observed": False},
        "blockers": [], "history": [],
    }
    cs.save_session(repo, session)
    return session


def record_artifacts(repo: Path):
    recon = artifact(repo / "recon.json", "REPOSITORY_RECON")
    dedupe = artifact(repo / "dedupe.json", "DUPLICATE_WORK_EVIDENCE")
    assert cs.cmd_record(repo, _args(kind="recon", file=[recon], conclusion=None,
                                     reason=None)) == 0
    assert cs.cmd_record(repo, _args(kind="dedupe", file=[dedupe], conclusion=None,
                                     reason=None)) == 0


def witness(repo: Path, purpose: str, etype: str, expect_fail=False, head_bound=False,
            regression_id=None, status_ok=True, test_file=None):
    argv = ["/usr/bin/env", "python3", "-c", "pass" if status_ok else "raise SystemExit(1)"]
    em.cmd_record(repo, purpose, argv, expect_fail, head_bound, etype, regression_id,
                  [test_file] if test_file else None)
    return em.load_entries(repo)[-1]


def advance_through(repo: Path, states: list[str]):
    for st in states:
        assert advance(repo, st) == 0, st


def to_prove(repo: Path):
    init_session(repo)
    record_artifacts(repo)
    advance_through(repo, ["RECON", "CANDIDATE", "DEDUPLICATE"])
    assert cs.cmd_set_classification(repo, _args(classification="GOOD_CANDIDATE")) == 0
    advance_through(repo, ["PROVE"])


def witness_red(repo: Path, regression_id="R1", test_file="test_mod.py"):
    witness(repo, "RED: regression fails on unmodified upstream", "RED_REGRESSION",
            expect_fail=True, status_ok=False, regression_id=regression_id,
            test_file=repo / test_file)


def grant_edit(repo: Path):
    cs.cmd_set_authority(repo, _args(grant="worktree_edit", evidence_ref="user said ok",
                                     by_user="user", action=None, target=None))


def advance(repo: Path, to: str) -> int:
    return cs.cmd_advance(repo, _args(to=to))


def _args(**kw):
    class A:
        pass
    a = A()
    for k, v in kw.items():
        setattr(a, k, v)
    return a


# ---------------------------------------------------------------- typed evidence
def test_reproduction_requires_typed_evidence(repo):
    to_prove(repo)
    # a plain GENERAL record that happens to say "reproduce" must NOT satisfy the gate
    witness(repo, "reproduce the bug somehow", "GENERAL")
    assert advance(repo, "RED") == 1
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0


def test_red_requires_typed_expected_fail_witness(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0
    witness(repo, "a plain pass", "GENERAL")  # not a RED witness
    grant_edit(repo)
    assert advance(repo, "PATCH") == 1
    s = cs.load_session(repo)
    assert any("RED_REGRESSION" in b for b in s["blockers"])


# ------------------------------------------------------- RED↔GREEN regression id
def test_green_requires_matching_regression_id(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0
    witness_red(repo, regression_id="R1")
    grant_edit(repo)
    assert advance(repo, "PATCH") == 0
    assert cs.cmd_record(repo, _args(kind="patch-intent",
                                     file=[str(_write(repo, "plan.md", "intent"))],
                                     conclusion=None, reason=None)) == 0
    (repo / "mod.py").write_text("def target():\n    return 2\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "fix")
    witness(repo, "GREEN but wrong regression", "GREEN_REGRESSION", head_bound=True,
            regression_id="R-other")
    assert advance(repo, "GREEN") == 0
    # the REGRESSION gate binds GREEN to the RED proof's regression identity
    assert advance(repo, "REGRESSION") == 1
    s = cs.load_session(repo)
    assert any("regression_id matching the RED proof" in b for b in s["blockers"])
    witness(repo, "GREEN for R1", "GREEN_REGRESSION", head_bound=True,
            regression_id="R1", test_file=repo / "test_mod.py")
    assert advance(repo, "REGRESSION") == 0


# ------------------------------------------ test modified after RED invalidates proof
def test_changed_regression_test_invalidates_green(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0
    witness_red(repo, regression_id="R1", test_file="test_mod.py")
    grant_edit(repo)
    assert advance(repo, "PATCH") == 0
    assert cs.cmd_record(repo, _args(kind="patch-intent",
                                     file=[str(_write(repo, "plan.md", "i"))],
                                     conclusion=None, reason=None)) == 0
    (repo / "mod.py").write_text("def target():\n    return 2\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "fix")
    # weaken the test after RED, then try to claim GREEN
    (repo / "test_mod.py").write_text("def test_target():\n    assert True\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "weaken test")
    witness(repo, "GREEN from weakened test", "GREEN_REGRESSION", head_bound=True,
            regression_id="R1", test_file=repo / "test_mod.py")
    # GREEN state itself records the run; the REGRESSION gate binds GREEN to RED
    # and refuses because the regression test digest changed after RED
    assert advance(repo, "GREEN") == 0
    assert advance(repo, "REGRESSION") == 1
    s = cs.load_session(repo)
    assert any("changed after" in b and "RED" in b for b in s["blockers"])


# ------------------------------------------------- RED pre-patch production binding
def test_production_edit_before_red_blocks_patch(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0
    witness_red(repo, regression_id="R1")
    # production code edited and committed BEFORE the PATCH transition
    (repo / "mod.py").write_text("def target():\n    return 99\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "premature production edit")
    grant_edit(repo)
    assert advance(repo, "PATCH") == 1
    s = cs.load_session(repo)
    assert any("production file(s) already modified" in b for b in s["blockers"])


# test-only edits before RED→PATCH are allowed
def test_test_only_edits_before_patch_allowed(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0
    witness_red(repo, regression_id="R1")
    (repo / "test_mod.py").write_text("def test_target():\n    assert target() is not None\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "test-only tweak")
    grant_edit(repo)
    assert advance(repo, "PATCH") == 0


# --------------------------------------------------------------- IN_REVIEW strict
def test_in_review_requires_understood(repo):
    s = init_session(repo)
    sa = artifact(repo / "scope.json", "SCOPE_AUDIT", {"conclusion": "WITHIN_SCOPE"})
    # record FIRST (cmd_record reloads from disk), then mutate the fresh session
    assert cs.cmd_record(repo, _args(kind="scope-audit", file=[sa],
                                     conclusion="WITHIN_SCOPE", reason=None)) == 0
    s = cs.load_session(repo)
    s["state"] = "PR_READY"
    s["upstream"] = {"observed": True, "pr_identity": {"repo": "r", "number": 5}}
    s["authority"]["actions"] = [{"action": "OPEN_PR", "target": "r#5",
                                  "authorized_by": "user", "evidence_ref": "msg",
                                  "created_at": "t", "consumed_at": None}]
    s["understanding"] = {"status": "DEFERRED"}
    cs.save_session(repo, s)
    assert advance(repo, "IN_REVIEW") == 1
    s = cs.load_session(repo)
    assert any("UNDERSTOOD" in b for b in s["blockers"])
    s["understanding"] = {"status": "INCOMPLETE"}
    cs.save_session(repo, s)
    assert advance(repo, "IN_REVIEW") == 1
    s["understanding"] = {"status": "UNDERSTOOD", "confirmed_by": "user-im"}
    cs.save_session(repo, s)
    assert advance(repo, "IN_REVIEW") == 0
    s = cs.load_session(repo)
    consumed = [g for g in s["authority"]["actions"] if g.get("consumed_at")]
    assert consumed, "OPEN_PR grant must be consumed by the transition"


# --------------------------------------------------------- action-scoped grants
def test_action_scoped_grants(repo):
    init_session(repo)
    # remote actions cannot be granted as a blanket flag
    assert cs.cmd_set_authority(repo, _args(grant="remote", evidence_ref="e",
                                            by_user="u", action=None,
                                            target=None)) == 2
    assert cs.cmd_set_authority(repo, _args(grant="remote", evidence_ref="e",
                                            by_user="u", action="NOT_AN_ACTION",
                                            target="r#1")) == 2
    assert cs.cmd_set_authority(repo, _args(grant="remote", evidence_ref="e",
                                            by_user="u", action="COMMENT_ISSUE",
                                            target="r#1")) == 0
    s = cs.load_session(repo)
    assert "remote_write" not in s["authority"], "session-wide remote_write must not exist"
    assert cs.has_pending_remote_action(s, "COMMENT_ISSUE")
    assert not cs.has_pending_remote_action(s, "OPEN_PR")


def test_upstream_capture_grants_nothing(repo):
    init_session(repo)
    pr = repo / "pr.json"
    pr.write_text(json.dumps({"pr": {"number": 3, "state": "closed", "merged": False,
                                     "user": {"login": "a"}}, "reviews": [],
                              "timeline": []}))
    assert cs.cmd_upstream(repo, _args(pr_json=str(pr))) == 0
    s = cs.load_session(repo)
    assert s["upstream"]["observed"] is True
    assert s["upstream"]["outcome"] == "CLOSED_NOT_MERGED"
    assert s["authority"].get("remote_write") is None or s["authority"]["remote_write"] is False
    assert s["authority"]["actions"] == [], "upstream observation grants no actions"
    assert not cs.has_pending_remote_action(s, "OPEN_PR")


# ---------------------------------------------------- structured artifact gates
def test_empty_recon_artifact_rejected(repo):
    init_session(repo)
    junk = repo / "junk.json"
    junk.write_text("{}")
    assert cs.cmd_record(repo, _args(kind="recon", file=[str(junk)], conclusion=None,
                                     reason=None)) == 0, "recording is allowed; the GATE rejects it"
    assert advance(repo, "RECON") == 0
    assert advance(repo, "CANDIDATE") == 1
    s = cs.load_session(repo)
    assert any("not a structured artifact" in b for b in s["blockers"])


def test_tampered_artifact_rejected(repo):
    init_session(repo)
    path = Path(artifact(repo / "recon.json", "REPOSITORY_RECON"))
    data = json.loads(path.read_text())
    data["findings"] = {"fabricated": "later edit"}
    path.write_text(json.dumps(data))  # digest no longer matches
    assert cs.cmd_record(repo, _args(kind="recon", file=[str(path)], conclusion=None,
                                     reason=None)) == 0
    assert advance(repo, "RECON") == 0
    assert advance(repo, "CANDIDATE") == 1
    s = cs.load_session(repo)
    assert any("digest mismatch" in b for b in s["blockers"])


def test_wrong_type_artifact_rejected(repo):
    init_session(repo)
    wrong = Path(artifact(repo / "wrong.json", "CONTEXT_PACK"))
    assert cs.cmd_record(repo, _args(kind="recon", file=[str(wrong)], conclusion=None,
                                     reason=None)) == 0
    assert advance(repo, "RECON") == 0
    assert advance(repo, "CANDIDATE") == 1
    s = cs.load_session(repo)
    assert any("expected REPOSITORY_RECON" in b for b in s["blockers"])


def test_scope_audit_requires_structured_artifact(repo):
    s = init_session(repo)
    s["state"] = "REVIEW"
    s["understanding"] = {"status": "DEFERRED"}
    cs.save_session(repo, s)
    # conclusion without a structured artifact must not satisfy PR_READY
    assert cs.cmd_record(repo, _args(kind="scope-audit", file=None,
                                     conclusion="WITHIN_SCOPE", reason=None)) == 0
    assert advance(repo, "PR_READY") == 1
    s = cs.load_session(repo)
    assert any("no structured artifact" in b for b in s["blockers"])


# 10 — restart reconstruction
def test_session_survives_restart(repo):
    init_session(repo)
    assert advance(repo, "RECON") == 0


# stale head-bound GREEN (HEAD moved, no rerun) blocks CONTRIBUTOR_UNDERSTANDING
def test_stale_head_bound_green_blocks_validation(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0
    witness_red(repo, regression_id="R1")
    grant_edit(repo)
    assert advance(repo, "PATCH") == 0
    marker = repo / "plan.md"
    marker.write_text("i")
    assert cs.cmd_record(repo, _args(kind="patch-intent", file=[str(marker)],
                                     conclusion=None, reason=None)) == 0
    witness(repo, "GREEN for R1", "GREEN_REGRESSION", head_bound=True,
            regression_id="R1", test_file=repo / "test_mod.py")
    assert advance(repo, "GREEN") == 0
    # move HEAD without re-running the suite: head-bound green is now stale
    (repo / "notes.md").write_text("unrelated change moves HEAD")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "move head")
    assert advance(repo, "REGRESSION") == 1
    s = cs.load_session(repo)
    assert any("STALE" in b for b in s["blockers"])
    # re-run at the new HEAD: a fresh head-bound record supersedes the stale one
    witness(repo, "GREEN for R1 (rerun at new HEAD)", "GREEN_REGRESSION",
            head_bound=True, regression_id="R1", test_file=repo / "test_mod.py")
    assert advance(repo, "REGRESSION") == 0


def _write(repo: Path, name: str, content: str) -> Path:
    p = repo / name
    p.write_text(content)
    return p
