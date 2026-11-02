#!/usr/bin/env python3
"""V5.2 Phase 0 — reproduction tests for the suspected evidence-chain holes.

Each test documents the SUSPECTED hole and asserts the SECURE behavior.
Holes that reproduce will fail on the pre-fix runtime; each failure is a proven
hole. A test that already passes means the suspicion was wrong for that item.

Run: python3 -m pytest tests/test_v52_holes.py -q
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

import sys

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys_path = str(SCRIPTS)
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

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


def make_repo(tmp_path: Path) -> Path:
    subprocess.run(["/usr/bin/env", "git", "init", "-q", str(tmp_path)], capture_output=True)
    git(tmp_path, "config", "user.email", "t@t.co")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "mod.py").write_text("def target():\n    return 1\n")
    (tmp_path / "test_mod.py").write_text(
        "def test_target():\n    assert target() is not None\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def envelope(a_type: str, repo_id: str, base_sha: str, extra: dict | None = None) -> dict:
    body = {"type": a_type, "schema_version": 1, "repository": repo_id,
            "repository_id": repo_id, "base_sha": base_sha,
            "generated_by": "probe", "created_at": "2026-10-06T00:00:00Z"}
    body.update(extra or {})
    body["digest"] = hashlib.sha256(
        json.dumps(body, sort_keys=True).encode()).hexdigest()
    return body


def write_artifact(repo: Path, name: str, data: dict) -> str:
    p = repo / name
    p.write_text(json.dumps(data, indent=2))
    return str(p)


def session_with_artifact(repo: Path, artifact_path: str):
    s = cs.load_session(repo)
    cs.save_session(repo, s)
    assert cs.cmd_record(repo, _args(kind="recon", file=[artifact_path],
                                     conclusion=None, reason=None)) == 0


def base_session(repo: Path, goal_digest="g1") -> dict:
    goal = repo / "goal.json"
    goal.write_text(json.dumps({"digest": goal_digest}))
    s = {
        "session_version": 2, "task_id": "t1", "repository": "r",
        "repository_id": cs.repository_identity(repo),
        "base_sha": git(repo, "rev-parse", "HEAD"),
        "state": "DISCOVER",
        "goal": {"digest": goal_digest, "path": str(repo / "goal.json")},
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
    cs.save_session(repo, s)
    return s


def advance(repo: Path, to: str) -> int:
    return cs.cmd_advance(repo, _args(to=to))


# A — wrong-repository artifact replay
def test_a_wrong_repository_recon_rejected(tmp_path):
    repo_a = make_repo(tmp_path / "a")
    (tmp_path / "b").mkdir(parents=True)
    repo_b = make_repo(tmp_path / "b")
    base_a = git(repo_a, "rev-parse", "HEAD")
    art = write_artifact(repo_b, "recon.json",
                         envelope("REPOSITORY_RECON", "repo-a", base_a))
    base_session(repo_b)
    session_with_artifact(repo_b, art)
    # SECURE: repository_id mismatch must refuse CANDIDATE
    assert advance(repo_b, "RECON") == 0
    assert advance(repo_b, "CANDIDATE") == 1


def test_a_wrong_repository_scope_audit_rejected(tmp_path):
    repo_b = make_repo(tmp_path / "b")
    base_b = git(repo_b, "rev-parse", "HEAD")
    s = base_session(repo_b)
    s["state"] = "REVIEW"
    s["understanding"] = {"status": "DEFERRED"}
    cs.save_session(repo_b, s)
    art = write_artifact(repo_b, "scope.json",
                         envelope("SCOPE_AUDIT", "repo-a", base_b,
                                  {"conclusion": "WITHIN_SCOPE"}))
    cs.cmd_record(repo_b, _args(kind="scope-audit", file=[art],
                                conclusion=None, reason=None))
    # SECURE: foreign scope artifact must not satisfy PR_READY
    assert advance(repo_b, "PR_READY") == 1


# B — wrong-base artifact replay
def test_b_wrong_base_recon_rejected(tmp_path):
    repo = make_repo(tmp_path)
    old_base = git(repo, "rev-parse", "HEAD")
    s = base_session(repo)
    s["base_sha"] = old_base
    cs.save_session(repo, s)
    # artifact generated at ANOTHER base (simulate: different sha)
    art = write_artifact(repo, "recon.json",
                         envelope("REPOSITORY_RECON", "r", "f" * 40))
    session_with_artifact(repo, art)
    assert advance(repo, "RECON") == 0
    assert advance(repo, "CANDIDATE") == 1  # base mismatch must refuse


# C — tampered Goal Contract with retained digest field
def test_c_tampered_goal_contract_rejected_at_init(tmp_path):
    repo = make_repo(tmp_path)
    # compile a REAL contract via the verified loader path
    gc = SCRIPTS / "goal_compiler.py"
    r = subprocess.run(["/usr/bin/env", "python3", str(gc), str(repo), "compile",
                        "--task-id", "t1", "--intent", "fix target",
                        "--done-when", "run: true", "--repository", "r"],
                       capture_output=True, text=True, shell=False)
    goal = sorted((repo / ".oss-contrib-evidence" / "goals").glob("*.json"))[-1]
    # tamper content, keep digest field
    data = json.loads(goal.read_text())
    data["intent"] = "backdoored intent"
    goal.write_text(json.dumps(data, indent=2))
    r = run_session_init(repo, str(goal), "tamper")
    assert r.returncode != 0, "tampered contract must be rejected at init"


def run_session_init(repo: Path, goal: str, task: str):
    return subprocess.run(
        ["/usr/bin/env", "python3", str(SCRIPTS / "contribution_session.py"),
         str(repo), "init", "--task-id", task, "--goal", goal],
        capture_output=True, text=True, shell=False)


# D — scope conclusion disagreement
def test_d_scope_conclusion_cannot_be_relabelled(tmp_path):
    repo = make_repo(tmp_path)
    base = git(repo, "rev-parse", "HEAD")
    s = base_session(repo)
    s["state"] = "REVIEW"
    s["understanding"] = {"status": "DEFERRED"}
    cs.save_session(repo, s)
    art = write_artifact(repo, "scope.json",
                         envelope("SCOPE_AUDIT", "r", base,
                                  {"conclusion": "SCOPE_FINDINGS"}))
    # SECURE: recording WITHIN_SCOPE over a SCOPE_FINDINGS artifact must refuse.
    # (the envelope uses repo identity "r" — matching this test's repository —
    # so the only refusal reason is the relabelling attempt)
    r = cs.cmd_record(repo, _args(kind="scope-audit", file=[art],
                                  conclusion="WITHIN_SCOPE", reason=None))
    assert r == 1, "agent must not relabel the machine finding"


# E — remote authorization target mismatch
def test_e_remote_target_mismatch_rejected(tmp_path):
    repo = make_repo(tmp_path)
    s = base_session(repo)
    s["state"] = "PR_READY"
    s["scope_audit"] = {"conclusion": "WITHIN_SCOPE"}
    s["understanding"] = {"status": "UNDERSTOOD", "confirmed_by": "u"}
    s["upstream"] = {"observed": True,
                     "pr_identity": {"repo": "owner/repo-B", "number": 7}}
    s["authority"]["actions"] = [{"action": "OPEN_PR", "target": "owner/repo-A#5",
                                  "authorized_by": "u", "evidence_ref": "e",
                                  "created_at": "t", "consumed_at": None}]
    cs.save_session(repo, s)
    # SECURE: OPEN_PR authorized for repo-A must not satisfy repo-B publication
    assert advance(repo, "IN_REVIEW") == 1


# F — RED without test identity
def test_f_red_without_test_identity_insufficient(tmp_path):
    repo = make_repo(tmp_path)
    to_prove(repo)
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0
    # RED_REGRESSION with regression_id but NO test-file identity
    witness(repo, "RED: fails on unmodified upstream", "RED_REGRESSION",
            expect_fail=True, status_ok=False, regression_id="R1",
            test_file=None)
    # SECURE: behavioral flow requires the RED proof to carry test identity
    # (this probe asserts the gate refuses; current runtime may allow = hole)
    cs.cmd_set_authority(repo, _args(grant="worktree_edit", evidence_ref="ok",
                                     by_user="u"))
    assert advance(repo, "PATCH") == 1


def to_prove(repo: Path):
    s = base_session(repo)
    my_id = cs.repository_identity(repo)
    recon = write_artifact(repo, "recon.json",
                           envelope("REPOSITORY_RECON", my_id, s["base_sha"]))
    dedupe = write_artifact(repo, "dedupe.json",
                            envelope("DUPLICATE_WORK_EVIDENCE", my_id, s["base_sha"]))
    assert cs.cmd_record(repo, _args(kind="recon", file=[recon], conclusion=None,
                                     reason=None)) == 0
    assert cs.cmd_record(repo, _args(kind="dedupe", file=[dedupe], conclusion=None,
                                     reason=None)) == 0
    advance_through(repo, ["RECON", "CANDIDATE", "DEDUPLICATE"])
    assert cs.cmd_set_classification(repo, _args(classification="GOOD_CANDIDATE")) == 0
    advance_through(repo, ["PROVE"])


def advance_through(repo: Path, states):
    for st in states:
        assert advance(repo, st) == 0, st


def witness(repo: Path, purpose: str, etype: str, expect_fail=False,
            head_bound=False, regression_id=None, status_ok=True, test_file=None):
    argv = ["/usr/bin/env", "python3", "-c",
            "pass" if status_ok else "raise SystemExit(1)"]
    em.cmd_record(repo, purpose, argv, expect_fail, head_bound, etype,
                  regression_id, [str(test_file)] if test_file else None)
    return em.load_entries(repo)[-1]


# G — dirty worktree before PATCH (unstaged, uncommitted production edit)
def test_g_unstaged_production_edit_blocks_patch(tmp_path):
    repo = make_repo(tmp_path)
    to_prove(repo)
    witness(repo, "reproduce the bug", "REPRODUCTION")
    assert advance(repo, "RED") == 0
    witness(repo, "RED: fails on unmodified upstream", "RED_REGRESSION",
            expect_fail=True, status_ok=False, regression_id="R1",
            test_file=repo / "test_mod.py")
    # dirty worktree: unstaged production edit, NOT committed
    (repo / "mod.py").write_text("def target():\n    return 99\n")
    cs.cmd_set_authority(repo, _args(grant="worktree_edit", evidence_ref="ok",
                                     by_user="u"))
    assert advance(repo, "PATCH") == 1  # currently: hole (only base..HEAD checked)
