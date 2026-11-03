#!/usr/bin/env python3
"""test_skill_lint.py — V12 §1 mechanical compliance audit of the Skill's
consumer-facing surface. Consumer-side evidence: the checks read SKILL.md and
the CLI's own --help output as raw material; no self-authored summaries are
consulted. Runs in CI via pytest, so results are reproducible by anyone.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "SKILL.md"
SESSION = ROOT / "scripts" / "contribution_session.py"
ALLOWED_FRONTMATTER = {"name", "description", "license", "compatibility",
                       "metadata"}


def _frontmatter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "SKILL.md must start with a --- frontmatter block"
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def _cli_help(*args: str) -> str:
    p = subprocess.run(["/usr/bin/env", "python3", str(SESSION), *args, "--help"],
                       capture_output=True, text=True, shell=False)
    assert p.returncode == 0, p.stderr
    return p.stdout


def test_frontmatter_fields_legal():
    fm = _frontmatter(SKILL.read_text())
    bad = set(fm) - ALLOWED_FRONTMATTER
    assert not bad, "illegal frontmatter keys: %s" % sorted(bad)
    for req in ("name", "description"):
        assert fm.get(req), "missing required key: %s" % req


def test_description_char_budget():
    fm = _frontmatter(SKILL.read_text())
    d = fm.get("description", "")
    assert len(d) <= 1024, "description %d > 1024 chars" % len(d)
    assert len(d) > 200, "description suspiciously short for trigger coverage"


def test_body_line_budget():
    text = SKILL.read_text()
    body = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.S)
    lines = body.count("\n") + 1
    assert lines <= 500, "SKILL.md body is %d lines (> 500 cap)" % lines


def test_referenced_paths_exist():
    text = SKILL.read_text()
    refs = set(re.findall(r"(?:references|assets|scripts)/[\w\-./]+", text))
    refs = {r.rstrip(".,;:)\"]") for r in refs}  # strip sentence punctuation
    assert refs, "no internal references found — check the extraction pattern"
    missing = [r for r in sorted(refs) if not (ROOT / r).exists()]
    assert not missing, "SKILL.md references nonexistent files: %s" % missing


def test_bash_examples_match_cli_surface():
    """Every session subcommand + flag shown in SKILL.md bash blocks must be
    accepted by the real CLI today (no stale examples)."""
    text = SKILL.read_text()
    blocks = re.findall(r"```bash\n(.*?)```", text, re.S)
    assert blocks, "no bash blocks found"
    usage = []
    for b in blocks:
        for line in b.splitlines():
            line = line.strip()
            if "contribution_session.py" not in line and not line.startswith("$S"):
                continue
            usage.append(line)
    sub_help = _cli_help()
    # definitive surface: the {a,b,c} usage line argparse prints
    m = re.search(r"\{([a-z-]+(?:,[a-z-]+)+)\}", sub_help)
    assert m, "could not parse subcommand list from top-level --help"
    subcommands = set(m.group(1).split(","))
    problems = []
    for line in usage:
        if line.startswith("#") or line.startswith("S="):
            continue
        # normalize the $S/<skill-dir> prefix forms
        norm = re.sub(r"^S=.*$", "", line)
        norm = re.sub(r"^\$S\s+", "", line)
        norm = re.sub(r"^python3\s+\S*contribution_session\.py\s+", "", norm)
        norm = re.sub(r"^<repo>\s+", "", norm)
        norm = re.sub(r"^<repo>\s*", "", norm)
        tokens = norm.split()
        if not tokens:
            continue
        sub = tokens[0]
        if sub.startswith("-"):
            continue  # global-flag-only line
        if sub not in subcommands:
            problems.append("unknown subcommand %r in line: %s" % (sub, line))
            continue
        flags = {t for t in tokens[1:] if t.startswith("--")}
        flags = {f.rstrip('"]') for f in flags}
        accepted = set(re.findall(r"--[\w-]+", _cli_help(sub)))
        bad = flags - accepted
        if bad:
            problems.append("subcommand %s: flags %s not in --help (line: %s)"
                            % (sub, sorted(bad), line))
    assert not problems, "stale CLI usage in SKILL.md:\n  " + "\n  ".join(problems)


def test_cli_surface_documented():
    """Inverse direction: every production-surface subcommand the CLI offers
    must appear in SKILL.md (no hidden surface)."""
    text = SKILL.read_text()
    sub_help = _cli_help()
    names = set(re.findall(r"^\s{2,}(\S+)\s{2,}", sub_help, re.M))
    # top-level argparse lists subcommands with descriptions; keep the
    # workflow ones every agent must know about
    must_document = {"investigate", "note", "read-source", "evidence",
                     "read-rules", "refresh-context", "explain-blocker",
                     "resume", "report", "status", "advance", "init"}
    missing = sorted(s for s in must_document if s in names and s not in text)
    assert not missing, "CLI offers but SKILL.md never mentions: %s" % missing


def test_inline_script_invocations_use_real_subcommands():
    """Real-usage defect class (lobehub session, problems 4/5): SKILL.md
    showed script invocations that the real CLI rejects — missing or stale
    subcommands. Any inline-code span or bash-block line that invokes a
    script must name a subcommand the script's argparse exposes today."""
    text = SKILL.read_text()
    script_names = sorted(set(re.findall(r"scripts/([\w\-]+\.py)", text)))
    assert script_names, "no scripts/ references found"
    candidates = re.findall(r"`([^`\n]+)`", text)
    for block in re.findall(r"```bash\n(.*?)```", text, re.S):
        candidates.extend(l.strip() for l in block.splitlines() if l.strip())
    problems = []
    for name in script_names:
        script = ROOT / "scripts" / name
        if not script.exists():
            continue  # missing files are test_referenced_paths_exist's job
        p = subprocess.run(["/usr/bin/env", "python3", str(script), "--help"],
                           capture_output=True, text=True, shell=False)
        if p.returncode != 0:
            continue
        m = re.search(r"\{([a-z-]+(?:,[a-z-]+)+)\}", p.stdout)
        if not m:
            continue  # script has no subcommand surface
        valid = set(m.group(1).split(","))
        for cand in candidates:
            tokens = cand.split()
            if len(tokens) < 2 or tokens[0].rsplit("/", 1)[-1] != name:
                continue  # not an invocation (bare mention) of this script
            words = set()
            for t in tokens[1:]:
                t = t.strip("`\"'|;,()<>")
                if not t or t.startswith(("-", "$", "<")):
                    continue
                words.add(t.lower())
            if not words & valid:
                problems.append("%s invoked without a real subcommand: %r "
                                "(valid: %s)" % (name, cand, sorted(valid)))
    assert not problems, "stale script usage in SKILL.md:\n  " + \
        "\n  ".join(problems)
