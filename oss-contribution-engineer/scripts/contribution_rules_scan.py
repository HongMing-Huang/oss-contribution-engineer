#!/usr/bin/env python3
"""contribution_rules_scan.py — locate and excerpt repository-local contribution rules.

Finds instruction files (CONTRIBUTING, AGENTS.md, CLAUDE.md, SECURITY, templates,
governance docs — including nested copies) and excerpts lines matched by rule-relevant
keywords, so the caller knows which files to read in full.

This is a collector: matched lines are keyword hits, not interpretations. Read the
surfaced files; repository-local rules override the generic workflow.

Exit codes: 0 = scanned, 2 = usage error, 3 = repository not found.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git", ".hg", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    "out", "target", "vendor", "third_party", ".tox", ".nox", ".mypy_cache",
    ".pytest_cache", "site-packages", ".next", "coverage", "_build", "deps",
}

INSTRUCTION_NAMES = [
    "contributing", "code_of_conduct", "security", "developing", "development",
    "hacking", "maintainers", "governance", "releasing", "readme", "changelog",
    "changes", "pull_request_template", "issue_template", "support", "notice",
]
AI_NAMES = ["agents.md", "claude.md", "gemini.md", "copilot-instructions.md",
            ".cursorrules", "cursor-rules"]

MAX_FILE_BYTES = 400_000
MAX_LINES_PER_FILE = 12
MAX_TOTAL_FILES = 80

# keyword -> regex (short/ambiguous terms get word boundaries)
KEYWORDS: list[tuple[str, re.Pattern]] = [
    ("sign-off/DCO", re.compile(r"sign[- ]?off|\bDCO\b|developer.?s certificate of origin", re.I)),
    ("CLA", re.compile(r"\bCLA\b|contributor license|contributor agreement", re.I)),
    ("commit convention", re.compile(r"commit message|conventional commits|commit convention|signed-off|fixes #|closes #", re.I)),
    ("branching", re.compile(r"\bbranch(es|ing)?\b", re.I)),
    ("testing", re.compile(r"\btest(s|ing)?\b", re.I)),
    ("lint/format", re.compile(r"\blint(er)?\b|\bformat(ter|ting)?\b|pre-commit|ruff|clang-format|prettier|eslint", re.I)),
    ("build", re.compile(r"\bbuild(ing)?\b|compile", re.I)),
    ("PR process", re.compile(r"pull request|\bPR\b", re.I)),
    ("issue process", re.compile(r"\bissue(s)?\b", re.I)),
    ("claiming", re.compile(r"assign|\bclaim(ed|ing)?\b|work on this|before (you )?start", re.I)),
    ("changelog", re.compile(r"changelog|changeset|release notes|towncrier|newsfragment", re.I)),
    ("AI policy", re.compile(r"\bAI\b|\bLLM\b|\bGPT\b|assistant|generated (code|content)|coding agent|copilot|claude|chatgpt|machine[- ]generated", re.I)),
    ("security", re.compile(r"secur|vulnerab|private(ly)? (report|disclos)|responsible disclosure", re.I)),
    ("disclosure/attribution", re.compile(r"disclos|attribut|assisted-by|co-authored|report(ed)?-by", re.I)),
    ("review", re.compile(r"review", re.I)),
    ("conduct", re.compile(r"code of conduct|harassment|inclusive", re.I)),
]


def is_instruction_file(rel_name: str) -> str | None:
    name = rel_name.lower()
    base = os.path.basename(name)
    stem = base.rsplit(".", 1)[0] if "." in base else base
    for ai in AI_NAMES:
        if base == ai:
            return "ai_instruction"
    if base.startswith("copilot-instructions") or base.startswith(".cursorrules"):
        return "ai_instruction"
    for n in INSTRUCTION_NAMES:
        if stem.startswith(n):
            return "governance_doc"
    if ".github" in name and "template" in base:
        return "template"
    return None


def scan(repo: Path, max_depth: int) -> dict:
    root_depth = len(repo.parts)
    found: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(repo):
        cur = Path(dirpath)
        depth = len(cur.parts) - root_depth
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        if depth >= max_depth:
            dirnames[:] = []
        for fn in sorted(filenames):
            kind = is_instruction_file(fn)
            if not kind:
                continue
            path = cur / fn
            rel = path.relative_to(repo).as_posix()
            found.append({"path": rel, "kind": kind, "bytes": path.stat().st_size})
    found = [f for f in found if f["bytes"] <= MAX_FILE_BYTES][:MAX_TOTAL_FILES]
    skipped_big = sum(1 for f in found if f["bytes"] > MAX_FILE_BYTES)

    results = []
    for f in found:
        path = repo / f["path"]
        try:
            text = path.read_text(errors="replace")
        except OSError as e:
            results.append({**f, "matched_lines": [], "error": str(e)})
            continue
        hits: list[dict] = []
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("<!--",)):
                continue
            tags = [label for label, rx in KEYWORDS if rx.search(stripped)]
            if tags:
                hits.append({"line": lineno, "tags": tags, "text": stripped[:240]})
            if len(hits) >= MAX_LINES_PER_FILE:
                break
        results.append({**f, "matched_lines": hits})

    return {
        "repository": str(repo),
        "instruction_files": results,
        "files_skipped_for_size": skipped_big,
        "keyword_lexicon": [k for k, _ in KEYWORDS],
        "notes": [
            "matched lines are keyword hits, not interpretations — read each file in full before acting",
            "nested copies (e.g. packages/*/AGENTS.md) bind when working inside that subtree",
            "repository-local rules override the generic oss-contribution-engineer workflow",
        ],
    }


def summarize(report: dict) -> str:
    lines = [f"Contribution rules scan: {report['repository']}"]
    for f in report["instruction_files"]:
        star = " *AI*" if f["kind"] == "ai_instruction" else ""
        lines.append(f"  {f['path']} ({f['bytes']} bytes){star}")
        for h in f.get("matched_lines", []):
            lines.append(f"    L{h['line']} [{', '.join(h['tags'])}] {h['text']}")
    lines.append("Next: read every listed file in full; treat its rules as binding.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Locate and excerpt repository-local contribution rules.")
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--max-depth", type=int, default=4)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"error: {repo} is not a directory", file=sys.stderr)
        return 3
    report = scan(repo, max(1, args.max_depth))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(summarize(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
