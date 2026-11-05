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
MAX_SCAN_FILES = 30_000  # real monorepos: lobe-chat carries ~23k files; a
# 4k cap stopped the walk inside apps/ and never reached packages/ (found in
# real-repo validation) — a missed consumer is a broken consumer

RE_PY = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M)
RE_JS = re.compile(r"""(?:from\s+|import\s*\(\s*|require\s*\(\s*)['"]([^'"]+)['"]""")
# re-export edge: `export * from './x'` / `export { a } from './x'` — the
# barrel's importers consume the re-exported module too (barrel semantics)
RE_JS_EXPORT = re.compile(
    r"""export\s+(?:\*(?:\s+as\s+[\w$]+)?|\{[^}]*\})\s*from\s*['"]([^'"]+)['"]""")
RE_GO = re.compile(r"^\s*(?:_\s+)?(?:\.\s+)?\"([\w./-]+)\"", re.M)

TEST_MARKERS = (".test.", ".spec.", "_test.", "/__tests__/", "/tests/")


def _collect_export_targets(base: Path, exports) -> list[str]:
    """Flatten a package.json `exports` value into repo-relative candidate
    paths (string or nested conditions-dict; both may appear)."""
    out: list[str] = []
    if isinstance(exports, str):
        out.append(exports)
    elif isinstance(exports, dict):
        for v in exports.values():
            out.extend(_collect_export_targets(base, v))
    elif isinstance(exports, list):
        for v in exports:
            out.extend(_collect_export_targets(base, v))
    return out


