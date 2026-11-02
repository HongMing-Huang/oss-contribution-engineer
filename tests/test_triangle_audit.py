#!/usr/bin/env python3
"""test_triangle_audit.py — V12 §2 doc/code/test triangle consistency.

Three orphan classes, each mechanically checkable:
  A. claimed-without-test: ENFORCED capabilities whose cited test ids do not
     exist as real pytest functions (extends test_capability_claims by also
     checking the FUNCTION names, not just the files).
  B. tested-but-undocumented: session CLI subcommands exercised by the test
     suite but never mentioned in SKILL.md (hidden surface).
  C. mentioned-but-nonexistent: capability evidence naming script paths that
     do not exist on disk.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "SKILL.md"
CAPS = ROOT / "CAPABILITIES.json"
TESTS = ROOT / "tests"
SESSION = ROOT / "scripts" / "contribution_session.py"


def test_enforced_citations_resolve_to_real_functions():
    caps = json.loads(CAPS.read_text())["capabilities"]
    problems = []
    for name, cap in caps.items():
        for cite in cap.get("tests") or []:
            if "#" not in cite:
                problems.append("%s: citation %r lacks #function" % (name, cite))
                continue
            fname, func = cite.rsplit("#", 1)
            fpath = ROOT / fname
            if not fpath.exists():
                problems.append("%s: cited file %s missing" % (name, fname))
                continue
            if not re.search(r"def %s\(" % re.escape(func), fpath.read_text()):
                problems.append("%s: function %s not defined in %s"
                                % (name, func, fname))
    assert not problems, "claimed-without-test orphans:\n  " + "\n  ".join(problems)


def test_session_subcommands_exercised_are_documented():
    p = subprocess.run(["/usr/bin/env", "python3", str(SESSION), "--help"],
                       capture_output=True, text=True, shell=False)
    m = re.search(r"\{([a-z-]+(?:,[a-z-]+)+)\}", p.stdout)
    assert m, "cannot parse CLI surface"
    surface = set(m.group(1).split(","))
    # subcommands actually driven by the test suite (string literals in tests)
    exercised = set()
    for tf in TESTS.glob("*.py"):
        text = tf.read_text()
        for sub in surface:
            if re.search(r'"%s"' % re.escape(sub), text) or \
               re.search(r"'%s'" % re.escape(sub), text):
                exercised.add(sub)
    doc = SKILL.read_text()
    undocumented = sorted(s for s in exercised if s not in doc)
    # expert/debug-only commands may be exercised without headline docs, but
    # they must at least appear in the script index row for the session
    assert not undocumented, \
        "tested-but-undocumented session subcommands: %s" % undocumented


def test_capability_evidence_paths_exist():
    caps = json.loads(CAPS.read_text())["capabilities"]
    problems = []
    for name, cap in caps.items():
        for path in re.findall(r"scripts/[\w\-./]+\.py",
                               cap.get("evidence") or ""):
            if not (ROOT / path).exists():
                problems.append("%s: evidence names missing script %s"
                                % (name, path))
    assert not problems, "mentioned-but-nonexistent orphans:\n  " + \
        "\n  ".join(problems)
