#!/usr/bin/env python3
"""envcheck.py — first-run environment check (ecosystem convention for
script-heavy skills). Verifies everything the skill's runtime needs, prints
a pass/fail table, and tells the user exactly what to install when missing.

Usage: python3 <SKILL_DIR>/scripts/envcheck.py
Exit: 0 all critical checks pass; 1 any critical check fails.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

CRITICAL = "critical"
OPTIONAL = "optional"


def check(name: str, kind: str, verify) -> tuple:
    try:
        ok, detail = verify()
    except Exception as exc:
        ok, detail = False, str(exc)[:120]
    return (name, kind, ok, detail)


def _has_cmd(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def v_python():
    v = sys.version_info
    return v >= (3, 10), "Python %d.%d.%d %s" % (
        v.major, v.minor, v.micro, "(need ≥3.10)" if v < (3, 10) else "")


def v_git():
    if not _has_cmd("git"):
        return False, "not found"
    p = subprocess.run(["git", "--version"], capture_output=True, text=True,
                       shell=False)
    return p.returncode == 0, p.stdout.strip()


def v_gh():
    if not _has_cmd("gh"):
        return False, "not found (needed for --from-issue and dedupe captures)"
    p = subprocess.run(["gh", "--version"], capture_output=True, text=True,
                       shell=False)
    return p.returncode == 0, p.stdout.splitlines()[0] if p.stdout else "?"


def v_gh_auth():
    if not _has_cmd("gh"):
        return False, "gh not installed"
    p = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True,
                       shell=False)
    return p.returncode == 0, ("authenticated" if p.returncode == 0
                                else "not authenticated (run: gh auth login)")


def v_serena():
    cmd = shutil.which("serena")
    return cmd is not None, cmd or "not installed (optional: LSP symbol backend)"


def v_gopls():
    return _has_cmd("gopls"), "found" if _has_cmd("gopls") else \
        "not installed (optional: Go LSP, go install golang.org/x/tools/gopls@latest)"


def v_tsserver():
    return _has_cmd("typescript-language-server"), \
        "found" if _has_cmd("typescript-language-server") else \
        "not installed (optional: TS LSP, npm i -g typescript-language-server)"


def v_skill_dir():
    d = Path(__file__).resolve().parent.parent
    parts = ["SKILL.md", "scripts", "references", "assets", "CAPABILITIES.json"]
    missing = [p for p in parts if not (d / p).exists()]
    return not missing, str(d) + (" (missing: %s)" % missing if missing else "")


def main() -> int:
    checks = [
        check("Python ≥ 3.10", CRITICAL, v_python),
        check("git", CRITICAL, v_git),
        check("gh CLI", CRITICAL, v_gh),
        check("gh authenticated", OPTIONAL, v_gh_auth),
        check("Skill directory", CRITICAL, v_skill_dir),
        check("serena (LSP)", OPTIONAL, v_serena),
        check("gopls (Go LSP)", OPTIONAL, v_gopls),
        check("typescript-language-server", OPTIONAL, v_tsserver),
    ]
    print("oss-contribution-engineer — environment check")
    print("=" * 56)
    failed_critical = False
    for name, kind, ok, detail in checks:
        icon = "✅" if ok else ("⚠️ " if kind == OPTIONAL else "❌")
        print("  %s [%s] %s" % (icon, kind, name))
        if detail:
            print("       %s" % detail)
        if not ok and kind == CRITICAL:
            failed_critical = True
    print("=" * 56)
    if failed_critical:
        print("RESULT: FAILED — fix the ❌ critical items above, then re-run.")
        print("  Install hints: Python from python.org; git from git-scm.com;")
        print("  gh from cli.github.com then 'gh auth login'.")
        return 1
    opt_missing = sum(1 for _, k, ok, _ in checks if k == OPTIONAL and not ok)
    if opt_missing:
        print("RESULT: READY (⚠️ %d optional backend(s) not installed — "
              "the skill works without them)" % opt_missing)
    else:
        print("RESULT: READY — all checks passed.")
    print("\nQuick start:")
    print("  python3 <SKILL_DIR>/scripts/contribution_session.py <repo> "
          "investigate --from-issue OWNER/REPO#123")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