def build_resolution(repo: Path) -> tuple[dict, list]:
    """Precise import resolution for monorepos: workspace package names via
    package.json `exports`/`main`, and tsconfig path aliases. Real-repo
    validation on lobe-chat found the two dominant internal import forms are
    `@scope/pkg/subpath` and `@/alias` — bare tail-matching alone missed
    them, and a missed consumer is a broken consumer."""
    pkg_map: dict = {}   # "name" or "name/sub" -> repo-relative file/dir
    for pj in list(repo.glob("packages/*/package.json")) + \
            list(repo.glob("package.json")):
        try:
            data = json.loads(pj.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        name = data.get("name")
        if not name or not isinstance(name, str):
            continue
        base = pj.parent
        exports = data.get("exports")
        if isinstance(exports, dict):
            for key, val in exports.items():
                sub = key.lstrip("./")  # "./server" -> "server"
                for t in _collect_export_targets(base, val):
                    p = (base / t).resolve()
                    try:
                        rel = p.relative_to(repo).as_posix()
                    except ValueError:
                        continue
                    pkg_map.setdefault(name + ("/" + sub if sub and sub != "." else ""), rel)
        else:
            for field in ("main", "module", "types"):
                t = data.get(field)
                if isinstance(t, str):
                    p = (base / t).resolve()
                    try:
                        pkg_map.setdefault(name, p.relative_to(repo).as_posix())
                        break
                    except ValueError:
                        continue
    aliases: list = []  # (prefix, replacement) pairs from tsconfig paths
    for ts in [repo / "tsconfig.json", *repo.glob("*/tsconfig.json"),
               *repo.glob("packages/*/tsconfig.json"),
               *repo.glob("apps/*/tsconfig.json")]:
        try:
            data = json.loads(ts.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        paths = ((data.get("compilerOptions") or {}).get("paths")) or {}
        if not isinstance(paths, dict):
            continue
        base_dir = ts.parent
        for prefix, targets in paths.items():
            if not isinstance(targets, list) or not targets or \
                    not isinstance(targets[0], str):
                continue
            t = (base_dir / targets[0]).resolve()
            try:
                aliases.append((prefix, t.relative_to(repo).as_posix()))
            except ValueError:
                continue
    return pkg_map, aliases


def _resolve_spec(spec: str, importer_rel: str, pkg_map: dict,
                  aliases: list) -> str | None:
    """Import specifier -> repo-relative target path (no extension yet).
    Order: package exports map, tsconfig alias, relative."""
    if not spec.startswith("."):
        # exact package or package/subpath
        if spec in pkg_map:
            return pkg_map[spec]
        root = spec.split("/", 1)[0]
        if root in pkg_map and "/" in spec:
            sub = spec.split("/", 1)[1]
            base = pkg_map[root]
            # base may be the package entry; subpath extends the package dir
            pkg_dir = base.rsplit("/src/", 1)[0] if "/src/" in base else base
            return (pkg_dir + "/" + sub) if not sub.endswith((".ts", ".js")) \
                else (pkg_dir + "/" + sub)
        for prefix, target in aliases:
            if prefix.endswith("/*") and spec.startswith(prefix[:-1]):
                # replace the star: '@/const/trace' + '@/const/*'->'pkg/src/*'
                # must yield 'pkg/src/trace', not 'pkg/src/*/trace' (harness
                # caught every alias-subpath consumer missing)
                return target[:-1] + spec[len(prefix) - 1:]
            if spec == prefix:
                return target
        return None
    base_dir = importer_rel.rsplit("/", 1)[0] if "/" in importer_rel else ""
    cand = (base_dir + "/" + spec) if base_dir else spec
    norm = []
    for s in cand.split("/"):
        if s == ".." and norm:
            norm.pop()
        elif s not in (".", ""):
            norm.append(s)
    return "/".join(norm)


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


def extract_imports(path: Path) -> tuple[list[str], list[str]]:
    """(usage_specs, reexport_specs) — usage imports consume the target;
    re-export edges propagate consumption transitively (barrel files)."""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return [], []
    usage: list[str] = []
    reexport: list[str] = []
    if path.suffix == ".py":
        for m in RE_PY.finditer(text):
            usage.append((m.group(1) or m.group(2) or "").split(".")[0])
    elif path.suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
        reexport = RE_JS_EXPORT.findall(text)
        usage = [s for s in RE_JS.findall(text) if s not in reexport]
    elif path.suffix == ".go":
        usage = RE_GO.findall(text)
    return [s for s in usage if s], [s for s in reexport if s]


def find_consumers(repo: Path, changed: list[str]) -> dict:
    """Returns {'consumers': {changed: [...]}, 'barrels': {barrel: [changed...]}}.
    Direct consumers (their import resolves to the changed file itself) need
    individual verdicts; barrel-mediated consumers (they import a package
    root/index that re-exports the changed file) are reported with their via
    — file-level semantics over a popular barrel lists hundreds of files, so
    the BARREL carries the verdict instead of every importer."""
    pkg_map, aliases = build_resolution(repo)
    changed_set = set(changed)

    # pass 1: collect repo files and their import specs
    repo_files: set[str] = set()
    specs_by_file: dict[str, tuple[list, list]] = {}
    scanned = 0
    truncated = False
    for dirpath, dirnames, filenames in _walk(repo):
        for fn in filenames:
            f = Path(dirpath) / fn
            if f.suffix not in SCAN_EXTS:
                continue
            scanned += 1
            if scanned > MAX_SCAN_FILES:
                truncated = True
                break
            try:
                if f.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            rel = f.relative_to(repo).as_posix()
            repo_files.add(rel)
            specs_by_file[rel] = extract_imports(f)

    noext_all: dict[str, str] = {}
    for r in repo_files:
        stem = r
        for ext in (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
            if r.endswith(ext):
                stem = r[: -len(ext)]
                break
        noext_all[stem] = r

    def resolve_to_file(spec: str, rel: str) -> str | None:
        target = _resolve_spec(spec, rel, pkg_map, aliases)
        if not target:
            return None
        if target in repo_files:
            return target
        if target in noext_all:
            return noext_all[target]
        for e in (".ts", ".tsx", ".js", ".jsx",
                  "/index.ts", "/index.tsx", "/index.js"):
            if target + e in repo_files:
                return target + e
        return None

    def tail_fallback(spec: str) -> str | None:
        """Two-segment tail match against CHANGED files only — kills the
        one-segment false positive ('@/types/trace' is a different file than
        packages/const/src/trace.ts) while still catching Go module paths."""
        spec_tail = spec.split("/")[-2:]
        if len(spec_tail) < 2:
            return None
        for c in changed:
            if c.split("/")[-2:] == spec_tail or \
                    c.rsplit(".", 1)[0].split("/")[-2:] == spec_tail:
                return c
        return None

    # pass 2: build edges over ALL repo files
    usage_edges: dict[str, set[str]] = {}
    reexport_edges: dict[str, set[str]] = {}
    spec_of: dict[tuple, str] = {}
    for rel, (usage_specs, reexport_specs) in specs_by_file.items():
        for spec in reexport_specs:
            t = resolve_to_file(spec, rel)
            if t and t != rel:
                reexport_edges.setdefault(rel, set()).add(t)
        for spec in usage_specs:
            t = resolve_to_file(spec, rel)
            if t is None and not spec.startswith("."):
                t = tail_fallback(spec)
            if t and t != rel:
                usage_edges.setdefault(rel, set()).add(t)
                spec_of[(rel, t)] = spec

    # barrels exposing changed files (bounded fixpoint)
    exposes: dict[str, set[str]] = {c: {c} for c in changed}
    for _ in range(6):
        grew = False
        for b, tgts in reexport_edges.items():
            cur = exposes.setdefault(b, set())
            for t in tgts:
                for c in exposes.get(t, ()):
                    if c not in cur:
                        cur.add(c)
                        grew = True
        if not grew:
            break
    barrels = {b: sorted(cs) for b, cs in exposes.items()
               if b not in changed_set and cs & changed_set}

    consumers: dict[str, list[dict]] = {c: [] for c in changed}
    for f in sorted(usage_edges):
        is_test = any(m in f for m in TEST_MARKERS) or "/test" in f
        hits: dict[str, dict] = {}
        for t in sorted(usage_edges[f]):
            for c in exposes.get(t, ()):
                if c not in hits:
                    hits[c] = {"path": f, "via": spec_of.get((f, t), ""),
                               "direct": t == c,
                               "via_barrel": t if t != c else None,
                               "kind": "test" if is_test else "production"}
        for c, entry in sorted(hits.items()):
            consumers[c].append(entry)
    return {"consumers": consumers, "barrels": barrels,
            "scanned_files": scanned, "scan_truncated": truncated}


def _walk(repo: Path):
    import os
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        yield dirpath, dirnames, filenames


def _digest(artifact: dict) -> str:
    # digest covers the MEASUREMENT, not the wall clock — created_at excluded
    # so the same scan of the same tree yields the same digest (found by the
    # harness determinism test)
    return hashlib.sha256(json.dumps(
        {k: v for k, v in artifact.items() if k not in ("digest", "created_at")},
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


def _verdict_targets(artifact: dict) -> set:
    """Files needing verdicts: DIRECT consumers (their import resolves to the
    changed file) plus every BARREL that re-exports a changed file (its
    verdict covers the indirect importers — hundreds on a popular package
    root; each one getting a sentence would make the gate unusable)."""
    targets = {c["path"] for cs in artifact["consumers"].values()
               for c in cs if c.get("direct")}
    targets |= set(artifact.get("barrels") or {})
    return targets


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--base", default="HEAD",
                    help="diff base (default HEAD — the working tree vs HEAD)")
    ap.add_argument("--verdict", action="append", default=[],
                    metavar="PATH::VERDICT",
                    help="record a verdict sentence for one direct consumer "
                         "or barrel (repeatable); the sentence is auditable "
                         "evidence")
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
        listed = _verdict_targets(artifact)
        for v in args.verdict:
            if "::" not in v:
                print("error: --verdict expects PATH::verdict (got %r)" % v,
                      file=sys.stderr)
                return 2
            path, text = v.split("::", 1)
            path, text = path.strip(), text.strip()
            if path not in listed:
                print("error: %s is not a verdict target (direct consumers "
                      "and barrels: %s)" % (path, ", ".join(sorted(listed))
                                            or "none"),
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
        outstanding = sorted(_verdict_targets(artifact)
                             - set(artifact["verdicts"]))
        if outstanding:
            print("still outstanding: %s" % ", ".join(outstanding))
            return 1
        print("RESULT         CONSUMER IMPACT COMPLETE")
        return 0

    res = find_consumers(repo, changed)
    consumers, barrels = res["consumers"], res["barrels"]
    if res.get("scan_truncated"):
        print("warning: scan stopped at %d files (MAX_SCAN_FILES) — the "
              "consumer list may be INCOMPLETE; raise the cap or split the "
              "repo scan" % MAX_SCAN_FILES, file=sys.stderr)
    artifact = {
        "type": "CONSUMER_IMPACT",
        "schema_version": 1,
        "repository": _identity(repo),
        "base": args.base,
        "git_head": head.strip(),
        "changed_production_files": changed,
        "consumers": consumers,
        "barrels": barrels,
        "scanned_files": res.get("scanned_files"),
        "scan_truncated": res.get("scan_truncated", False),
        "verdicts": {},
        "method": "lexical import scan (python/js/ts/go) with precise "
                  "resolution: workspace package.json exports, tsconfig path "
                  "aliases, relative paths, barrel re-export propagation, "
                  "two-segment tail-match fallback. Heuristic, not semantic "
                  "— LSP-verified references are a stronger future method; "
                  "unmapped import styles remain a known blind spot. Direct "
                  "consumers and barrels need verdicts; barrel-mediated "
                  "importers are covered by the barrel's verdict.",
        "generated_by": "consumer_impact.py",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    artifact["digest"] = _digest(artifact)
    artifact_path.write_text(json.dumps(artifact, indent=2))

    total = sum(len(v) for v in consumers.values())
    print("CONSUMER_IMPACT written: %s" % artifact_path)
    print("changed production files: %d; consumers found: %d "
          "(direct: %d, via barrels: %d)"
          % (len(changed), total,
             sum(1 for cs in consumers.values() for c in cs if c["direct"]),
             sum(1 for cs in consumers.values() for c in cs if not c["direct"])))
    for c, cs in consumers.items():
        for con in cs:
            if con["direct"]:
                print("  %-42s <- %-11s %s" % (c[:42], con["kind"], con["path"]))
    for b, exposed in barrels.items():
        n = sum(1 for cs in consumers.values() for c in cs
                if c.get("via_barrel") == b)
        print("  barrel %s re-exports %s (covers %d indirect importers)"
              % (b, ", ".join(exposed), n))
    targets = _verdict_targets(artifact)
    if total == 0:
        print("RESULT         NO CONSUMERS FOUND (lexical scan) — say so in "
              "the review rather than claiming 'no impact'")
        return 0
    print("next: verdict each DIRECT consumer and each BARREL —")
    print('  consumer_impact.py %s --verdict "path::why safe / how verified"'
          % repo)
    print("(%d verdict target(s): %s)" % (len(targets),
                                          ", ".join(sorted(targets))))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
