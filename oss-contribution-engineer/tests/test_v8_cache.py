#!/usr/bin/env python3
"""V8 cache acceptance tests: cold/warm/update/branch-change/corruption.

Run: python3 -m pytest tests/test_v8_cache.py -q
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import router_cache as rc            # noqa: E402
import retrieval_router as rr        # noqa: E402


def py(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/env", "python3", *args],
                          capture_output=True, text=True, shell=False)


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/env", "git", "-C", str(repo), *args],
                          capture_output=True, text=True, shell=False)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    (r / "pkg").mkdir(parents=True)
    (r / "pkg" / "alpha.py").write_text("def alpha():\n    return 1\n")
    (r / "pkg" / "beta.py").write_text("import pkg.alpha\n\n\ndef beta():\n    return alpha()\n")
    git(r, "init", "-q")
    git(r, "add", "-A")
    git(r, "commit", "-qm", "init")
    return r


def _same_ranking_state(a: rr.Corpus, b: rr.Corpus) -> None:
    assert sorted(a.files) == sorted(b.files)
    assert a.tokens.keys() == b.tokens.keys()
    for rel in a.tokens:
        assert dict(a.tokens[rel]) == dict(b.tokens[rel]), rel
        assert a.symbols[rel] == b.symbols[rel], rel
        assert sorted(a.imports[rel]) == sorted(b.imports[rel]), rel


def test_cold_then_warm_identical_ranking_state(repo):
    cold = rr.Corpus(repo)
    warm = rc.build_corpus(repo)          # first call: builds + stores cache
    _same_ranking_state(cold, warm)
    warm2 = rc.build_corpus(repo)         # second call: served from cache
    _same_ranking_state(cold, warm2)
    assert rc.cache_file(repo).exists()


def test_single_file_update_invalidates_only_that_file(repo):
    rc.build_corpus(repo)
    time.sleep(0.01)
    p = repo / "pkg" / "alpha.py"
    p.write_text("def alpha():\n    return 41\n")
    os.utime(p, ns=(time.time_ns(), time.time_ns()))  # force mtime change
    corpus = rc.build_corpus(repo)
    assert corpus.tokens["pkg/alpha.py"]          # re-read fresh, non-empty
    warm_again = rc.build_corpus(repo)
    _same_ranking_state(rr.Corpus(repo), warm_again)


def test_branch_change_invalidates_via_rewritten_mtimes(repo):
    rc.build_corpus(repo)
    git(repo, "checkout", "-q", "-b", "other")
    p = repo / "pkg" / "alpha.py"
    p.write_text("def alpha():\n    return 'branch'\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "branch")
    git(repo, "checkout", "-q", "-")
    # checkout rewrote alpha.py's mtime → cache must NOT serve stale tokens
    corpus = rc.build_corpus(repo)
    _same_ranking_state(rr.Corpus(repo), corpus)


def test_corrupt_cache_is_discarded_not_fatal(repo):
    rc.build_corpus(repo)
    rc.cache_file(repo).write_bytes(b"\x00\x01 not gzip")
    corpus = rc.build_corpus(repo)        # must rebuild cold, no exception
    _same_ranking_state(rr.Corpus(repo), corpus)


def test_route_with_cache_hook_matches_plain_route(repo):
    report_cold = rr.route(str(repo), "beta calls alpha", "issue2code", None, 8, 2, 50)
    rr.CORPUS_BUILDER = rc.build_corpus
    try:
        report_warm = rr.route(str(repo), "beta calls alpha", "issue2code", None, 8, 2, 50)
    finally:
        rr.CORPUS_BUILDER = None
    assert [c["path"] for c in report_cold["candidates"]] == \
        [c["path"] for c in report_warm["candidates"]]
