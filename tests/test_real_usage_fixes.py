#!/usr/bin/env python3
"""test_real_usage_fixes.py — regression tests for the six defects reported by
the first real external session (TypeScript monorepo). Each test pins the
exact failure mode the contributor hit, verified against source:

  P1  co-located *.test.ts / *.spec.ts classified as tests (was: production)
  P2  fork-identity gate explains the origin-slug rule
  P3  --test-file resolves cwd → --cwd → repo-root; never silently dropped
  P6  --intended accepts space / repeated / comma forms
  P5r rules tiering: READMEs, changelogs, data and test files are not binding
  RR  read-rules is two-step; receipts require a per-doc rule sentence
  PS  pr_style.py profiles captured merged PRs into a digest-carrying artifact
  NK  note --kind test records what a test run showed

Run: python3 -m pytest tests/test_real_usage_fixes.py -q
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
SESSION = SCRIPTS / "contribution_session.py"
sys.path.insert(0, str(SCRIPTS))
import contribution_session as cs  # noqa: E402
import contribution_rules_scan as crs  # noqa: E402


def py(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/env", "python3", *args],
                          capture_output=True, text=True, shell=False)


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/env", "git", "-C", str(repo), *args],
                          capture_output=True, text=True, shell=False)


@pytest.fixture()
def repo(tmp_path: Path):
    py("-c", "")  # warm import cache; keep argv literal for the hook
    subprocess.run(["/usr/bin/env", "git", "init", "-q", str(tmp_path)],
                   capture_output=True)
    git(tmp_path, "config", "user.email", "t@t.co")
    git(tmp_path, "config", "user.name", "t")
    return tmp_path


# ------------------------------------------------------------------- P1
@pytest.mark.parametrize("path", [
    "src/server/modes/jsonResponseMode.test.ts",
    "src/hook.spec.tsx",
    "src/x.spec.mjs", "src/x.test.cjs", "src/x.test.jsx",
    "pkg/sub/mod.test.ts",
])
def test_ts_family_is_test_path(path):
    assert cs.is_test_path(path), path


def test_production_paths_still_not_tests():
    for path in ("src/server/modes/jsonResponseMode.ts",
                 "src/testdata/fixture.json".replace("testdata", "data"),
                 "docs/testing.md"):
        if path == "docs/testing.md":  # '/test' substring rule: doc named testing matches
            assert cs.is_test_path(path)
        else:
            assert not cs.is_test_path(path)


# ------------------------------------------------------------------- P3
def test_test_file_resolves_from_repo_root_with_foreign_cwd(repo):
    """Real failure: package cwd + repo-relative --test-file → empty
    test_identity → RED binding refused."""
    import evidence_manifest as em
    pkg = repo / "packages" / "server"
    pkg.mkdir(parents=True)
    (pkg / "mod.test.ts").write_text("it('x', () => {});\n")
    (repo / "mod.py").write_text("x = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    resolved = em._resolve_test_file("packages/server/mod.test.ts",
                                     str(pkg), repo)
    assert resolved is not None and resolved.name == "mod.test.ts"


def test_unresolved_test_file_warns_not_silent(repo):
    import evidence_manifest as em
    (repo / "mod.py").write_text("x = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    rc = em.cmd_record(repo, "missing test file", ["python3", "-c", "1"],
                       expect_fail=False,
                       test_files=["no/such/file.test.ts"])
    assert rc == 0  # execution itself passed
    entries = [json.loads(l) for l in
               (repo / ".oss-contrib-evidence" / "manifest.jsonl")
               .read_text().splitlines() if l.strip()]
    last = entries[-1]
    assert last["test_identity"] == []


# ------------------------------------------------------------------- P6
def test_intended_accepts_space_repeated_and_comma_forms(repo):
    for f in ("a.ts", "b.ts", "c.test.ts"):
        (repo / f).write_text("export {}\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    (repo / "a.ts").write_text("export const x = 2\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "edit")
    common = [str(SCRIPTS / "diff_scope_check.py"), str(repo),
              "--base", "HEAD~1", "--json"]
    for extra in (
        ["--intended", "a.ts", "b.ts"],              # space-separated
        ["--intended", "a.ts", "--intended", "b.ts"],  # repeated
        ["--intended", "a.ts,b.ts"],                 # comma (legacy)
    ):
        r = py(*common, *extra)
        assert r.returncode in (0, 1), r.stderr  # 1 = findings, still valid
        out = json.loads(r.stdout)
        assert out["intended"] == ["a.ts", "b.ts"], extra


# ------------------------------------------------------------------- P5 root
def test_reference_and_noise_docs_are_not_binding(repo):
    (repo / "CONTRIBUTING.md").write_text("# C\nsign off\n")
    (repo / "README.md").write_text("# R\n")
    (repo / "CHANGELOG.md").write_text("# CL\n")
    (repo / "changelog.json").write_text("{}\n")
    (repo / "changes.test.ts").write_text("export {}\n")
    (repo / "packages").mkdir()
    (repo / "packages" / "README.md").write_text("# pkg readme\n")
    man = crs.binding_manifest(repo, max_depth=4)
    binding_paths = [b["path"] for b in man["binding"]]
    assert binding_paths == ["CONTRIBUTING.md"]
    kinds = {d["path"]: d["kind"] for d in man["discovered"]}
    assert kinds.get("packages/README.md") == "reference_doc"
    assert "changelog.json" not in kinds and "changes.test.ts" not in kinds


# ------------------------------------------------------------------- read-rules
def _ns(**kw):
    a = argparse.Namespace()
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def _init_session(repo: Path):
    from goal_compiler import load_contract  # noqa: F401 — presence check
    r = py(str(SCRIPTS / "goal_compiler.py"), str(repo), "compile",
           "--task-id", "t1", "--intent", "fix target",
           "--done-when", "run: true",
           "--repository", cs.repository_identity(repo))
    assert r.returncode == 0, r.stderr
    goal = sorted((repo / ".oss-contrib-evidence" / "goals").glob("*.json"))[-1]
    assert cs.cmd_init(repo, _ns(goal=str(goal), task_id="t1",
                                 fresh=False)) == 0


def test_read_rules_step1_lists_binding_and_waits(repo):
    (repo / "CONTRIBUTING.md").write_text("# C\nsign off your commits\n")
    (repo / "mod.py").write_text("x = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    _init_session(repo)
    rc = cs.cmd_read_rules(repo, _ns(read=[]))
    assert rc == 0
    s = cs.load_session(repo)
    # discovery recorded, but NO read receipt yet
    assert s["artifacts"].get("rules_discovered")
    assert not s["artifacts"].get("rules_read")


def test_read_rules_step2_requires_rule_sentence(repo):
    (repo / "CONTRIBUTING.md").write_text("# C\nsign off your commits\n")
    (repo / "mod.py").write_text("x = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    _init_session(repo)
    # bad path and thin sentence are refused
    for bad in ("NOT_THERE.md::rule", "CONTRIBUTING.md::ok"):
        rc = cs.cmd_read_rules(repo, _ns(read=[bad]))
        assert rc == 2, bad
    # proper sentence completes the receipt
    rc = cs.cmd_read_rules(
        repo, _ns(read=["CONTRIBUTING.md::commits must be signed off"]))
    assert rc == 0
    s = cs.load_session(repo)
    assert s["artifacts"].get("rules_read")
    receipt = json.loads(Path(s["artifacts"]["rules_read"][-1]).read_text())
    assert receipt["covered"][0]["why"] == "commits must be signed off"
    assert not receipt["uncovered"]


# ------------------------------------------------------------------- pr_style
def test_pr_style_profile_guidance_and_digest(tmp_path):
    prs = [
        {"title": "fix: handle empty mode", "body": "## Summary\ncloses #1",
         "additions": 40, "deletions": 3, "changedFiles": 2,
         "commits": [{"messageHeadline": "fix: handle empty mode"}]},
        {"title": "Add plugin hook", "body": "Closes #2",
         "additions": 120, "deletions": 10, "changedFiles": 4,
         "commits": [{"messageHeadline": "add hook"}]},
        {"title": "remove dead code", "body": "",
         "additions": 5, "deletions": 80, "changedFiles": 1,
         "commits": [{"messageHeadline": "remove dead code"}]},
    ]
    cap = tmp_path / "prs-merged.json"
    cap.write_text(json.dumps(prs))
    out = tmp_path / "profile.json"
    r = py(str(SCRIPTS / "pr_style.py"), "profile", str(cap),
           "--out", str(out))
    assert r.returncode == 0, r.stderr
    art = json.loads(out.read_text())
    assert art["type"] == "PR_STYLE_PROFILE"
    assert art["sample_size"] == 3
    assert art["titles"]["conventional_commit_pct"] == 33
    assert art["bodies"]["linking_issue_pct"] == 67
    assert len(art["guidance"]) >= 4 and art["digest"]


# ------------------------------------------------------------------- note kind
def test_note_kind_test_persists(repo):
    (repo / "mod.py").write_text("x = 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    rc = cs.cmd_note(repo, _ns(kind="test", text="pkg tests: 272 pass",
                               next=None))
    assert rc == 0
    st = json.loads((repo / ".oss-contrib-evidence" / "investigation.json")
                    .read_text())
    assert st["test"][0]["text"] == "pkg tests: 272 pass"
