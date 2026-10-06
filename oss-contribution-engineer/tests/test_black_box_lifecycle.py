#!/usr/bin/env python3
"""V5.2 black-box lifecycle tests — public CLI only (no internal imports, no
direct session.json edits). Proves the evidence chain and the executable
review-driven revision loop end to end.

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
GOAL = SCRIPTS / "goal_compiler.py"
EVIDENCE = SCRIPTS / "evidence_manifest.py"
GOVERNOR = SCRIPTS / "budget_governor.py"


def run(script: Path, *args: str) -> subprocess.CompletedProcess:
    # literal loader head + shell=False: nothing is ever parsed by a shell
    return subprocess.run(["/usr/bin/env", "python3", str(script), *args],
                          capture_output=True, text=True, shell=False)


def git(repo: Path, *args: str) -> str:
    p = subprocess.run(["/usr/bin/env", "git", "-C", str(repo), *args],
                       capture_output=True, text=True, shell=False)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def repo_id(repo: Path) -> str:
    r = run(SESSION, str(repo), "status")
    # status prints state line first; derive identity via git remote fallback
    r = subprocess.run(["/usr/bin/env", "git", "-C", str(repo), "remote",
                        "get-url", "origin"], capture_output=True, text=True,
                       shell=False)
    if r.returncode == 0:
        import re
        m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", r.stdout.strip())
        if m:
            return m.group(1)
    root = git(repo, "rev-parse", "--show-toplevel")
    return "local-" + hashlib.sha256(root.encode()).hexdigest()[:12]


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


def compiled_goal(repo: Path, task: str) -> str:
    r = run(GOAL, str(repo), "compile", "--task-id", task,
            "--intent", "fix target", "--done-when", "run: true",
            "--repository", repo_id(repo))
    assert r.returncode == 0, r.stderr
    goals = sorted((repo / ".oss-contrib-evidence" / "goals").glob("*.json"))
    return str(goals[-1])


def artifact(repo: Path, name: str, a_type: str, repo_id: str,
             base_sha: str, extra: dict | None = None) -> str:
    body = {"type": a_type, "schema_version": 1, "repository": repo_id,
            "repository_id": repo_id, "base_sha": base_sha,
            "generated_by": "test-script", "created_at": "2026-10-06T00:00:00Z"}
    body.update(extra or {})
    body["digest"] = hashlib.sha256(
        json.dumps(body, sort_keys=True).encode()).hexdigest()
    p = repo / name
    p.write_text(json.dumps(body, indent=2))
    return str(p)


def session_state(repo: Path) -> dict:
    sf = repo / ".oss-contrib-evidence" / "session.json"
    return json.loads(sf.read_text())


def evidence(repo: Path, purpose: str, etype: str, *extra: str, ok: bool = True,
             regression_id: str | None = None,
             test_file: str | None = None) -> subprocess.CompletedProcess:
    args = [str(repo), "record", "--purpose", purpose, "--evidence-type", etype]
    if regression_id:
        args += ["--regression-id", regression_id]
    if test_file:
        args += ["--test-file", test_file]
    args += list(extra)
    args += ["--", "/usr/bin/env", "python3", "-c",
             "pass" if ok else "raise SystemExit(1)"]
    return run(EVIDENCE, *args)


def full_path_to_patch(repo: Path, task: str, regression_id="R1",
                       test_file="test_mod.py"):
    """Drive the public CLI from init to GREEN legitimately."""
    base = git(repo, "rev-parse", "HEAD")
    r = run(SESSION, str(repo), "init", "--task-id", task, "--goal",
            compiled_goal(repo, task))
    assert r.returncode == 0, r.stderr
    recon = artifact(repo, "recon.json", "REPOSITORY_RECON", repo_id(repo), base)
    dedupe = artifact(repo, "dedupe.json", "DUPLICATE_WORK_EVIDENCE",
                      repo_id(repo), base)
    run(SESSION, str(repo), "record", "--kind", "recon", "--file", recon)
    run(SESSION, str(repo), "record", "--kind", "dedupe", "--file", dedupe)
    run(SESSION, str(repo), "advance", "--to", "RECON")
    run(SESSION, str(repo), "advance", "--to", "CANDIDATE")
    run(SESSION, str(repo), "advance", "--to", "DEDUPLICATE")
    run(SESSION, str(repo), "set-classification", "--classification",
        "GOOD_CANDIDATE")
    run(SESSION, str(repo), "advance", "--to", "PROVE")
    r = evidence(repo, "reproduce the bug", "REPRODUCTION")
    assert r.returncode == 0, r.stderr
    run(SESSION, str(repo), "advance", "--to", "RED")
    r = evidence(repo, "RED: fails on unmodified upstream", "RED_REGRESSION",
                 "--expect-fail", "--regression-id", regression_id,
                 "--test-file", str(repo / test_file), ok=False)
    # cmd_record exits 1 because the *witnessed command* failed; the record
    # itself succeeded (status PASS as an expected failure)
    assert "recorded" in r.stdout, r.stderr
    run(SESSION, str(repo), "set-authority", "--grant", "worktree_edit",
        "--evidence-ref", "user ok", "--by-user", "user")
    r = run(SESSION, str(repo), "advance", "--to", "PATCH")
    assert r.returncode == 0, r.stderr
    plan = repo / "plan.md"
    plan.write_text("intent")
    run(SESSION, str(repo), "record", "--kind", "patch-intent", "--file", str(plan))


def to_green(repo: Path, task="bb", regression_id="R1", test_file="test_mod.py",
             fix=("def target():\n    return 2\n")):
    full_path_to_patch(repo, task, regression_id, test_file)
    (repo / "mod.py").write_text(fix)
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "fix")
    r = evidence(repo, "GREEN: passes after fix", "GREEN_REGRESSION",
                 "--head-bound", "--regression-id", regression_id,
                 "--test-file", str(repo / test_file))
    assert r.returncode == 0, r.stderr
    run(SESSION, str(repo), "advance", "--to", "GREEN")


def test_happy_path_to_pr_ready(repo):
    to_green(repo, "bb1")
    run(SESSION, str(repo), "advance", "--to", "REGRESSION")
    run(SESSION, str(repo), "advance", "--to", "CONTRIBUTOR_UNDERSTANDING")
    r = run(SESSION, str(repo), "set-understanding", "--status", "UNDERSTOOD",
            "--confirmed-by", "user")
    assert r.returncode == 0
    run(SESSION, str(repo), "advance", "--to", "REVIEW")
    base = git(repo, "rev-parse", "HEAD")
    sa = artifact(repo, "scope.json", "SCOPE_AUDIT", repo_id(repo), base,
                  {"conclusion": "WITHIN_SCOPE"})
    r = run(SESSION, str(repo), "record", "--kind", "scope-audit", "--file", sa)
    assert r.returncode == 0, r.stderr
    assert run(SESSION, str(repo), "advance", "--to", "PR_READY").returncode == 0
    assert "PR_READY" in run(SESSION, str(repo), "status").stdout


def test_skip_red_is_refused(repo):
    full_path_to_patch.__wrapped__ if False else None
    base = git(repo, "rev-parse", "HEAD")
    r = run(SESSION, str(repo), "init", "--task-id", "neg", "--goal",
            compiled_goal(repo, "neg"))
    assert r.returncode == 0
    recon = artifact(repo, "r.json", "REPOSITORY_RECON", repo_id(repo), base)
    dedupe = artifact(repo, "d.json", "DUPLICATE_WORK_EVIDENCE", repo_id(repo), base)
    run(SESSION, str(repo), "record", "--kind", "recon", "--file", recon)
    run(SESSION, str(repo), "record", "--kind", "dedupe", "--file", dedupe)
    run(SESSION, str(repo), "advance", "--to", "RECON")
    run(SESSION, str(repo), "advance", "--to", "CANDIDATE")
    run(SESSION, str(repo), "advance", "--to", "DEDUPLICATE")
    run(SESSION, str(repo), "set-classification", "--classification",
        "GOOD_CANDIDATE")
    run(SESSION, str(repo), "advance", "--to", "PROVE")
    evidence(repo, "reproduce the bug", "REPRODUCTION")
    r = run(SESSION, str(repo), "advance", "--to", "RED")
    assert r.returncode == 0
    # no RED witness → PATCH refused
    run(SESSION, str(repo), "set-authority", "--grant", "worktree_edit",
        "--evidence-ref", "ok", "--by-user", "u")
    r = run(SESSION, str(repo), "advance", "--to", "PATCH")
    assert r.returncode == 1
    assert "RED_REGRESSION" in r.stderr


def test_wrong_repository_artifact_rejected(repo):
    base = git(repo, "rev-parse", "HEAD")
    r = run(SESSION, str(repo), "init", "--task-id", "wrong-repo", "--goal",
            compiled_goal(repo, "wrong-repo"))
    assert r.returncode == 0
    foreign = artifact(repo, "recon.json", "REPOSITORY_RECON",
                       "some-owner/other-repo", base)
    run(SESSION, str(repo), "record", "--kind", "recon", "--file", foreign)
    r = run(SESSION, str(repo), "advance", "--to", "RECON")
    assert r.returncode == 0
    r = run(SESSION, str(repo), "advance", "--to", "CANDIDATE")
    assert r.returncode == 1
    assert "wrong-repository replay" in r.stderr


def test_wrong_base_artifact_rejected(repo):
    base = git(repo, "rev-parse", "HEAD")
    r = run(SESSION, str(repo), "init", "--task-id", "wrong-base", "--goal",
            compiled_goal(repo, "wrong-base"))
    assert r.returncode == 0
    # artifact bound to a DIFFERENT base than the session
    foreign = artifact(repo, "recon.json", "REPOSITORY_RECON",
                       repo_id(repo), "f" * 40)
    run(SESSION, str(repo), "record", "--kind", "recon", "--file", foreign)
    run(SESSION, str(repo), "advance", "--to", "RECON")
    r = run(SESSION, str(repo), "advance", "--to", "CANDIDATE")
    assert r.returncode == 1
    assert "wrong-revision replay" in r.stderr


def test_tampered_goal_contract_rejected(repo):
    goal_path = compiled_goal(repo, "tamper")
    data = json.loads(Path(goal_path).read_text())
    data["intent"] = "backdoored"  # keep the old digest
    Path(goal_path).write_text(json.dumps(data, indent=2))
    r = run(SESSION, str(repo), "init", "--task-id", "tamper", "--goal",
            goal_path)
    assert r.returncode != 0
    assert "digest" in r.stderr.lower()


def test_scope_finding_cannot_be_relabelled(repo):
    to_green(repo, "relabel")
    run(SESSION, str(repo), "advance", "--to", "REGRESSION")
    run(SESSION, str(repo), "advance", "--to", "CONTRIBUTOR_UNDERSTANDING")
    run(SESSION, str(repo), "set-understanding", "--status", "UNDERSTOOD",
        "--confirmed-by", "user")
    run(SESSION, str(repo), "advance", "--to", "REVIEW")
    base = git(repo, "rev-parse", "HEAD")
    sa = artifact(repo, "scope.json", "SCOPE_AUDIT", repo_id(repo), base,
                  {"conclusion": "SCOPE_FINDINGS"})
    r = run(SESSION, str(repo), "record", "--kind", "scope-audit", "--file", sa,
            "--conclusion", "WITHIN_SCOPE")
    assert r.returncode == 1
    assert "relabelled" in r.stderr or "disagrees" in r.stderr
    # without --conclusion the derived (machine) conclusion is stored as-is
    r = run(SESSION, str(repo), "record", "--kind", "scope-audit", "--file", sa)
    assert r.returncode == 0
    s = session_state(repo)
    assert s["scope_audit"]["conclusion"] == "SCOPE_FINDINGS"
    # PR_READY stays blocked until a human acknowledges separately
    assert run(SESSION, str(repo), "advance", "--to", "PR_READY").returncode == 1
    r = run(SESSION, str(repo), "acknowledge-scope-finding", "--reason",
            "drift reviewed and accepted by maintainer", "--by-user", "user")
    assert r.returncode == 0
    s = session_state(repo)
    assert s["scope_audit"]["conclusion"] == "SCOPE_FINDINGS"
    assert s["scope_audit"]["acknowledgement"]["acknowledged"] is True


def test_review_loop_reenters_patch_and_rereview(repo):
    rid = repo_id(repo)
    to_green(repo, "loop")
    run(SESSION, str(repo), "advance", "--to", "REGRESSION")
    run(SESSION, str(repo), "advance", "--to", "CONTRIBUTOR_UNDERSTANDING")
    run(SESSION, str(repo), "set-understanding", "--status", "UNDERSTOOD",
        "--confirmed-by", "user")
    run(SESSION, str(repo), "advance", "--to", "REVIEW")
    base = git(repo, "rev-parse", "HEAD")
    sa = artifact(repo, "scope.json", "SCOPE_AUDIT", repo_id(repo), base,
                  {"conclusion": "WITHIN_SCOPE"})
    run(SESSION, str(repo), "record", "--kind", "scope-audit", "--file", sa)
    run(SESSION, str(repo), "advance", "--to", "PR_READY")
    # grant + receipt the OPEN_PR action, then observe the published PR
    run(SESSION, str(repo), "set-authority", "--grant", "remote", "--action",
        "OPEN_PR", "--target", rid + "#1", "--evidence-ref", "user ok",
        "--by-user", "user")
    grant_id = session_state(repo)["authority"]["actions"][-1]["grant_id"]
    r = run(SESSION, str(repo), "record-remote-action", "--grant-id", grant_id,
            "--resulting", rid + "#1", "--by-user", "user")
    assert r.returncode == 0, r.stderr
    pr = repo / "pr.json"
    pr.write_text(json.dumps({"pr": {"number": 1, "state": "open",
                                     "user": {"login": "me"}},
                              "reviews": [], "timeline": []}))
    r = run(SESSION, str(repo), "upstream", "--pr-json", str(pr))
    assert r.returncode == 0
    assert run(SESSION, str(repo), "advance", "--to", "IN_REVIEW").returncode == 0
    # review comes back: CHANGES_REQUESTED
    pr.write_text(json.dumps({"pr": {"number": 1, "state": "open",
                                     "user": {"login": "me"}},
                              "reviews": [{"state": "CHANGES_REQUESTED",
                                           "user": {"login": "rev"},
                                           "submitted_at": "t"}],
                              "timeline": []}))
    r = run(SESSION, str(repo), "upstream", "--pr-json", str(pr))
    assert r.returncode == 0
    assert session_state(repo)["upstream"]["substate"] == "CHANGES_REQUESTED"
    # accept the review change: runtime re-enters PATCH with revalidation debt
    r = run(SESSION, str(repo), "accept-review-change", "--reason",
            "reviewer-requested error handling fix", "--by-user", "user")
    assert r.returncode == 0, r.stderr
    assert session_state(repo)["state"] == "PATCH"
    # prior validation is invalidated: IN_REVIEW unreachable until revalidated
    (repo / "mod.py").write_text("def target():\n    return 3\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "review fix")
    evidence(repo, "reproduce the bug (again)", "REPRODUCTION")
    run(SESSION, str(repo), "advance", "--to", "RED")
    evidence(repo, "RED: fails after review change", "RED_REGRESSION",
             "--expect-fail", "--regression-id", "R2",
             "--test-file", str(repo / "test_mod.py"), ok=False)
    run(SESSION, str(repo), "advance", "--to", "PATCH")
    evidence(repo, "GREEN after review fix", "GREEN_REGRESSION", "--head-bound",
             "--regression-id", "R2", "--test-file", str(repo / "test_mod.py"))
    run(SESSION, str(repo), "advance", "--to", "GREEN")
    run(SESSION, str(repo), "advance", "--to", "REGRESSION")
    # rereview without revalidation debt cleared is refused — the runtime already
    # cleared it above; a REQUEST_REREVIEW grant + receipt is now required
    r = run(SESSION, str(repo), "request-rereview")
    assert r.returncode == 1
    assert "REQUEST_REREVIEW" in r.stderr
    run(SESSION, str(repo), "set-authority", "--grant", "remote", "--action",
        "REQUEST_REREVIEW", "--target", rid + "#1", "--evidence-ref", "user ok",
        "--by-user", "user")
    r = run(SESSION, str(repo), "request-rereview")
    assert r.returncode == 0, r.stderr
    assert session_state(repo)["upstream"]["substate"] == "READY_FOR_REREVIEW"


def test_merged_is_success_closed_is_not(repo):
    # MERGED: a captured merged PR reports success
    init_and_reach_pr_ready(repo, "merged-case")
    pr = repo / "pr_merged.json"
    pr.write_text(json.dumps({"pr": {"number": 2, "state": "closed",
                                     "merged": True,
                                     "user": {"login": "me"}},
                              "reviews": [], "timeline": []}))
    r = run(SESSION, str(repo), "upstream", "--pr-json", str(pr))
    assert r.returncode == 0
    assert "MERGED" in r.stdout

    # CLOSED_NOT_MERGED: a second, fresh session observes a closed-unmerged PR —
    # never reported as success
    r = run(SESSION, str(repo), "init", "--task-id", "closed-case", "--goal",
            compiled_goal(repo, "closed-case"), "--fresh")
    assert r.returncode == 0, r.stderr
    pr2 = repo / "pr_closed.json"
    pr2.write_text(json.dumps({"pr": {"number": 3, "state": "closed",
                                      "merged": False,
                                      "user": {"login": "me"}},
                               "reviews": [], "timeline": []}))
    r = run(SESSION, str(repo), "upstream", "--pr-json", str(pr2))
    assert r.returncode == 0
    assert "CLOSED_NOT_MERGED" in r.stdout
    assert "NOT a merged contribution" in r.stdout


def test_posthoc_grant_cannot_legitimize_observed_pr(repo):
    """V5.2: an OPEN_PR grant recorded AFTER the upstream capture must be
    refused by record-remote-action — authorization cannot be manufactured
    post-hoc to legitimize an already-observed remote action."""
    r = run(SESSION, str(repo), "init", "--task-id", "posthoc", "--goal",
            compiled_goal(repo, "posthoc"))
    assert r.returncode == 0, r.stderr
    # 1) capture the upstream PR FIRST (observation)
    pr = repo / "pr.json"
    pr.write_text(json.dumps({"pr": {"number": 11, "state": "open",
                                     "user": {"login": "someone"}},
                              "reviews": [], "timeline": []}))
    r = run(SESSION, str(repo), "upstream", "--pr-json", str(pr))
    assert r.returncode == 0
    assert session_state(repo)["upstream"]["observed"] is True
    # 2) THEN create an OPEN_PR grant (the grant itself is a human decision and
    #    is allowed; legitimization happens only at receipt time)
    r = run(SESSION, str(repo), "set-authority", "--grant", "remote",
            "--action", "OPEN_PR", "--target", "r#11", "--evidence-ref",
            "later grant", "--by-user", "user")
    assert r.returncode == 0, r.stderr
    grant_id = session_state(repo)["authority"]["actions"][-1]["grant_id"]
    # 3) receipting it must be refused
    r = run(SESSION, str(repo), "record-remote-action", "--grant-id", grant_id,
            "--resulting", "r#11", "--by-user", "user")
    assert r.returncode == 1
    assert "post-hoc" in r.stderr
    s = session_state(repo)
    assert s["authority"]["actions"][-1]["consumed_at"] is None, \
        "the refused grant must remain unconsumed"
    assert s["authority"]["receipts"] == [], "no receipt may be recorded"


def init_and_reach_pr_ready(repo: Path, task: str):
    to_green(repo, task)
    run(SESSION, str(repo), "advance", "--to", "REGRESSION")
    run(SESSION, str(repo), "advance", "--to", "CONTRIBUTOR_UNDERSTANDING")
    run(SESSION, str(repo), "set-understanding", "--status", "UNDERSTOOD",
        "--confirmed-by", "user")
    run(SESSION, str(repo), "advance", "--to", "REVIEW")
    base = git(repo, "rev-parse", "HEAD")
    sa = artifact(repo, "scope.json", "SCOPE_AUDIT", repo_id(repo), base,
                  {"conclusion": "WITHIN_SCOPE"})
    run(SESSION, str(repo), "record", "--kind", "scope-audit", "--file", sa)
    run(SESSION, str(repo), "advance", "--to", "PR_READY")


def test_budget_govern_cli(repo):
    pack = {"pack_version": 2, "type": "CONTEXT_PACK", "schema_version": 1,
            "token_accounting": {"source_used_est": 20000, "test_used_est": 0},
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
    out = repo / "governed.json"
    r = run(GOVERNOR, "govern", str(pf), "--out", str(out))
    assert r.returncode == 0, r.stderr
    governed = json.loads(out.read_text())
    assert [s["path"] for s in governed["source_ranges"]] == ["a.py"]
    assert governed["token_accounting"]["source_used_est"] == 110
    assert governed["pack_digest"] != pack["pack_digest"]


def test_invalid_recon_and_dedupe_artifacts_rejected(repo):
    base = git(repo, "rev-parse", "HEAD")
    r = run(SESSION, str(repo), "init", "--task-id", "inv", "--goal",
            compiled_goal(repo, "inv"))
    assert r.returncode == 0
    junk = repo / "junk.json"
    junk.write_text("{}")
    # recording junk is allowed; the GATE rejects it
    run(SESSION, str(repo), "record", "--kind", "recon", "--file", str(junk))
    run(SESSION, str(repo), "advance", "--to", "RECON")
    r = run(SESSION, str(repo), "advance", "--to", "CANDIDATE")
    assert r.returncode == 1
    assert "not a structured artifact" in r.stderr
    good_recon = artifact(repo, "recon.json", "REPOSITORY_RECON",
                          repo_id(repo), base)
    run(SESSION, str(repo), "record", "--kind", "recon", "--file", good_recon)
    assert run(SESSION, str(repo), "advance", "--to", "CANDIDATE").returncode == 0
    junk2 = repo / "d.json"
    junk2.write_text("{}")
    run(SESSION, str(repo), "record", "--kind", "dedupe", "--file", str(junk2))
    r = run(SESSION, str(repo), "advance", "--to", "DEDUPLICATE")
    assert r.returncode == 1
    assert "not a structured artifact" in r.stderr


def test_captured_pr_grants_no_authorization(repo):
    base = git(repo, "rev-parse", "HEAD")
    r = run(SESSION, str(repo), "init", "--task-id", "cap", "--goal",
            compiled_goal(repo, "cap"))
    assert r.returncode == 0
    pr = repo / "pr.json"
    pr.write_text(json.dumps({"pr": {"number": 9, "state": "open",
                                     "user": {"login": "a"}},
                              "reviews": [], "timeline": []}))
    r = run(SESSION, str(repo), "upstream", "--pr-json", str(pr))
    assert r.returncode == 0
    assert "grants no remote authorization" in r.stdout
    s = session_state(repo)
    assert s["upstream"]["observed"] is True
    assert s["authority"].get("remote_write") is None
    assert s["authority"]["actions"] == []
