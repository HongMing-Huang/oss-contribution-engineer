#!/usr/bin/env python3
"""test_real_repo_probes.py — Layer D of the standardized dig-out process:
gold-labeled probes against a REAL repository (lobehub/lobe-chat, shallow
blobless clone, cached under /tmp). Skips with a reason when offline, so CI
runs the always-on layers (test_real_world_harness.py) and any machine with
network digs here.

Gold labels come from the 2026-11-03 manual validation round and are
deliberately RANGES/SETS, not point values, so upstream drift between probe
runs degrades gracefully: a gold violation means the SKILL regressed (or the
repo changed shape enough to re-label — either way, a human looks).

Run: python3 -m pytest tests/test_real_repo_probes.py -q
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
CACHE = Path("/tmp/oss-skill-e2e")
REPO_URL = "https://github.com/lobehub/lobe-chat"
REPO_DIR = CACHE / "lobe-chat"
TRACE = "packages/const/src/trace.ts"


def py(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/env", "python3", *args],
                          capture_output=True, text=True, shell=False)


@pytest.fixture(scope="module")
def lobe() -> Path:
    if REPO_DIR.exists() and (REPO_DIR / ".git").exists():
        return REPO_DIR
    REPO_DIR.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["git", "clone", "--filter=blob:none", "--depth", "1",
         REPO_URL, str(REPO_DIR)],
        capture_output=True, text=True, shell=False)
    if r.returncode != 0:
        pytest.skip("offline or clone failed: %s" % r.stderr.strip()[:120])
    return REPO_DIR


def test_rules_tiering_on_real_repo(lobe):
    r = py(str(SCRIPTS / "contribution_rules_scan.py"),
           "binding-manifest", str(lobe))
    assert r.returncode == 0, r.stderr
    man = json.loads(r.stdout)
    binding = {b["path"] for b in man["binding"]}
    kinds = {d["path"]: d["kind"] for d in man["discovered"]}
    # gold: real rules ARE binding
    for must in ("CONTRIBUTING.md", "AGENTS.md", "SECURITY.md",
                 ".github/PULL_REQUEST_TEMPLATE.md"):
        assert must in binding, "real rule %s no longer binding" % must
    # gold: reference/noise stays out of the binding gate
    assert "README.md" not in binding and kinds.get("README.md") == "reference_doc"
    assert len(binding) <= 30, "binding set ballooned again (tiering regressed)"
    assert sum(1 for k in kinds.values() if k == "reference_doc") >= 20


def test_consumer_impact_on_real_import_graph(lobe):
    trace = lobe / TRACE
    original = trace.read_text()
    try:
        trace.write_text(original + "// probe edit (harness; never committed)\n")
        t0 = time.monotonic()
        r = py(str(SCRIPTS / "consumer_impact.py"), str(lobe), "--base", "HEAD")
        dt = time.monotonic() - t0
        art = json.loads((lobe / ".oss-contrib-evidence" /
                          "consumer-impact.json").read_text())
        entries = art["consumers"].get(TRACE, [])
        # gold: the barrel-mediated fan-out is REAL and large
        assert len(entries) >= 400, "consumer recall collapsed: %d" % len(entries)
        assert "packages/const/src/index.ts" in art["barrels"]
        # gold: the twin false-positive class stays dead
        assert all(c.get("via") != "@/types/trace" for c in entries), \
            "same-name tail collision regressed"
        assert art["scan_truncated"] is False
        assert dt < 60, "23k-file scan took %.1fs (>60s gold bound)" % dt
    finally:
        trace.write_text(original)
        shutil.rmtree(lobe / ".oss-contrib-evidence", ignore_errors=True)
