#!/usr/bin/env python3
"""V10 skill-surface invariant tests (secondary output — production behavior is
the deliverable). Protects only the new workflow invariants:

  1. session investigate composes the whole pipeline and persists Investigation
     State with a VISIBLE fallback chain + CURRENT-digest provenance;
  2. read-source does NOT expand without a question, and one --follow-question
     follows exactly one semantic relation (recorded as evidence);
  3. resume detects repository HEAD drift and names it;
  4. report projects session evidence into the first-class outputs.

Run: python3 -m pytest tests/test_v10_skill_surface.py -q
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
SESSION = SCRIPTS / "contribution_session.py"
GOAL = SCRIPTS / "goal_compiler.py"
sys.path.insert(0, str(SCRIPTS))
import contribution_session as cs  # noqa: E402


def py(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/env", "python3", *args],
                          capture_output=True, text=True, shell=False)


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/env", "git", "-C", str(repo), *args],
                          capture_output=True, text=True, shell=False)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    (r / "src").mkdir(parents=True)
    (r / "src" / "alpha.py").write_text(
        "def alpha():\n    return base_value()\n\n\ndef base_value():\n    return 1\n")
    (r / "CONTRIBUTING.md").write_text("# Contributing\n\nAll patches need a test.\n")
    git(r, "init", "-q")
    git(r, "config", "user.email", "t@t.co")
    git(r, "config", "user.name", "t")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "init")
    goal = py(str(GOAL), str(r), "compile", "--task-id", "v10",
              "--intent", "fix alpha", "--done-when",
              "run: python3 -m pytest -q",
              "--repository", cs.repository_identity(r))
    assert goal.returncode == 0, goal.stderr
    contract = sorted((r / ".oss-contrib-evidence" / "goals").glob("*.json"))[-1]
    s = py(str(SESSION), str(r), "init", "--task-id", "v10", "--goal", str(contract))
    assert s.returncode == 0, s.stderr
    return r


def test_investigate_persists_state_with_visible_fallbacks(repo):
    r = py(str(SESSION), str(repo), "investigate",
           "--task-text", "alpha calls base_value", "--task-type", "bug_report")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "backends used:" in out
    assert "PYTHON_AST" in out and "LEXICAL_LIGHTWEIGHT" in out
    assert "fallback:" in out, "skipped backends must be VISIBLE with reasons"
    st = json.loads((repo / ".oss-contrib-evidence" / "investigation.json").read_text())
    assert st["candidate_files"], "candidate files persisted"
    assert st["candidate_root_causes"], "located symbols persisted"
    prov = st["context"]["provenance"]
    assert prov and all(p["digest_state"] == "CURRENT" for p in prov)
    s = json.loads((repo / ".oss-contrib-evidence" / "session.json").read_text())
    assert s.get("context", {}).get("pack_digest")


def test_read_source_expansion_requires_and_answers_question(repo):
    r = py(str(SESSION), str(repo), "investigate",
           "--task-text", "alpha calls base_value")
    assert r.returncode == 0
    r1 = py(str(SESSION), str(repo), "read-source",
            "--path", "src/alpha.py", "--start", "1")
    assert r1.returncode == 0, r1.stderr
    assert "no expansion" in r1.stdout, "expansion without a question is refused"
    r2 = py(str(SESSION), str(repo), "read-source",
            "--path", "src/alpha.py", "--start", "1",
            "--follow-question", "what does alpha call?")
    assert r2.returncode == 0, r2.stderr
    assert "EXPANSION" in r2.stdout and "base_value" in r2.stdout
    assert "L5-6" in r2.stdout, "the followed symbol's span is shown"
    st = json.loads((repo / ".oss-contrib-evidence" / "investigation.json").read_text())
    answered = st.get("answered_questions", [])
    assert len(answered) == 1 and "call" in answered[0]["relation"]
    assert any(e["text"].startswith("followed")
               and "what does alpha call?" in e["text"]
               for e in st.get("evidence", []))


def test_resume_detects_head_drift(repo):
    py(str(SESSION), str(repo), "investigate",
       "--task-text", "alpha calls base_value")
    (repo / "src" / "alpha.py").write_text(
        "def alpha():\n    return base_value() + 1\n\n\ndef base_value():\n    return 1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "drift")
    r = py(str(SESSION), str(repo), "resume")
    assert r.returncode == 1, "resume must flag staleness"
    assert "HEAD changed" in r.stdout
    r_ok = py(str(SESSION), str(repo), "explain-blocker")
    assert "next transition" in r_ok.stdout


def test_report_projects_session_evidence(repo):
    py(str(SESSION), str(repo), "investigate",
       "--task-text", "alpha calls base_value")
    py(str(SESSION), str(repo), "note", "--kind", "known_facts",
       "--text", "alpha delegates to base_value")
    r = py(str(SESSION), str(repo), "report")
    assert r.returncode == 0, r.stderr
    out = repo / ".oss-contrib-evidence" / "report"
    names = {p.name for p in out.glob("*.md")}
    assert {"walkthrough.md", "root-cause.md", "code-neighborhood.md",
            "validation-summary.md", "risk-and-nongoals.md",
            "understanding-prompts.md", "issue-draft.md"} <= names
    rc = (out / "root-cause.md").read_text()
    assert "alpha delegates to base_value" in rc, "projection from evidence, not hand-written"


def test_evidence_cwd_pins_the_witnessed_run(repo):
    # V9 F4: without --cwd the command ran from the caller's cwd and
    # relative paths failed spuriously; --cwd pins it and is recorded.
    r = py(str(SESSION), str(repo), "evidence",
           "--purpose", "cwd-bound run: show repo-local file",
           "--evidence-type", "REPRODUCTION", "--cwd", str(repo),
           "--", "/usr/bin/env", "sh", "-c", "test -f CONTRIBUTING.md && pwd")
    assert r.returncode == 0, r.stderr
    entry = json.loads(
        (repo / ".oss-contrib-evidence" / "manifest.jsonl").read_text().splitlines()[-1])
    assert entry["cwd"] == str(repo)
    assert entry["status"] == "PASS"


def test_unconfirmed_is_a_stopping_classification(repo):
    # V9 F6: a real issue that cannot be reproduced needs an honest terminal
    # class; UNCONFIRMED must end the run and block patch-side states.
    r = py(str(SESSION), str(repo), "set-classification",
           "--classification", "UNCONFIRMED")
    assert r.returncode == 0, r.stderr
    r2 = py(str(SESSION), str(repo), "advance", "--to", "DEDUPLICATE")
    assert r2.returncode != 0, "UNCONFIRMED is not STOPPING"
    r3 = py(str(SESSION), str(repo), "advance", "--to", "PROVE")
    assert r3.returncode != 0, "UNCONFIRMED is not STOPPING"
