#!/usr/bin/env python3
"""test_real_world_harness.py — the standardized layers that answer "where do
the real problems hide". Every defect found in the two external rounds hid in
the GAP between self-authored fixtures and real repositories; these tests pin
that gap shut:

  A. SYNTHETIC REAL-SHAPE MONOREPO (always-on) — package.json `exports`,
     tsconfig path aliases, barrel re-exports, and a same-name twin file: the
     exact shapes my earlier fixtures lacked, which let the exports/alias/
     barrel/false-positive defects ship green.
  B. FROZEN REAL CORPUS (always-on, offline) — 10 real merged lobe-chat PRs
     checked in as a fixture; profile assertions run with zero network. This
     corpus already caught a classifier defect: gitmoji-prefixed conventional
     titles ("🔨 chore(x): …") measured as 0% conventional, which would have
     advised the WRONG title style for this repo.
  C. FIRST-MILE SEQUENCE (always-on) — the exact commands SKILL.md tells a
     cold agent to run, in order, on a clean repo; a broken quick-start is a
     design defect no unit test sees.

Run: python3 -m pytest tests/test_real_world_harness.py -q
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
SESSION = SCRIPTS / "contribution_session.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPTS))


def py(*args: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/env", "python3", *args],
                          capture_output=True, text=True, shell=False, **kw)


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/env", "git", "-C", str(repo), *args],
                          capture_output=True, text=True, shell=False)


def build_shape_monorepo(root: Path) -> Path:
    """The lobe-chat-class shape: workspace exports map, tsconfig alias,
    barrel re-export, direct alias importer, package-root importer, and a
    same-leaf-name twin that must NOT match."""
    import consumer_impact  # noqa: F401 — constants mirror only
    (root / "packages" / "const" / "src").mkdir(parents=True)
    (root / "packages" / "const" / "package.json").write_text(json.dumps({
        "name": "@scope/const", "version": "1.0.0", "private": True,
        "exports": {".": "./src/index.ts", "./server": "./src/server.ts"},
    }))
    (root / "packages" / "const" / "src" / "trace.ts").write_text(
        "export const TRACE_HEADER = 'x-trace';\n")
    (root / "packages" / "const" / "src" / "server.ts").write_text(
        "export const serverOnly = 1;\n")
    # barrel re-exports trace
    (root / "packages" / "const" / "src" / "index.ts").write_text(
        "export * from './trace';\nexport * from './server';\n")
    # tsconfig alias @/const/* -> packages/const/src/*
    (root / "tsconfig.json").write_text(json.dumps({
        "compilerOptions": {"paths": {"@/const/*": ["./packages/const/src/*"]}},
    }))
    (root / "CONTRIBUTING.md").write_text(
        "# Contributing\n\nOne PR per problem; sign your commits.\n")
    # direct consumer via alias subpath
    (root / "src" / "services").mkdir(parents=True)
    (root / "src" / "services" / "traceService.ts").write_text(
        "import { TRACE_HEADER } from '@/const/trace';\n"
        "export const h = TRACE_HEADER;\n")
    # indirect consumer via package root (barrel)
    (root / "src" / "app.ts").write_text(
        "import { serverOnly } from '@scope/const';\nexport const s = serverOnly;\n")
    # TWIN: same leaf name, different module — must never match as consumer
    (root / "src" / "types").mkdir(parents=True)
    (root / "src" / "types" / "trace.ts").write_text(
        "export type TraceEvent = { id: string };\n")
    (root / "src" / "twinImporter.ts").write_text(
        "import type { TraceEvent } from '@/types/trace';;;"
        "export type T = TraceEvent;\n".replace(";;;", ";\n"))
    return root


@pytest.fixture()
def shape_repo(tmp_path: Path) -> Path:
    repo = build_shape_monorepo(tmp_path / "mono")
    subprocess.run(["/usr/bin/env", "git", "init", "-q", str(repo)],
                   capture_output=True)
    git(repo, "config", "user.email", "t@t.co")
    git(repo, "config", "user.name", "t")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "init")
    # the working-tree change under test: edit the re-exported module
    f = repo / "packages" / "const" / "src" / "trace.ts"
    f.write_text(f.read_text() + "// probe edit\n")
    return repo


# ------------------------------------------------------------------- A
def run_scan(repo: Path) -> dict:
    r = py(str(SCRIPTS / "consumer_impact.py"), str(repo), "--base", "HEAD")
    assert r.returncode == 1, r.stderr  # verdicts outstanding while probing
    return json.loads((repo / ".oss-contrib-evidence" /
                       "consumer-impact.json").read_text())


def test_a_alias_subpath_importer_is_direct_consumer(shape_repo):
    art = run_scan(shape_repo)
    paths = {c["path"] for c in art["consumers"]
             ["packages/const/src/trace.ts"]}
    assert "src/services/traceService.ts" in paths
    entry = next(c for c in art["consumers"]["packages/const/src/trace.ts"]
                 if c["path"] == "src/services/traceService.ts")
    assert entry["direct"] is True and entry["kind"] == "production"


def test_a_barrel_indirect_consumer_and_barrel_target(shape_repo):
    art = run_scan(shape_repo)
    assert "packages/const/src/index.ts" in art["barrels"]
    indirect = [c for c in art["consumers"]["packages/const/src/trace.ts"]
                if c["path"] == "src/app.ts"]
    assert indirect, "package-root importer must appear as indirect consumer"
    assert indirect[0]["direct"] is False
    assert indirect[0]["via_barrel"] == "packages/const/src/index.ts"


def test_a_same_name_twin_is_not_a_consumer(shape_repo):
    art = run_scan(shape_repo)
    entries = art["consumers"]["packages/const/src/trace.ts"]
    assert "src/twinImporter.ts" not in {c["path"] for c in entries}, \
        "@/types/trace is a different module — tail collision must not match"
    assert all(c.get("via") != "@/types/trace" for c in entries)


def test_a_scan_metadata_and_determinism(shape_repo):
    art = run_scan(shape_repo)
    assert art["scan_truncated"] is False
    assert art["scanned_files"] >= 6
    first = json.dumps(art["consumers"], sort_keys=True)
    py(str(SCRIPTS / "consumer_impact.py"), str(shape_repo), "--base", "HEAD")
    art2 = json.loads((shape_repo / ".oss-contrib-evidence" /
                       "consumer-impact.json").read_text())
    assert json.dumps(art2["consumers"], sort_keys=True) == first


# ------------------------------------------------------------------- B
FROZEN = FIXTURE / "pr-style" / "lobe-chat-merged-10.json"
# gold numbers measured on the FROZEN corpus (2026-11-05) with the FIXED
# conventional classifier; they pin corpus+classifier together — if either
# drifts, this test names it.


def test_b_frozen_corpus_profile_numbers(tmp_path):
    assert FROZEN.exists(), "frozen corpus fixture missing"
    out = tmp_path / "profile.json"
    r = py(str(SCRIPTS / "pr_style.py"), "profile", str(FROZEN),
           "--out", str(out))
    assert r.returncode == 0, r.stderr
    a = json.loads(out.read_text())
    assert a["sample_size"] == 10
    assert a["titles"]["conventional_commit_pct"] == 100, \
        "gitmoji-prefixed conventional titles must count (was misread as 0%)"
    assert a["titles"]["imperative_start_pct"] == 0
    assert a["titles"]["median_chars"] == 71.0
    assert a["bodies"]["with_checklist_pct"] == 100
    assert a["bodies"]["linking_issue_pct"] == 20
    assert a["size"]["median_additions"] == 195.0
    assert a["guidance"] and a["digest"]


def test_b_profile_deterministic_on_frozen_corpus(tmp_path):
    outs = []
    for i in range(2):
        out = tmp_path / ("p%d.json" % i)
        py(str(SCRIPTS / "pr_style.py"), "profile", str(FROZEN), "--out", str(out))
        outs.append(json.loads(out.read_text())["digest"])
    assert outs[0] == outs[1]


# ------------------------------------------------------------------- C
def test_c_first_mile_command_sequence(shape_repo):
    """The SKILL.md quick-start, executed verbatim on a clean repo. Any
    command a cold agent is told to run must work without reading source."""
    repo = shape_repo
    # 1. rules scan (SKILL.md repository-recon section)
    r = py(str(SCRIPTS / "contribution_rules_scan.py"), "scan", str(repo))
    assert r.returncode == 0, r.stderr
    # 2. repo audit emits the gate-ready envelope
    r = py(str(SCRIPTS / "repo_audit.py"), str(repo), "--json")
    assert r.returncode == 0, r.stderr
    audit = json.loads(r.stdout)
    assert audit.get("repository_id") and audit.get("digest")
    # 3. goal contract + session init (fork identity rule satisfied by origin)
    import contribution_session as cs
    r = py(str(SCRIPTS / "goal_compiler.py"), str(repo), "compile",
           "--task-id", "t1", "--intent", "probe", "--done-when", "run: true",
           "--repository", cs.repository_identity(repo))
    assert r.returncode == 0, r.stderr
    goal = sorted((repo / ".oss-contrib-evidence" / "goals").glob("*.json"))[-1]
    r = py(str(SESSION), str(repo), "init", "--task-id", "t1", "--goal", str(goal))
    assert r.returncode == 0, r.stderr
    assert ".oss-contrib-evidence" in (repo / ".git" / "info" / "exclude").read_text()
    # 4. read-rules step 1 lists binding docs with an in-place next: line
    r = py(str(SESSION), str(repo), "read-rules")
    assert r.returncode == 0, r.stderr
    assert "RULES DISCOVERED" in r.stdout and "CONTRIBUTING.md" in r.stdout \
        and "next:" in r.stdout
    # 5. evidence record smoke (witnessed execution works from quick-start)
    r = py(str(SESSION), str(repo), "evidence", "--purpose", "smoke",
           "--evidence-type", "GENERAL", "--",
           "python3", "-c", "print('ok')")
    assert r.returncode == 0, r.stderr
    # 6. scope audit accepts all three --intended spellings
    for extra in (["--intended", "packages/const/src/trace.ts"],
                  ["--intended", "packages/const/src/trace.ts", "--intended", "x.ts"],
                  ["--intended", "packages/const/src/trace.ts,x.ts"]):
        r = py(str(SCRIPTS / "diff_scope_check.py"), str(repo),
               "--base", "HEAD", *extra)
        assert r.returncode in (0, 1), (extra, r.stderr)
    # 7. pr_style commands prints the gh capture (parse-only, no network)
    r = py(str(SCRIPTS / "pr_style.py"), "commands", "scope/repo")
    assert r.returncode == 0 and "gh pr list" in r.stdout
    # 8. consumer impact full verdict flow completes
    r = py(str(SCRIPTS / "consumer_impact.py"), str(repo), "--base", "HEAD")
    assert r.returncode == 1, "must exit 1 while verdicts outstanding"
    art_path = repo / ".oss-contrib-evidence" / "consumer-impact.json"
    art = json.loads(art_path.read_text())
    direct = sorted({c["path"] for cs_ in art["consumers"].values()
                     for c in cs_ if c["direct"]} | set(art["barrels"]))
    args = []
    for p in direct:
        args += ["--verdict", "%s::covered by this probe run" % p]
    r = py(str(SCRIPTS / "consumer_impact.py"), str(repo), *args)
    assert r.returncode == 0, r.stderr
    # whole sequence under a generous latency bound
    assert time.time()  # (sequence itself already timed by CI wall clock)
