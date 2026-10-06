#!/usr/bin/env python3
"""V5.2 runtime integration tests (contribution_session.py).

Covers typed evidence, structured artifact binding (repository/base/task),
verified Goal Contracts at init, worktree-aware pre-patch, RED↔GREEN identity,
action-scoped remote authorization with receipts, upstream substate lifecycle,
and validation attempt semantics.

Run: python3 -m pytest tests/test_session_runtime.py -q
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


def _args(**kw):
    class A:
        pass
    a = A()
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def goal_digest_of(body: dict) -> str:
    body = {k: v for k, v in body.items() if k != "digest"}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


@pytest.fixture()
def repo(tmp_path: Path):
    subprocess.run(["/usr/bin/env", "git", "init", "-q", str(tmp_path)],
                   capture_output=True)
    git(tmp_path, "config", "user.email", "t@t.co")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "mod.py").write_text("def target():\n    return 1\n")
    (tmp_path / "test_mod.py").write_text(
        "def test_target():\n    assert target() is not None\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def contract(repo: Path, digest: str | None = None, intent="fix target") -> Path:
    body = {"contract_version": 1, "task_id": "t1", "intent": intent,
            "repository": cs.repository_identity(repo),
            "done_when": [{"criterion": "run: true", "observable": True,
                           "how_observed": "run"}]}
    body["digest"] = digest or goal_digest_of(body)
    g = repo / "goal.json"
    g.write_text(json.dumps(body, indent=2))
    return g


def init_session(repo: Path, base=None, digest=None) -> dict:
    session = {
        "session_version": 2, "task_id": "t1", "repository": "r",
        "repository_id": cs.repository_identity(repo),
        "base_sha": base or git(repo, "rev-parse", "HEAD"),
        "state": "DISCOVER",
        "goal": {"digest": digest or "goal-digest-1",
                 "path": str(contract(repo))},
        "authority": {"read": True, "worktree_edit": False,
                      "grants": [], "actions": [], "receipts": []},
        "context": {"plan": None, "pack": None, "receipt": None},
        "artifacts": {}, "classification": None,
        "classification_evidence": None,
        "understanding": {"status": None, "confirmed_by": None},
        "scope_audit": {}, "upstream": {"observed": False, "substate": "NONE"},
        "review_revalidation_required": False,
        "blockers": [], "history": [],
    }
    cs.save_session(repo, session)
    return session


def envelope(repo: Path, a_type: str, base: str, extra: dict | None = None) -> dict:
    repo_id = cs.repository_identity(repo)
    body = {"type": a_type, "schema_version": 1, "repository": repo_id,
            "repository_id": repo_id, "base_sha": base,
            "generated_by": "test", "created_at": "2026-10-06T00:00:00Z"}
    body.update(extra or {})
    body["digest"] = hashlib.sha256(
        json.dumps(body, sort_keys=True).encode()).hexdigest()
    return body


def record_artifacts(repo: Path, base: str):
    recon = repo / "recon.json"
    recon.write_text(json.dumps(envelope(repo, "REPOSITORY_RECON", base)))
    dedupe = repo / "dedupe.json"
    dedupe.write_text(json.dumps(envelope(repo, "DUPLICATE_WORK_EVIDENCE", base)))
    assert cs.cmd_record(repo, _args(kind="recon", file=[str(recon)],
                                     conclusion=None, reason=None)) == 0
    assert cs.cmd_record(repo, _args(kind="dedupe", file=[str(dedupe)],
                                     conclusion=None, reason=None)) == 0


def to_prove(repo: Path):
    init_session(repo)
    record_artifacts(repo, cs.load_session(repo)["base_sha"])
    advance_through(repo, ["RECON", "CANDIDATE", "DEDUPLICATE"])
    assert cs.cmd_set_classification(
        repo, _args(classification="GOOD_CANDIDATE")) == 0
    advance_through(repo, ["PROVE"])


def witness(repo: Path, purpose: str, etype: str, expect_fail=False,
            head_bound=False, regression_id=None, status_ok=True, test_file=None):
    argv = ["/usr/bin/env", "python3", "-c",
            "pass" if status_ok else "raise SystemExit(1)"]
    em.cmd_record(repo, purpose, argv, expect_fail, head_bound, etype,
                  regression_id, [str(test_file)] if test_file else None)
    return em.load_entries(repo)[-1]


def witness_red(repo: Path, regression_id="R1", test_file="test_mod.py"):
    witness(repo, "RED: fails on unmodified upstream", "RED_REGRESSION",
            expect_fail=True, status_ok=False, regression_id=regression_id,
            test_file=repo / test_file)


def grant_edit(repo: Path):
    cs.cmd_set_authority(repo, _args(grant="worktree_edit", evidence_ref="user ok",
                                     by_user="user", action=None, target=None))


def advance(repo: Path, to: str) -> int:
    return cs.cmd_advance(repo, _args(to=to))


def advance_through(repo: Path, states):
    for st in states:
        assert advance(repo, st) == 0, st


# ---------------------------------------------------------- typed evidence (4)
def test_reproduction_requires_typed_evidence(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug somehow", "GENERAL")
    assert advance(repo, "RED") == 1
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0


def test_red_requires_typed_expected_fail_witness(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0
    witness(repo, "a plain pass", "GENERAL")
    grant_edit(repo)
    assert advance(repo, "PATCH") == 1
    s = cs.load_session(repo)
    assert any("RED_REGRESSION" in b for b in s["blockers"])


# ------------------------------------------------- RED↔GREEN identity (5/6)
def test_green_requires_matching_regression_id(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0
    witness_red(repo, regression_id="R1")
    grant_edit(repo)
    assert advance(repo, "PATCH") == 0
    plan = repo / "plan.md"
    plan.write_text("intent")
    assert cs.cmd_record(repo, _args(kind="patch-intent", file=[str(plan)],
                                     conclusion=None, reason=None)) == 0
    (repo / "mod.py").write_text("def target():\n    return 2\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "fix")
    witness(repo, "GREEN wrong id", "GREEN_REGRESSION", head_bound=True,
            regression_id="R-other", test_file=repo / "test_mod.py")
    assert advance(repo, "GREEN") == 0
    assert advance(repo, "REGRESSION") == 1
    s = cs.load_session(repo)
    assert any("regression_id matching the RED proof" in b for b in s["blockers"])
    witness(repo, "GREEN for R1", "GREEN_REGRESSION", head_bound=True,
            regression_id="R1", test_file=repo / "test_mod.py")
    assert advance(repo, "REGRESSION") == 0


def test_changed_regression_test_invalidates_green(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0
    witness_red(repo, regression_id="R1")
    grant_edit(repo)
    assert advance(repo, "PATCH") == 0
    plan = repo / "plan.md"
    plan.write_text("i")
    assert cs.cmd_record(repo, _args(kind="patch-intent", file=[str(plan)],
                                     conclusion=None, reason=None)) == 0
    (repo / "mod.py").write_text("def target():\n    return 2\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "fix")
    (repo / "test_mod.py").write_text("def test_target():\n    assert True\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "weaken")
    witness(repo, "GREEN from weakened test", "GREEN_REGRESSION", head_bound=True,
            regression_id="R1", test_file=repo / "test_mod.py")
    assert advance(repo, "GREEN") == 0
    assert advance(repo, "REGRESSION") == 1
    s = cs.load_session(repo)
    assert any("changed after" in b for b in s["blockers"])


# ------------------------------------------------- RED needs test identity (F)
def test_red_without_test_identity_rejected(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0
    # RED_REGRESSION with regression_id but NO test-file identity
    witness(repo, "RED: fails on unmodified upstream", "RED_REGRESSION",
            expect_fail=True, status_ok=False, regression_id="R1",
            test_file=None)
    grant_edit(repo)
    assert advance(repo, "PATCH") == 1
    s = cs.load_session(repo)
    assert any("--test-file" in b for b in s["blockers"])


# ------------------------------------------------ pre-patch integrity (5/7)
def test_production_edit_before_red_blocks_patch(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0
    witness_red(repo, regression_id="R1")
    (repo / "mod.py").write_text("def target():\n    return 99\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "premature edit")
    grant_edit(repo)
    assert advance(repo, "PATCH") == 1
    s = cs.load_session(repo)
    assert any("production file(s) already modified" in b for b in s["blockers"])


def test_unstaged_production_edit_blocks_patch(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0
    witness_red(repo, regression_id="R1")
    (repo / "mod.py").write_text("def target():\n    return 99\n")  # unstaged
    grant_edit(repo)
    assert advance(repo, "PATCH") == 1
    s = cs.load_session(repo)
    assert any("production file(s) already modified" in b for b in s["blockers"])


def test_staged_production_edit_blocks_patch(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0
    witness_red(repo, regression_id="R1")
    (repo / "mod.py").write_text("def target():\n    return 99\n")
    git(repo, "add", "mod.py")  # staged but uncommitted
    grant_edit(repo)
    assert advance(repo, "PATCH") == 1
    s = cs.load_session(repo)
    assert any("production file(s) already modified" in b for b in s["blockers"])


def test_untracked_production_file_blocks_patch(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0
    witness_red(repo, regression_id="R1")
    (repo / "new_production.py").write_text("x = 1\n")  # untracked production
    grant_edit(repo)
    assert advance(repo, "PATCH") == 1
    s = cs.load_session(repo)
    assert any("production file(s) already modified" in b for b in s["blockers"])


def test_test_only_edits_before_patch_allowed(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0
    witness_red(repo, regression_id="R1")
    (repo / "test_mod.py").write_text(
        "def test_target():\n    assert target() is not None\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "test-only tweak")
    grant_edit(repo)
    assert advance(repo, "PATCH") == 0


# ------------------------------------------------- stale / attempts (10)
def test_stale_head_bound_green_blocks_then_recovers(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0
    witness_red(repo, regression_id="R1")
    grant_edit(repo)
    assert advance(repo, "PATCH") == 0
    plan = repo / "plan.md"
    plan.write_text("i")
    assert cs.cmd_record(repo, _args(kind="patch-intent", file=[str(plan)],
                                     conclusion=None, reason=None)) == 0
    witness(repo, "GREEN for R1", "GREEN_REGRESSION", head_bound=True,
            regression_id="R1", test_file=repo / "test_mod.py")
    assert advance(repo, "GREEN") == 0
    (repo / "notes.md").write_text("move head")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "move head")
    assert advance(repo, "REGRESSION") == 1
    s = cs.load_session(repo)
    assert any("STALE" in b for b in s["blockers"])
    # FAIL→fix→rerun: a historical FAIL must not permanently block once the
    # same requirement has a later passing rerun
    witness(repo, "suite that failed earlier", "PACKAGE_TEST", status_ok=False)
    witness(repo, "suite rerun after fix", "PACKAGE_TEST")
    witness(repo, "GREEN rerun at new HEAD", "GREEN_REGRESSION", head_bound=True,
            regression_id="R1", test_file=repo / "test_mod.py")
    assert advance(repo, "REGRESSION") == 0
    assert advance(repo, "CONTRIBUTOR_UNDERSTANDING") == 0


def test_active_fail_still_blocks_without_rerun(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0
    witness_red(repo, regression_id="R1")
    grant_edit(repo)
    assert advance(repo, "PATCH") == 0
    plan = repo / "plan.md"
    plan.write_text("i")
    assert cs.cmd_record(repo, _args(kind="patch-intent", file=[str(plan)],
                                     conclusion=None, reason=None)) == 0
    witness(repo, "GREEN for R1", "GREEN_REGRESSION", head_bound=True,
            regression_id="R1", test_file=repo / "test_mod.py")
    assert advance(repo, "GREEN") == 0
    witness(repo, "suite failed and never rerun", "PACKAGE_TEST", status_ok=False)
    assert advance(repo, "REGRESSION") == 0
    assert advance(repo, "CONTRIBUTOR_UNDERSTANDING") == 1
    s = cs.load_session(repo)
    assert any("no later passing rerun" in b for b in s["blockers"])


# ------------------------------------------------- scope audit semantics (D/3)
def test_scope_audit_conclusion_derived_from_artifact(repo):
    to_prove(repo)
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0
    witness_red(repo, regression_id="R1")
    grant_edit(repo)
    assert advance(repo, "PATCH") == 0
    plan = repo / "plan.md"
    plan.write_text("i")
    assert cs.cmd_record(repo, _args(kind="patch-intent", file=[str(plan)],
                                     conclusion=None, reason=None)) == 0
    (repo / "mod.py").write_text("def target():\n    return 2\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "fix")
    witness(repo, "GREEN for R1", "GREEN_REGRESSION", head_bound=True,
            regression_id="R1", test_file=repo / "test_mod.py")
    assert advance(repo, "GREEN") == 0
    assert advance(repo, "REGRESSION") == 0
    # relabelling attempt: WITHIN_SCOPE conclusion over a SCOPE_FINDINGS artifact
    body = envelope(repo, "SCOPE_AUDIT", git(repo, "rev-parse", "HEAD"),
                    {"conclusion": "SCOPE_FINDINGS"})
    sa = repo / "scope.json"
    sa.write_text(json.dumps(body))
    r = cs.cmd_record(repo, _args(kind="scope-audit", file=[str(sa)],
                                  conclusion="WITHIN_SCOPE", reason=None))
    assert r == 1, "agent must not relabel the machine finding"


# ------------------------------------------------- IN_REVIEW receipt (E/5)
def test_in_review_requires_open_pr_receipt(repo):
    s = init_session(repo)
    sa = repo / "scope.json"
    sa.write_text(json.dumps(envelope(repo, "SCOPE_AUDIT",
                                      s["base_sha"],
                                      {"conclusion": "WITHIN_SCOPE"})))
    assert cs.cmd_record(repo, _args(kind="scope-audit", file=[str(sa)],
                                     conclusion=None, reason=None)) == 0
    s = cs.load_session(repo)
    s["state"] = "PR_READY"
    s["upstream"] = {"observed": True,
                     "pr_identity": {"repo": cs.repository_identity(repo),
                                     "number": 5}}
    s["understanding"] = {"status": "UNDERSTOOD", "confirmed_by": "user"}
    cs.save_session(repo, s)
    assert advance(repo, "IN_REVIEW") == 1
    s = cs.load_session(repo)
    assert any("OPEN_PR action receipt" in b for b in s["blockers"])


def test_in_review_receipt_target_mismatch_rejected(repo):
    s = init_session(repo)
    sa = repo / "scope.json"
    sa.write_text(json.dumps(envelope(repo, "SCOPE_AUDIT", s["base_sha"],
                                      {"conclusion": "WITHIN_SCOPE"})))
    assert cs.cmd_record(repo, _args(kind="scope-audit", file=[str(sa)],
                                     conclusion=None, reason=None)) == 0
    s = cs.load_session(repo)
    s["state"] = "PR_READY"
    s["upstream"] = {"observed": True,
                     "pr_identity": {"repo": "other/repo-b", "number": 7}}
    s["understanding"] = {"status": "UNDERSTOOD", "confirmed_by": "user"}
    # authorize OPEN_PR for repo-A, upstream is repo-B → mismatch
    s["authority"]["receipts"] = [{
        "grant_id": "g1", "action": "OPEN_PR", "target": "owner/repo-a#3",
        "performed_at": "t", "resulting_identity": "owner/repo-a#3",
        "recorded_by": "user"}]
    cs.save_session(repo, s)
    assert advance(repo, "IN_REVIEW") == 1
    s = cs.load_session(repo)
    assert any("does not match" in b for b in s["blockers"])


def test_in_review_accepts_matching_receipt(repo):
    s = init_session(repo)
    sa = repo / "scope.json"
    sa.write_text(json.dumps(envelope(repo, "SCOPE_AUDIT", s["base_sha"],
                                      {"conclusion": "WITHIN_SCOPE"})))
    assert cs.cmd_record(repo, _args(kind="scope-audit", file=[str(sa)],
                                     conclusion=None, reason=None)) == 0
    s = cs.load_session(repo)
    s["state"] = "PR_READY"
    my_repo = cs.repository_identity(repo)
    s["upstream"] = {"observed": True,
                     "pr_identity": {"repo": my_repo, "number": 5}}
    s["understanding"] = {"status": "UNDERSTOOD", "confirmed_by": "user"}
    s["authority"]["receipts"] = [{
        "grant_id": "g1", "action": "OPEN_PR", "target": my_repo + "#5",
        "performed_at": "t", "resulting_identity": my_repo + "#5",
        "recorded_by": "user"}]
    cs.save_session(repo, s)
    assert advance(repo, "IN_REVIEW") == 0


# ------------------------------------------------- upstream observation (E/5)
def test_upstream_capture_grants_nothing(repo):
    init_session(repo)
    pr = repo / "pr.json"
    pr.write_text(json.dumps({"pr": {"number": 3, "state": "closed", "merged": False,
                                     "user": {"login": "a"}}, "reviews": [],
                              "timeline": []}))
    assert cs.cmd_upstream(repo, _args(pr_json=str(pr))) == 0
    s = cs.load_session(repo)
    assert s["upstream"]["observed"] is True
    assert s["upstream"]["substate"] == "CLOSED_NOT_MERGED"
    assert s["authority"].get("remote_write") is None
    assert s["authority"]["actions"] == []


def test_action_scoped_grants(repo):
    init_session(repo)
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
    assert "remote_write" not in s["authority"]
    assert cs.has_pending_remote_action(s, "COMMENT_ISSUE")
    assert not cs.has_pending_remote_action(s, "OPEN_PR")


# ------------------------------------------------- artifact binding (A/B/2)
def test_wrong_repository_artifact_rejected(repo):
    other = cs.repository_identity(repo) + "-other"
    init_session(repo)
    foreign = repo / "recon.json"
    foreign.write_text(json.dumps(
        envelope(repo, "REPOSITORY_RECON", git(repo, "rev-parse", "HEAD"),
                 {"repository_id": other})))
    assert cs.cmd_record(repo, _args(kind="recon", file=[str(foreign)],
                                     conclusion=None, reason=None)) == 0
    assert advance(repo, "RECON") == 0
    assert advance(repo, "CANDIDATE") == 1
    s = cs.load_session(repo)
    assert any("wrong-repository replay" in b for b in s["blockers"])


def test_wrong_base_artifact_rejected(repo):
    init_session(repo, base="f" * 40)
    foreign_base = repo / "recon.json"
    foreign_base.write_text(json.dumps(
        envelope(repo, "REPOSITORY_RECON", git(repo, "rev-parse", "HEAD"))))
    assert cs.cmd_record(repo, _args(kind="recon", file=[str(foreign_base)],
                                     conclusion=None, reason=None)) == 0
    assert advance(repo, "RECON") == 0
    assert advance(repo, "CANDIDATE") == 1
    s = cs.load_session(repo)
    assert any("wrong-revision replay" in b for b in s["blockers"])


# ------------------------------------------------- goal contract verify (C/4)
def test_verified_goal_contract_required_at_init(tmp_path):
    repo = make_repo(tmp_path)
    gc = SCRIPTS / "goal_compiler.py"
    r = subprocess.run(["/usr/bin/env", "python3", str(gc), str(repo), "compile",
                        "--task-id", "t1", "--intent", "fix target",
                        "--done-when", "run: true", "--repository", "r"],
                       capture_output=True, text=True, shell=False)
    assert r.returncode == 0, r.stderr
    goal = sorted((repo / ".oss-contrib-evidence" / "goals").glob("*.json"))[-1]
    data = json.loads(goal.read_text())
    data["intent"] = "backdoored intent"  # tamper, keep digest
    goal.write_text(json.dumps(data, indent=2))
    r = subprocess.run(
        ["/usr/bin/env", "python3", str(SCRIPTS / "contribution_session.py"),
         str(repo), "init", "--task-id", "t1", "--goal", str(goal)],
        capture_output=True, text=True, shell=False)
    assert r.returncode != 0, "tampered contract must be rejected at init"


def make_repo(tmp_path: Path) -> Path:
    subprocess.run(["/usr/bin/env", "git", "init", "-q", str(tmp_path)],
                   capture_output=True)
    git(tmp_path, "config", "user.email", "t@t.co")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "mod.py").write_text("x = 1\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "init")
    return tmp_path


# ------------------------------------------------- dedupe provenance (8)
def test_good_candidate_requires_dedupe_bundle(repo):
    to_prove(repo)
    s = cs.load_session(repo)
    s["artifacts"]["dedupe"] = []  # remove provenance
    cs.save_session(repo, s)
    assert cs.cmd_set_classification(
        repo, _args(classification="GOOD_CANDIDATE")) == 1, \
        "GOOD_CANDIDATE without a dedupe evidence bundle must be refused"
    s = cs.load_session(repo)
    # the earlier (provenanced) classification persists; the refused call must
    # NOT record a new provenance-less classification
    last = [h for h in s["history"] if h.get("event") == "classification"][-1]
    assert last["evidence_bundle"], "refused re-classification must not record"


def test_classification_records_evidence_provenance(repo):
    to_prove(repo)
    s = cs.load_session(repo)
    assert s["classification_evidence"] is not None
    assert s["classification_evidence"]["bundle"]


# 10 — restart reconstruction
def test_session_survives_restart(repo):
    init_session(repo)
    assert advance(repo, "RECON") == 0
    s2 = cs.load_session(repo)
    assert s2["state"] == "RECON"
    assert cs.cmd_reconstruct(repo, None) == 0
