#!/usr/bin/env python3
"""consumer_impact.py — who consumes what I changed, and did I check them?

Real-usage defect this closes: a change passed RED, GREEN, package tests,
lint, type-check and scope audit — and still broke three downstream
consumers (CLI, eval harness, replay tool) that only self-review caught.
Every gate proved "commands ran"; none asked "who imports the symbols I
touched, and are they still fine?".

Parse-only and heuristic BY DESIGN (lexical import scan; no LSP/network):
the artifact is an ADVISORY checklist that the PR_READY gate forces you to
walk — every listed consumer needs a recorded verdict, and a verdict is a
sentence a human can audit.

Usage:
  consumer_impact.py <repo> --base HEAD~1        # compute + list consumers
  consumer_impact.py <repo> --verdict "path::why it is safe / how verified"

Exit: 0 complete (or no consumers), 1 verdicts outstanding, 2 usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
             "build", "out", "target", "vendor", "third_party", ".tox",
             ".nox", ".mypy_cache", ".pytest_cache", "coverage", ".next",
             "_build", ".oss-contrib-evidence"}
SCAN_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go"}
RESOLVE_EXTS = ["", ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
                "/index.ts", "/index.tsx", "/index.js", "/index.jsx"]
MAX_FILE_BYTES = 400_000
MAX_SCAN_FILES = 4000

RE_PY = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M)
RE_JS = re.compile(r"""(?:from\s+|import\s*\(\s*|require\s*\(\s*)['"]([^'"]+)['"]""")
RE_GO = re.compile(r"^\s*(?:_\s+)?(?:\.\s+)?\"([\w./-]+)\"", re.M)

TEST_MARKERS = (".test.", ".spec.", "_test.", "/__tests__/", "/tests/")


def _git(repo: Path, *args: str) -> tuple[int, str]:
    p = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True, shell=False)
    return p.returncode, p.stdout


def changed_files(repo: Path, base: str) -> list[str]:
    rc, out = _git(repo, "diff", "--name-only", base)
    if rc != 0:
        print("error: git diff --name-only %s failed" % base, file=sys.stderr)
        raise SystemExit(3)
    files = [l.strip() for l in out.splitlines() if l.strip()]
    rc, status = _git(repo, "status", "--porcelain")
    if rc == 0:
        for l in status.splitlines():
            if l.startswith("??"):
                p = l[3:].strip().strip('"')
                if not p.endswith("/") and p not in SKIP_DIRS:
                    files.append(p)
    return sorted(set(files))


def extract_imports(path: Path) -> list[str]:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return []
    specs: list[str] = []
    if path.suffix == ".py":
        for m in RE_PY.finditer(text):
            specs.append((m.group(1) or m.group(2) or "").split(".")[0])
    elif path.suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
        specs.extend(RE_JS.findall(text))
    elif path.suffix == ".go":
        specs.extend(RE_GO.findall(text))
    return [s for s in specs if s]


def _candidate_targets(changed: str) -> list[str]:
    """How a changed path can be referenced: module stem forms for Python,
    the path-without-extension tail for JS/TS relative imports."""
    p = changed.rsplit(".", 1)[0] if "." in changed.rsplit("/", 1)[-1] else changed
    parts = p.split("/")
    tails = ["/".join(parts[-i:]) for i in range(1, min(4, len(parts)) + 1)]
    if changed.endswith(".py"):
        stems = [changed.rsplit("/", 1)[-1].rsplit(".", 1)[0]]
        return stems + tails
    return tails


def find_consumers(repo: Path, changed: list[str]) -> dict[str, list[dict]]:
    targets = {c: _candidate_targets(c) for c in changed}
    by_repo_path = {c: c.rsplit(".", 1)[0] for c in changed}
    consumers: dict[str, list[dict]] = {c: [] for c in changed}
    scanned = 0
    for dirpath, dirnames, filenames in _walk(repo):
        for fn in filenames:
            f = Path(dirpath) / fn
            if f.suffix not in SCAN_EXTS:
                continue
            scanned += 1
            if scanned > MAX_SCAN_FILES:
                return consumers
            try:
                if f.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            rel = f.relative_to(repo).as_posix()
            if rel in consumers:
                continue  # a changed file importing itself is not a consumer
            specs = extract_imports(f)
            if not specs:
                continue
            is_test = any(m in rel for m in TEST_MARKERS) or "/test" in rel
            for c in changed:
                for spec in specs:
                    if spec.startswith("."):
                        # relative: resolve against the importer's directory
                        base_dir = rel.rsplit("/", 1)[0] if "/" in rel else ""
                        cand = (base_dir + "/" + spec) if base_dir else spec
                        norm = []
                        for s in cand.split("/"):
                            if s == ".." and norm:
                                norm.pop()
                            elif s not in (".", ""):
                                norm.append(s)
                        cand = "/".join(norm)
                        for ext in RESOLVE_EXTS:
                            if cand + ext == by_repo_path[c]:
                                consumers[c].append(
                                    {"path": rel, "via": spec,
                                     "kind": "test" if is_test else "production"})
                                break
                        else:
                            continue
                        break
                    else:
                        # bare/package specifier: tail match against the path
                        hit = any(spec == t or spec.endswith("/" + t)
                                  or t.endswith("/" + spec)
                                  for t in targets[c])
                        if hit:
                            consumers[c].append(
                                {"path": rel, "via": spec,
                                 "kind": "test" if is_test else "production"})
                            break
    return consumers


def _walk(repo: Path):
    import os
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        yield dirpath, dirnames, filenames


def _digest(artifact: dict) -> str:
    return hashlib.sha256(json.dumps(
        {k: v for k, v in artifact.items() if k != "digest"},
        sort_keys=True).encode()).hexdigest()


def _identity(repo: Path) -> str:
    """Origin slug when available (mirrors contribution_session)."""
    p = subprocess.run(["git", "-C", str(repo), "remote", "get-url", "origin"],
                       capture_output=True, text=True, shell=False)
    if p.returncode == 0:
        m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", p.stdout.strip())
        if m:
            return m.group(1)
    return "local-" + hashlib.sha256(str(repo).encode()).hexdigest()[:12]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--base", default="HEAD",
                    help="diff base (default HEAD — the working tree vs HEAD)")
    ap.add_argument("--verdict", action="append", default=[],
                    metavar="PATH::VERDICT",
                    help="record a verdict sentence for one listed consumer "
                         "(repeatable); the sentence is auditable evidence")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print("error: %s is not a directory" % repo, file=sys.stderr)
        return 2

    ev = repo / ".oss-contrib-evidence"
    ev.mkdir(parents=True, exist_ok=True)
    artifact_path = ev / "consumer-impact.json"

    rc, head = _git(repo, "rev-parse", "HEAD")
    if rc != 0:
        print("error: %s is not a git repository" % repo, file=sys.stderr)
        return 3

    changed = [c for c in changed_files(repo, args.base)
               if not any(m in c for m in TEST_MARKERS)]

    if args.verdict:
        if not artifact_path.exists():
            print("error: no consumer-impact artifact yet — run without "
                  "--verdict first", file=sys.stderr)
            return 2
        artifact = json.loads(artifact_path.read_text())
        listed = {c["path"] for cs in artifact["consumers"].values() for c in cs}
        for v in args.verdict:
            if "::" not in v:
                print("error: --verdict expects PATH::verdict (got %r)" % v,
                      file=sys.stderr)
                return 2
            path, text = v.split("::", 1)
            path, text = path.strip(), text.strip()
            if path not in listed:
                print("error: %s is not a listed consumer (listed: %s)"
                      % (path, ", ".join(sorted(listed)) or "none"),
                      file=sys.stderr)
                return 2
            if len(text) < 10:
                print("error: verdict for %s too thin to be auditable" % path,
                      file=sys.stderr)
                return 2
            artifact["verdicts"][path] = text
        artifact["digest"] = _digest(artifact)
        artifact_path.write_text(json.dumps(artifact, indent=2))
        print("verdicts recorded: %d" % len(artifact["verdicts"]))
        listed = {c["path"] for cs in artifact["consumers"].values()
                  for c in cs}
        outstanding = sorted(listed - set(artifact["verdicts"]))
        if outstanding:
            print("still outstanding: %s" % ", ".join(outstanding))
            return 1
        print("RESULT         CONSUMER IMPACT COMPLETE")
        return 0

    consumers = find_consumers(repo, changed)
    artifact = {
        "type": "CONSUMER_IMPACT",
        "schema_version": 1,
        "repository": _identity(repo),
        "base": args.base,
        "git_head": head.strip(),
        "changed_production_files": changed,
        "consumers": consumers,
        "verdicts": {},
        "method": "lexical import scan (python/js/ts/go); heuristic, not "
                  "semantic — LSP-verified references are a stronger future "
                  "method; missing import styles are a known blind spot",
        "generated_by": "consumer_impact.py",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    artifact["digest"] = _digest(artifact)
    artifact_path.write_text(json.dumps(artifact, indent=2))

    total = sum(len(v) for v in consumers.values())
    print("CONSUMER_IMPACT written: %s" % artifact_path)
    print("changed production files: %d; consumers found: %d"
          % (len(changed), total))
    for c, cs in consumers.items():
        for con in cs:
            print("  %-42s <- %-8s %s" % (c[:42], con["kind"], con["path"]))
    if total == 0:
        print("RESULT         NO CONSUMERS FOUND (lexical scan) — say so in "
              "the review rather than claiming 'no impact'")
        return 0
    outstanding = {c["path"] for cs in consumers.values() for c in cs}
    print("next: give each consumer a verdict sentence —")
    print('  consumer_impact.py %s --verdict "path::why safe / how verified"'
          % repo)
    print("(%d verdict(s) outstanding)" % len(outstanding))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
