#!/usr/bin/env python3
"""diff_scope_check.py — compare the actual diff against the stated intended scope.

Reports per-file categorization (production / test / docs / manifest / lockfile /
generated / config), formatting-only files, and drift against an --intended file list.
Flags scope drift and diff-budget overrun so scope creep becomes visible before a PR.

All subprocess calls use argv lists with shell=False (no shell interpretation).

Exit codes: 0 = clean (within budget, no drift), 1 = drift or budget findings,
2 = usage error, 3 = not a git repository.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

LOCKFILES = {
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml",
    "Cargo.lock", "poetry.lock", "uv.lock", "Pipfile.lock", "go.sum", "Gemfile.lock",
    "composer.lock", "packages.lock.json", "bun.lockb", "Podfile.lock",
}
MANIFESTS = [
    "package.json", "pyproject.toml", "setup.py", "setup.cfg", "go.mod", "go.work",
    "Cargo.toml", "pom.xml", "build.gradle", "build.gradle.kts", "Gemfile",
    "composer.json", "mix.exs", "requirements*.txt", "Pipfile", "Package.swift",
    "*.csproj", "*.fsproj",
]
GENERATED_PATTERNS = [
    "*.min.js", "*.min.css", "*.map", "*.snap", "*.pb.go", "*_pb2.py",
    "*_pb2_grpc.py", "*.generated.*", "*.g.cs", "*_gen.go", "*.ipynb",
]
GENERATED_DIRS = ["dist/", "vendor/", "__snapshots__/", "coverage/", ".gen/", "generated/"]

TEST_HINTS = ["test", "spec", "tests/", "testing/"]
DOC_EXTS = [".md", ".rst", ".txt", ".adoc"]
CONFIG_HINTS = [".github/", ".gitlab/", ".circleci/", ".gitea/"]

BUDGET = {"production_files": 5, "test_files": 3, "new_dependencies": 0}


def _diff_added_lines(repo: Path, base: str, path: str):
    """Return (rc, added '+' lines) of base..worktree for one file."""
    p = subprocess.run(["git", "-C", str(repo), "diff", base, "--", path],
                       capture_output=True, text=True, shell=False)
    if p.returncode != 0:
        return p.returncode, "", ""
    added = [l[1:] for l in p.stdout.splitlines()
             if l.startswith("+") and not l.startswith("+++")]
    return 0, "\n".join(added), ""


def make_git_runner(repo: Path):
    repo_arg = str(repo)

    def run_git(args: list[str]) -> tuple[int, str, str]:
        # Inline argv list + shell=False: git never interprets anything through a shell.
        p = subprocess.run(["git", "-C", repo_arg, *args],
                           capture_output=True, text=True, shell=False)
        return p.returncode, p.stdout, p.stderr

    return run_git


def _git_head(repo: Path, *args: str) -> str | None:
    rc, out, _ = make_git_runner(repo)(["rev-parse", *args]) if args else \
        make_git_runner(repo)(["rev-parse", "HEAD"])
    return out.strip() if rc == 0 else None


def categorize(path: str) -> str:
    p = path.replace("\\", "/")
    low = p.lower()
    for lf in LOCKFILES:
        if low.endswith("/" + lf) or low == lf:
            return "lockfile"
    for m in MANIFESTS:
        if fnmatch.fnmatch(low, m) or low.endswith("/" + m):
            return "manifest"
    for d in GENERATED_DIRS:
        if low.startswith(d) or "/" + d in low:
            return "generated"
    for pat in GENERATED_PATTERNS:
        if fnmatch.fnmatch(low, pat) or fnmatch.fnmatch(low.split("/")[-1], pat):
            return "generated"
    base = low.rsplit("/", 1)[-1]
    if any(h in low for h in TEST_HINTS) or base.startswith("test_") or base.endswith("_test.go") \
            or base.startswith("conftest.") or base.endswith("_test.py"):
        return "test"
    if any(low.endswith(e) for e in DOC_EXTS):
        return "docs"
    if any(low.startswith(h) or "/" + h in low for h in CONFIG_HINTS) or low.endswith(
            (".yml", ".yaml", ".toml", ".cfg", ".ini", ".editorconfig")) \
            or base in ("makefile", "dockerfile", "jenkinsfile") or base.startswith("dockerfile"):
        return "config"
    return "production"


def main() -> int:
    ap = argparse.ArgumentParser(description="Diff scope audit against intended files and budget.")
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--base", default="HEAD", help="base ref (default HEAD; e.g. origin/main)")
    ap.add_argument("--intended", nargs="+", action="extend", default=[],
                    help="intended file paths — space-separated, repeatable, "
                         "and/or comma-separated (all forms accepted)")
    ap.add_argument("--hats", default="", help="declared hats for production files: path=BEHAVIOR|REFACTOR,...")
    ap.add_argument("--show-hats", action="store_true", help="include per-file two-hats classification")
    ap.add_argument("--show-delta", action="store_true", help="include complexity delta in JSON output")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    hats_arg = args.hats
    show_hats = args.show_hats
    show_delta = args.show_delta
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print("error: %s is not a directory" % repo, file=sys.stderr)
        return 3
    run_git = make_git_runner(repo)

    rc, _, _ = run_git(["rev-parse", "--git-dir"])
    if rc != 0:
        print("error: %s is not a git repository" % repo, file=sys.stderr)
        return 3
    base = args.base.strip()
    if not base or base.startswith("-"):
        print("error: --base must be a non-empty ref not starting with '-'", file=sys.stderr)
        return 2

    rc, out, err = run_git(["diff", "--numstat", base])
    if rc != 0:
        print("error: git diff failed: %s" % err.strip(), file=sys.stderr)
        return 3
    rc, status_out, _ = run_git(["status", "--porcelain"])
    status_lines = status_out.splitlines() if rc == 0 else []

    files: dict[str, dict] = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added, deleted, path = parts[0], parts[1], parts[2]
        files[path] = {
            "added": 0 if added == "-" else int(added),
            "deleted": 0 if deleted == "-" else int(deleted),
            "category": categorize(path),
        }
    tooling_prefixes = (".oss-contrib-evidence/", "__pycache__/", "tests/__pycache__/")
    untracked = []
    for l in status_lines:
        if not l.startswith("??"):
            continue
        path = l[3:].strip('"')
        if path.endswith(".pyc") or path.startswith(tooling_prefixes) or "/__pycache__/" in path:
            continue  # tooling output, not patch scope
        if path.endswith("/"):
            # git reports a wholly-untracked DIRECTORY as one entry — expand it
            # to files so scope findings name real paths, not "dir/" (real-usage
            # defect: new __tests__/ was flagged wholesale until staged)
            d = repo / path
            n = 0
            for sub in sorted(d.rglob("*")):
                if sub.is_file() and not sub.name.endswith(".pyc") \
                        and "__pycache__" not in sub.parts:
                    untracked.append(sub.relative_to(repo).as_posix())
                    n += 1
                    if n >= 200:
                        break
            continue
        untracked.append(path)
    for path in untracked:
        if path not in files:
            files[path] = {"added": None, "deleted": None, "category": categorize(path),
                           "untracked": True}

    # formatting-only detection for small files: a diff that ignores whitespace and
    # blank lines and yields no +/- body lines changed only spacing.
    for path, info in files.items():
        if info["added"] is not None and info["added"] + info["deleted"] <= 120:
            rc, wout, _ = run_git(["diff", "-w", "--ignore-blank-lines", base, "--", path])
            body = [l for l in wout.splitlines()
                    if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
            info["formatting_only"] = (rc == 0 and len(body) == 0)

    counts: dict[str, int] = {}
    for info in files.values():
        counts[info["category"]] = counts.get(info["category"], 0) + 1

    # accept every reasonable spelling: "--intended a b", repeated flags,
    # and the old comma-separated single string
    intended = [p for tok in args.intended for p in tok.split(",") if p.strip()]
    unintended = sorted(p for p in files if p not in intended) if intended else []
    missing = sorted(p for p in intended if p not in files) if intended else []

    lock_or_manifest = sorted(p for p, i in files.items() if i["category"] in ("lockfile", "manifest"))
    formatting = sorted(p for p, i in files.items() if i.get("formatting_only") is True)

    budget_findings = []
    if counts.get("production_files", 0) > BUDGET["production_files"]:
        budget_findings.append("production files %d > %d" % (counts["production_files"], BUDGET["production_files"]))
    if counts.get("test_files", 0) > BUDGET["test_files"]:
        budget_findings.append("test files %d > %d" % (counts["test_files"], BUDGET["test_files"]))
    if lock_or_manifest:
        budget_findings.append("dependency surface changed (%s) — verify every dependency "
                               "change is required by the fix" % ", ".join(lock_or_manifest))

    # ---- V5.3 complexity delta + two-hats classification ----
    # Complexity accumulates incrementally: surface what a patch ADDS so the
    # new concepts can be justified. Not an automatic rejection.
    hats_declared = {}
    for pair in (hats_arg or "").split(","):
        if "=" in pair:
            fp, hat = pair.split("=", 1)
            hats_declared[fp.strip()] = hat.strip().upper()

    import re as _re
    DEF_PAT = _re.compile(
        r"^\s*(?:async\s+)?(?:def|function|fn|func)\s+\w+|^\s*(?:pub\s+)?"
        r"(?:class|struct|trait|interface|enum)\s+\w+", _re.M)
    BRANCH_PAT = _re.compile(r"^\s*(?:if|elif|else\b|match|case|switch|except|catch\b)", _re.M)
    FLAG_PAT = _re.compile(r"add_argument\(|--[a-z][a-z-]+", _re.M)
    IMPORT_PAT = _re.compile(r"^\s*(?:import |from \w+ |require\(|use \w+|#include)", _re.M)

    delta = {"new_symbols": 0, "new_branches": 0, "new_flags": 0,
             "new_imports": 0, "added_lines_production": 0,
             "new_public_contracts": 0, "per_file": []}
    hats = []
    BOOKKEEPING_PREFIXES = (".oss-contrib-evidence/", ".oss-contrib/",
                            "__pycache__/", ".git/")
    for path, info in sorted(files.items()):
        if path.startswith(BOOKKEEPING_PREFIXES) or "/__pycache__/" in path \
                or path.endswith(".pyc"):
            continue  # runtime bookkeeping — not patch scope, not production
        cat = info["category"]
        entry = {"path": path, "category": cat}
        if info.get("untracked") or (info["added"] is None):
            entry["added"] = None
        else:
            entry["added"] = info["added"]
        added_prod = 0
        if cat == "production" and (info["added"] or 0) > 0:
            rc2, out2, _ = _diff_added_lines(repo, base, path)
            if rc2 == 0:
                added_lines = out2
                defs = len(DEF_PAT.findall(added_lines))
                branches = len(BRANCH_PAT.findall(added_lines))
                flags = len(FLAG_PAT.findall(added_lines))
                imports = len(IMPORT_PAT.findall(added_lines))
                added_prod = len(added_lines.splitlines())
                delta["new_symbols"] += defs
                delta["new_branches"] += branches
                delta["new_flags"] += flags
                delta["new_imports"] += imports
                delta["added_lines_production"] += added_prod
                entry["complexity"] = {"new_symbols": defs, "new_branches": branches,
                                       "new_flags": flags, "new_imports": imports,
                                       "added_lines": added_prod}
                if defs and not info.get("formatting_only"):
                    entry["hint"] = "adds new symbol definitions — BEHAVIOR or REFACTOR?"
        # two hats: TEST / MECHANICAL / declared / undecided
        if cat == "test":
            entry["hat"] = "TEST"
        elif info.get("formatting_only"):
            entry["hat"] = "MECHANICAL"
        elif path in hats_declared:
            entry["hat"] = hats_declared[path]
        elif cat == "production":
            entry["hat"] = "UNDECLARED (BEHAVIOR or REFACTOR — declare via --hat)"
        hats.append(entry)
        if cat == "test":
            pass
    delta["per_file"] = [e for e in hats if e["category"] == "production"]
    delta["justification_required"] = (
        delta["new_symbols"] >= 3 or delta["new_imports"] > 0
        or delta["added_lines_production"] > 200)
    report = {
        "type": "SCOPE_AUDIT",
        "schema_version": 1,
        "repository": str(repo),
        "base_sha": _git_head(repo, "rev-parse", base) or None,
        "head_sha": _git_head(repo, "rev-parse", "HEAD"),
        "generated_by": "diff_scope_check.py",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "base": base,
        "changed_files": files,
        "category_counts": counts,
        "untracked": untracked,
        "intended": intended,
        "unintended_changes": unintended,
        "intended_but_unchanged": missing,
        "dependency_surface_changed": lock_or_manifest,
        "formatting_only_files": formatting,
        "budget_findings": budget_findings,
        "budget_defaults": BUDGET,
        "complexity_delta": delta if show_delta else None,
        "hats": hats if show_hats else None,
        "conclusion": "SCOPE_FINDINGS" if (unintended or budget_findings) else "WITHIN_SCOPE",
        "notes": ["categories are heuristic path patterns, not semantics — verify flagged files",
                  "budget is the small-fix default from references/patch-design.md; justified "
                  "larger scope needs an explicit plan"],
    }
    report["digest"] = hashlib.sha256(json.dumps(
        {k: v for k, v in report.items() if k != "digest"}, sort_keys=True).encode()).hexdigest()

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("Diff scope audit vs %s (%d changed files)" % (base, len(files)))
        for path, info in sorted(files.items()):
            extra = []
            if info.get("untracked"):
                extra.append("untracked")
            if info.get("formatting_only"):
                extra.append("formatting-only")
            size = ("+%d/-%d" % (info["added"] or 0, info["deleted"] or 0)) if not info.get("untracked") else "n/a"
            print("  [%s] %8s  %s%s" % (info["category"], size, path,
                                        (" (" + ", ".join(extra) + ")") if extra else ""))
        print("  counts: %s" % json.dumps(counts))
        if unintended:
            print("  UNINTENDED (not in --intended): %s" % ", ".join(unintended))
        if missing:
            print("  intended but unchanged: %s" % ", ".join(missing))
        for f in budget_findings:
            print("  BUDGET: %s" % f)
        print("  conclusion: %s" % report["conclusion"])
    return 1 if (unintended or budget_findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
