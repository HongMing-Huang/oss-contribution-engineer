#!/usr/bin/env python3
"""repo_audit.py — deterministic repository environment audit.

Detects (from files on disk only): languages, package managers, build systems, test
frameworks, CI systems, contribution/ownership/AI-instruction docs, formatters/linters,
and type checkers. Outputs JSON (--json) and a human-readable summary.

This is a collector, not an analyzer: it reports what is on disk and never infers
semantics. Read the files it surfaces.

Exit codes: 0 = audited, 2 = usage error, 3 = repository not found.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", "out", "target", "vendor", "third_party", ".tox", ".nox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "site-packages", ".next", ".nuxt",
    "coverage", ".turbo", ".cache", ".parcel-cache", "obj", "bin/obj", ".gradle",
    ".terraform", "Pods", "DerivedData", ".stack-work", "_build", "deps",
}

LANG_EXTS = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
    ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".go": "Go",
    ".rs": "Rust", ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".cxx": "C++",
    ".hpp": "C++", ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin", ".rb": "Ruby",
    ".php": "PHP", ".cs": "C#", ".swift": "Swift", ".scala": "Scala", ".sh": "Shell",
    ".bash": "Shell", ".zsh": "Shell", ".lua": "Lua", ".zig": "Zig", ".ex": "Elixir",
    ".exs": "Elixir", ".erl": "Erlang", ".hs": "Haskell", ".dart": "Dart", ".vue": "Vue",
    ".svelte": "Svelte", ".proto": "Protocol Buffers", ".sql": "SQL", ".r": "R",
    ".jl": "Julia", ".m": "Objective-C", ".mm": "Objective-C",
}

# (category, detector-name, match: fnmatch pattern against posix relpath, case-insensitive)
FILE_DETECTORS = [
    # package managers
    ("package_manager", "npm", ["package.json"]),
    ("package_manager", "pnpm", ["pnpm-lock.yaml", "pnpm-workspace.yaml"]),
    ("package_manager", "yarn", ["yarn.lock", ".yarnrc", ".yarnrc.yml"]),
    ("package_manager", "pip", ["requirements*.txt", "requirements*.in"]),
    ("package_manager", "poetry", ["poetry.lock"]),
    ("package_manager", "uv", ["uv.lock"]),
    ("package_manager", "pipenv", ["Pipfile", "Pipfile.lock"]),
    ("package_manager", "conda", ["environment.yml", "environment.yaml"]),
    ("package_manager", "cargo", ["Cargo.toml"]),
    ("package_manager", "go modules", ["go.mod"]),
    ("package_manager", "maven", ["pom.xml"]),
    ("package_manager", "gradle", ["build.gradle", "build.gradle.kts", "gradlew"]),
    ("package_manager", "bundler", ["Gemfile"]),
    ("package_manager", "composer", ["composer.json"]),
    ("package_manager", "nuget", ["*.csproj", "*.fsproj", "packages.config", "nuget.config"]),
    ("package_manager", "hex/mix", ["mix.exs"]),
    ("package_manager", "cocoapods/spm", ["Podfile", "Package.swift"]),
    # build systems
    ("build_system", "make", ["Makefile", "makefile", "GNUmakefile", "*.mk"]),
    ("build_system", "cmake", ["CMakeLists.txt", "*.cmake"]),
    ("build_system", "meson", ["meson.build"]),
    ("build_system", "bazel", ["WORKSPACE", "MODULE.bazel", "BUILD", "BUILD.bazel", ".bazelrc"]),
    ("build_system", "just", ["justfile", ".justfile"]),
    ("build_system", "cargo", ["Cargo.toml"]),
    ("build_system", "go build", ["go.mod"]),
    ("build_system", "nox", ["noxfile.py"]),
    ("build_system", "tox", ["tox.ini", "tox.toml"]),
    ("build_system", "hatch", ["hatch.toml"]),
    ("build_system", "docker", ["Dockerfile", "Dockerfile.*", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]),
    # test frameworks
    ("test_framework", "pytest", ["pytest.ini", "conftest.py", "pyproject.toml"], ),
    ("test_framework", "unittest-style tests dir", ["tests/__init__.py"]),
    ("test_framework", "tox", ["tox.ini", "tox.toml"]),
    ("test_framework", "nox", ["noxfile.py"]),
    ("test_framework", "jest", ["jest.config.js", "jest.config.ts", "jest.config.mjs", "jest.config.json"]),
    ("test_framework", "vitest", ["vitest.config.ts", "vitest.config.js", "vitest.config.mts"]),
    ("test_framework", "mocha", [".mocharc.yml", ".mocharc.json", ".mocharc.js"]),
    ("test_framework", "playwright", ["playwright.config.ts", "playwright.config.js"]),
    ("test_framework", "cypress", ["cypress.config.js", "cypress.config.ts", "cypress.json"]),
    ("test_framework", "karma", ["karma.conf.js"]),
    ("test_framework", "go test", ["go.mod"]),
    ("test_framework", "cargo test", ["Cargo.toml"]),
    ("test_framework", "junit", ["pom.xml", "build.gradle", "build.gradle.kts"]),
    ("test_framework", "rspec", [".rspec", "spec/spec_helper.rb"]),
    ("test_framework", "minitest", ["test/test_helper.rb"]),
    ("test_framework", "ctest", ["CMakeLists.txt"]),
    # CI
    ("ci", "github actions", [".github/workflows/*.yml", ".github/workflows/*.yaml"]),
    ("ci", "gitlab ci", [".gitlab-ci.yml"]),
    ("ci", "circleci", [".circleci/config.yml", ".circleci/config.yaml"]),
    ("ci", "azure pipelines", ["azure-pipelines.yml", "azure-pipelines.yaml"]),
    ("ci", "jenkins", ["Jenkinsfile"]),
    ("ci", "drone", [".drone.yml"]),
    ("ci", "woodpecker", [".woodpecker.yml", ".woodpecker/*.yml"]),
    ("ci", "travis", [".travis.yml"]),
    ("ci", "buildkite", [".buildkite/pipeline.yml", ".buildkite/pipeline.yaml"]),
    ("ci", "cirrus", [".cirrus.yml"]),
    # contribution & governance docs
    ("contribution_doc", "README", ["README*", "readme*"]),
    ("contribution_doc", "CONTRIBUTING", ["CONTRIBUTING*", "contributing*", "docs/contributing*", ".github/CONTRIBUTING*"]),
    ("contribution_doc", "CODE_OF_CONDUCT", ["CODE_OF_CONDUCT*", ".github/CODE_OF_CONDUCT*", "docs/code-of-conduct*"]),
    ("contribution_doc", "SECURITY", ["SECURITY*", "SECURITY.md", ".github/SECURITY.md", "docs/security*"]),
    ("contribution_doc", "DEVELOPMENT/HACKING", ["DEVELOPMENT*", "HACKING*", "docs/developing*", "docs/development*"]),
    ("contribution_doc", "MAINTAINERS", ["MAINTAINERS*", "MAINTAINER*", "docs/maintainers*"]),
    ("contribution_doc", "GOVERNANCE", ["GOVERNANCE*", "docs/governance*"]),
    ("contribution_doc", "RELEASING/CHANGELOG", ["RELEASING*", "CHANGELOG*", "CHANGES*", "HISTORY*", ".changeset/*", "changes/*"]),
    ("contribution_doc", "PR template", [".github/PULL_REQUEST_TEMPLATE*", ".github/pull_request_template*", "docs/pull_request_template*", ".gitea/PULL_REQUEST_TEMPLATE*"]),
    ("contribution_doc", "issue templates", [".github/ISSUE_TEMPLATE/*", ".gitea/ISSUE_TEMPLATE/*"]),
    ("contribution_doc", "changesets config", [".changeset/config.json"]),
    # ownership
    ("ownership", "CODEOWNERS", ["CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS", ".gitlab/CODEOWNERS"]),
    ("ownership", "OWNERS", ["OWNERS", ".github/OWNERS", "*/OWNERS"]),
    # AI instructions
    ("ai_instruction", "AGENTS.md", ["AGENTS.md", "agents.md", "**/AGENTS.md"]),
    ("ai_instruction", "CLAUDE.md", ["CLAUDE.md", "**/CLAUDE.md"]),
    ("ai_instruction", "GEMINI.md", ["GEMINI.md", "**/GEMINI.md"]),
    ("ai_instruction", "copilot instructions", [".github/copilot-instructions.md", ".github/instructions/*.instructions.md"]),
    ("ai_instruction", "cursor rules", [".cursorrules", ".cursor/rules/*"]),
    ("ai_instruction", "claude dir", [".claude/**"]),
    # formatters / linters
    ("formatter_linter", "prettier", [".prettierrc", ".prettierrc*", "prettier.config.js", "prettier.config.mjs", "prettier.config.cjs"]),
    ("formatter_linter", "eslint", [".eslintrc", ".eslintrc*", "eslint.config.js", "eslint.config.mjs", "eslint.config.ts"]),
    ("formatter_linter", "biome", ["biome.json", "biome.jsonc"]),
    ("formatter_linter", "ruff", ["ruff.toml", ".ruff.toml"]),
    ("formatter_linter", "black", [".black"]),
    ("formatter_linter", "flake8", [".flake8", ".flake8.ini"]),
    ("formatter_linter", "isort", [".isort.cfg"]),
    ("formatter_linter", "rustfmt", ["rustfmt.toml", ".rustfmt.toml"]),
    ("formatter_linter", "clang-format", [".clang-format"]),
    ("formatter_linter", "gofmt (implicit)", ["go.mod"]),
    ("formatter_linter", "golangci-lint", [".golangci.yml", ".golangci.yaml", ".golangci.toml"]),
    ("formatter_linter", "pre-commit", [".pre-commit-config.yaml", ".pre-commit-config.yml"]),
    ("formatter_linter", "editorconfig", [".editorconfig"]),
    ("formatter_linter", "scalafmt", [".scalafmt.conf"]),
    ("formatter_linter", "styler/rubocop", [".rubocop.yml"]),
    ("formatter_linter", "gofumpt/golint misc", [".gofumpt"]),
    # type checkers / static analysis
    ("type_checker", "mypy", ["mypy.ini", ".mypy.ini"]),
    ("type_checker", "pyright", ["pyrightconfig.json"]),
    ("type_checker", "pytype", [".pytype"]),
    ("type_checker", "typescript strict (tsconfig)", ["tsconfig.json"]),
    ("type_checker", "clippy", ["Cargo.toml"]),
    ("type_checker", "vulture/bandit config", [".bandit", "bandit.yml"]),
    ("type_checker", "semgrep", [".semgrep.yml", ".semgrepconfig"]),
    ("type_checker", "codeql", [".github/workflows/*.yml"]),
]

# manifest files worth reading for commands
MANIFEST_FILES = [
    "package.json", "pyproject.toml", "Makefile", "makefile", "GNUmakefile", "CMakeLists.txt",
    "go.mod", "Cargo.toml", "Justfile", "justfile", "noxfile.py", "tox.ini", "tox.toml",
    "pom.xml", "build.gradle", "build.gradle.kts", "Gemfile", "meson.build", "WORKSPACE",
    "MODULE.bazel", "setup.py", "setup.cfg", "Poetry.lock", "uv.lock", "flake.nix",
]


def walk_files(root: Path, max_depth: int):
    root_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        cur = Path(dirpath)
        depth = len(cur.parts) - root_depth
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        if depth >= max_depth:
            dirnames[:] = []
        for fn in sorted(filenames):
            yield cur / fn


def matches(rel: str, pattern: str) -> bool:
    if pattern.startswith("**/"):
        return fnmatch.fnmatch(rel.lower(), pattern[3:].lower()) or fnmatch.fnmatch("*/" + rel.lower(), pattern.lower())
    return fnmatch.fnmatch(rel.lower(), pattern.lower())


def _git_head(repo: Path) -> str | None:
    p = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                       capture_output=True, text=True, shell=False)
    return p.stdout.strip() if p.returncode == 0 else None


def audit(repo: Path, max_depth: int) -> dict:
    files = list(walk_files(repo, max_depth))
    findings: dict[str, dict[str, set[str]]] = {}
    for cat, name, *rest in FILE_DETECTORS:
        patterns = rest[0] if rest else []
        for pattern in patterns:
            for f in files:
                rel = f.relative_to(repo).as_posix()
                if matches(rel, pattern):
                    findings.setdefault(cat, {}).setdefault(name, set()).add(rel)
    # languages by extension
    ext_counts = Counter()
    for f in files:
        ext_counts[f.suffix.lower()] += 1
    langs = Counter()
    for ext, n in ext_counts.items():
        if ext in LANG_EXTS:
            langs[LANG_EXTS[ext]] += n
    # top-level layout hint
    top = sorted(p.name for p in repo.iterdir() if not p.name.startswith(".") or p.name in (".github", ".gitlab", ".circleci", ".claude", ".cursor"))
    # manifests present
    present_manifests = []
    for f in files:
        rel = f.relative_to(repo).as_posix()
        if rel in MANIFEST_FILES or rel.lower() in [m.lower() for m in MANIFEST_FILES]:
            present_manifests.append(rel)
    body = {
        "type": "REPOSITORY_RECON",
        "schema_version": 1,
        "repository": str(repo),
        "base_sha": _git_head(repo),
        "generated_by": "repo_audit.py",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "max_depth": max_depth,
        "languages": [{"language": k, "files": v} for k, v in langs.most_common(10)],
        "top_level_entries": top[:60],
        "findings": {cat: {name: sorted(paths) for name, paths in sorted(items.items())}
                     for cat, items in sorted(findings.items())},
        "manifests_to_read": sorted(set(present_manifests)),
        "notes": [
            "file-based detection only; read the surfaced files to confirm actual commands",
            "detection depth capped; nested monorepo docs may live deeper — run with a subdir if needed",
        ],
    }
    body["digest"] = hashlib.sha256(json.dumps(
        {k: v for k, v in body.items() if k != "digest"}, sort_keys=True).encode()).hexdigest()
    return body


def summarize(report: dict) -> str:
    lines = ["Repository audit: " + report["repository"]]
    if report["languages"]:
        lines.append("  languages: " + ", ".join(f"{l['language']}({l['files']})" for l in report["languages"][:5]))
    for cat in ("package_manager", "build_system", "test_framework", "ci", "formatter_linter", "type_checker"):
        items = report["findings"].get(cat, {})
        if items:
            lines.append(f"  {cat}: " + ", ".join(sorted(items)))
    docs = report["findings"].get("contribution_doc", {})
    if docs:
        lines.append("  contribution docs: " + ", ".join(sorted(docs)))
    ai = report["findings"].get("ai_instruction", {})
    if ai:
        lines.append("  AI INSTRUCTIONS PRESENT (read and obey): " + ", ".join(sorted(ai)))
    own = report["findings"].get("ownership", {})
    if own:
        lines.append("  ownership: " + ", ".join(sorted(own)))
    if report["manifests_to_read"]:
        lines.append("  read for commands: " + ", ".join(report["manifests_to_read"][:10]))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic repository environment audit.")
    ap.add_argument("repo", nargs="?", default=".", help="repository root (default: .)")
    ap.add_argument("--max-depth", type=int, default=3, help="directory walk depth (default 3)")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"error: {repo} is not a directory", file=sys.stderr)
        return 3
    report = audit(repo, max(1, args.max_depth))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(summarize(report))
        print("\n(--json for machine-readable output)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
