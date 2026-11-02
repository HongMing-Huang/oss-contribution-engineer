#!/usr/bin/env python3
"""v8_profile.py — profile large-repository query latency by phase.

Measures where the time actually goes before any persistence work is justified
(V8 section 7): file discovery, file read+tokenize (the Corpus walk), symbol
extraction, BM25 stats, history, PageRank, routing end-to-end, structural graph
build, symbol index build. Uses explicit timers around the real code paths plus
cProfile for the walk phase.

Usage: python3 v8_profile.py --repo work/django@8abacfc36d --out runs/profile-django.json
"""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import pstats
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "oss-contribution-engineer" / "scripts"))

import retrieval_router as rr   # noqa: E402
import symbol_backend as sb     # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--query", default="JSONField __in lookup crash for bare Value primitives")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    res: dict = {"repo": str(repo), "profiled_at": datetime.now(timezone.utc).isoformat(),
                 "phases_ms": {}}

    # 1. file discovery only
    t0 = time.monotonic()
    files = list(_discover(repo))
    res["phases_ms"]["file_discovery"] = int((time.monotonic() - t0) * 1000)
    res["file_count"] = len(files)

    # 2. full Corpus (read+tokenize+symbols+imports+bm25+history) under cProfile
    pr = cProfile.Profile()
    t1 = time.monotonic()
    pr.enable()
    corpus = rr.Corpus(repo)
    pr.disable()
    res["phases_ms"]["corpus_total"] = int((time.monotonic() - t1) * 1000)
    res["phases_ms"]["corpus_walk_ms"] = None
    # split: time a re-walk WITHOUT tokenization to approximate read cost
    t2 = time.monotonic()
    for rel, text in rr.walk(repo):
        _ = len(text)
    res["phases_ms"]["read_only"] = int((time.monotonic() - t2) * 1000)

    # 3. ranking phases
    t3 = time.monotonic()
    qtokens = rr.tokenize(args.query)
    _ = corpus.bm25(qtokens)
    res["phases_ms"]["bm25"] = int((time.monotonic() - t3) * 1000)

    t4 = time.monotonic()
    _ = rr.repomap_rank(corpus, qtokens, [args.query], {}, iterations=30)
    res["phases_ms"]["pagerank_30iter"] = int((time.monotonic() - t4) * 1000)

    # 4. route end-to-end (cold)
    t5 = time.monotonic()
    rep = rr.route(str(repo), args.query, "issue2code", None, 8, 2, 50)
    res["phases_ms"]["route_cold_total"] = int((time.monotonic() - t5) * 1000)
    res["route_latency_reported"] = rep["routing_decision"]["latency_ms"]

    # 5. structural graph build (ast parse of every python file)
    t6 = time.monotonic()
    g = sb.build_graph(repo)
    res["phases_ms"]["symbol_graph_build"] = int((time.monotonic() - t6) * 1000)
    res["graph_counts"] = g["counts"]

    # 6. symbol spans index build
    t7 = time.monotonic()
    _ = sb.build_index(repo, "python-ast")
    res["phases_ms"]["symbol_index_build"] = int((time.monotonic() - t7) * 1000)

    # top cProfile functions for the corpus phase
    s = io.StringIO()
    st = pstats.Stats(pr, stream=s).sort_stats("cumulative")
    st.print_stats(14)
    res["corpus_cprofile_top"] = s.getvalue()[-2600:]

    Path(args.out).write_text(json.dumps(res, indent=2))
    print(json.dumps({k: v for k, v in res.items()
                      if k != "corpus_cprofile_top"}, indent=2))
    return 0


def _discover(repo: Path):
    for p in sorted(repo.rglob("*")):
        rel = p.relative_to(repo)
        if any(part in rr.SKIP_DIRS or part.startswith(".") for part in rel.parts[:-1]):
            continue
        if p.is_file() and not p.name.startswith(".") and \
                p.suffix in {".py", ".go", ".rs", ".ts", ".js", ".mjs", ".cjs"}:
            yield p


if __name__ == "__main__":
    raise SystemExit(main())
