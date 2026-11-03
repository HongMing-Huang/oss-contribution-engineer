#!/usr/bin/env python3
"""test_review_round_fixes.py — regression tests for the second external
review round (category/semantics critique). Pins:

  S5a  init writes .git/info/exclude so evidence can never leak into a commit
  S5b  wholly-untracked directories expand to files in scope audit (no more
       unintended_changes: ["__tests__/"])
  S6   consumer_impact.py finds importers of changed production files and
       refuses completeness without per-consumer verdicts; PR_READY blocks
       until a complete CONSUMER_IMPACT artifact is recorded
  R2   PR template declares exactly-one-problem-per-PR

Run: python3 -m pytest tests/test_review_round_fixes.py -q
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
SESSION = SCRIPTS / "contribution_session.py"
sys.path.insert(0, str(SCRIPTS))
import contribution_session as cs  # noqa: E402


def py(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/env", "python3", *args],
                          capture_output=True, text=True, shell=False)


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/env", "git", "-C", str(repo), *args],
                          capture_output=True, text=True, shell=False)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture()
def repo(tmp_path: Path):
    subprocess.run(["/usr/bin/env", "git", "init", "-q", str(tmp_path)],
                   capture_output=True)
    git(tmp_path, "config", "user.email", "t@t.co")
    git(tmp_path, "config", "user.name", "t")
    write(tmp_path / "mod.py", "x = 1\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def _goal_init(repo: Path):
    r = py(str(SCRIPTS / "goal_compiler.py"), str(repo), "compile",
           "--task-id", "t1", "--intent", "fix target",
           "--done-when", "run: true",
           "--repository", cs.repository_identity(repo))
    assert r.returncode == 0, r.stderr
    goal = sorted((repo / ".oss-contrib-evidence" / "goals").glob("*.json"))[-1]
    p = py(str(SESSION), str(repo), "init", "--task-id", "t1",
           "--goal", str(goal))
    assert p.returncode == 0, p.stderr


# ------------------------------------------------------------------- S5a
def test_init_excludes_evidence_dir_from_git(repo):
    _goal_init(repo)
    exclude = repo / ".git" / "info" / "exclude"
    assert exclude.exists()
    assert ".oss-contrib-evidence" in exclude.read_text()
    # git itself now ignores the evidence dir
    (repo / ".oss-contrib-evidence" / "manifest.jsonl").parent.mkdir(
        parents=True, exist_ok=True)
    (repo / ".oss-contrib-evidence" / "manifest.jsonl").write_text("{}\n")
    st = git(repo, "status", "--porcelain").stdout
    assert ".oss-contrib-evidence" not in st
    # idempotent: a second init must not duplicate the entry
    p = py(str(SESSION), str(repo), "init", "--task-id", "t2", "--fresh",
           "--goal", str(sorted((repo / ".oss-contrib-evidence" / "goals")
                                .glob("*.json"))[-1]))
    assert p.returncode == 0, p.stderr
    assert exclude.read_text().count(".oss-contrib-evidence/") == 1


# ------------------------------------------------------------------- S5b
def test_untracked_dir_expands_to_files_in_scope_audit(repo):
    write(repo / "src" / "lib.ts", "export const a = 1;\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    # a wholly-untracked test directory (never staged)
    write(repo / "__tests__" / "lib.test.ts", "it('a', () => {});\n")
    r = py(str(SCRIPTS / "diff_scope_check.py"), str(repo),
           "--base", "HEAD", "--json")
    assert r.returncode in (0, 1), r.stderr
    out = json.loads(r.stdout)
    assert "__tests__/" not in out["untracked"], \
        "untracked dir must expand to files, not stay a directory entry"
    assert "__tests__/lib.test.ts" in out["untracked"]


# ------------------------------------------------------------------- S6
@pytest.fixture()
def ts_repo(tmp_path: Path):
    """Recreates the reported failure shape: one module imported by three
    production consumers, modified in the working tree."""
    subprocess.run(["/usr/bin/env", "git", "init", "-q", str(tmp_path)],
                   capture_output=True)
    git(tmp_path, "config", "user.email", "t@t.co")
    git(tmp_path, "config", "user.name", "t")
    write(tmp_path / "src" / "server" / "modes" / "mode.ts",
          "export function jsonResponseMode(m: string): boolean {\n"
          "  return m === \"json\";\n}\n")
    for consumer, fn in (("cli/main.ts", "cliMain"), ("eval/ragEval.ts", "evalCase"),
                         ("trace/replay.ts", "replay")):
        write(tmp_path / "src" / consumer,
              "import { jsonResponseMode } from \"../server/modes/mode\";\n"
              "export function %s(m: string) { return jsonResponseMode(m); }\n" % fn)
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "init")
    write(tmp_path / "src" / "server" / "modes" / "mode.ts",
          "export function jsonResponseMode(m: string): boolean {\n"
          "  return m === \"json\" || m === \"raw\";\n}\n")
    return tmp_path


def test_consumer_impact_finds_importers_and_requires_verdicts(ts_repo):
    r = py(str(SCRIPTS / "consumer_impact.py"), str(ts_repo), "--base", "HEAD")
    assert r.returncode == 1  # verdicts outstanding
    for name in ("cli/main.ts", "eval/ragEval.ts", "trace/replay.ts"):
        assert name in r.stdout
    art = json.loads((ts_repo / ".oss-contrib-evidence" /
                      "consumer-impact.json").read_text())
    assert art["type"] == "CONSUMER_IMPACT" and art["digest"]
    # thin verdict refused
    r = py(str(SCRIPTS / "consumer_impact.py"), str(ts_repo),
           "--verdict", "src/cli/main.ts::ok")
    assert r.returncode == 2
    # unlisted path refused
    r = py(str(SCRIPTS / "consumer_impact.py"), str(ts_repo),
           "--verdict", "src/nope.ts::not a listed consumer at all")
    assert r.returncode == 2
    # full verdict set completes
    args = []
    for name in ("src/cli/main.ts", "src/eval/ragEval.ts", "src/trace/replay.ts"):
        args += ["--verdict", "%s::covered by package suite, 272 green" % name]
    r = py(str(SCRIPTS / "consumer_impact.py"), str(ts_repo), *args)
    assert r.returncode == 0, r.stderr
    assert "CONSUMER IMPACT COMPLETE" in r.stdout


def test_pr_ready_blocked_without_consumer_impact(repo):
    """advance to PR_READY must name the missing consumer-impact gate."""
    import argparse
    _goal_init(repo)

    def ns(**kw):
        a = argparse.Namespace()
        for k, v in kw.items():
            setattr(a, k, v)
        return a
    # fast-forward the session state to REVIEW with all other gates satisfied
    s = cs.load_session(repo)
    s["state"] = "REVIEW"
    s["understanding"] = {"status": "UNDERSTOOD", "confirmed_by": "user",
                          "at": cs.now()}
    cs.save_session(repo, s)
    rc = cs.cmd_advance(repo, ns(to="PR_READY"))
    assert rc == 1
    s = cs.load_session(repo)
    assert any("CONSUMER_IMPACT" in b for b in s["blockers"])


# ------------------------------------------------------------------- R2
def test_pr_template_declares_one_problem_per_pr():
    t = (Path(__file__).resolve().parent.parent / "assets" /
         "pull-request-template.md").read_text()
    assert "EXACTLY ONE problem per PR" in t
