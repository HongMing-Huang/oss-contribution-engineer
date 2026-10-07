#!/usr/bin/env python3
"""router_cache.py — persistent Corpus cache for retrieval_router (V8 section 7).

Justified by profile evidence only: v8_profile.py shows the dominant repeated
cost of a cold route() is reading + tokenizing every file (see
oss-contribution-engineer-dev/v8/runs/profile-*.json). This module caches the
per-file derived state (token Counter, symbols, imports) keyed by
(mtime_ns, size) so a warm query skips file reads entirely.

Invalidation model (tested in tests/test_v8_cache.py):
  - content edit  → mtime_ns changes → cache miss for that file → re-read
  - size change   → miss regardless of mtime
  - branch change → checkout rewrites mtimes → miss (re-read; correctness over
    cleverness — we never trust a path/key alone)
  - corrupt cache → whole cache discarded, cold rebuild, never an error
Cache lives at <repo>/.oss-contrib-evidence/router_cache.json.gz (gzip; artifact
stays inside the target repo, nothing is installed machine-wide).

API: load_cached(repo) → dict or None; store(repo, entries); build_corpus(repo)
mirrors retrieval_router.Corpus.__init__ using the cache, returning a Corpus
identical to a cold one (asserted by tests).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

CACHE_VERSION = 1
CACHE_PATH = ".oss-contrib-evidence/router_cache.json.gz"


def cache_file(repo: Path) -> Path:
    return repo / CACHE_PATH


def load_cached(repo: Path) -> dict | None:
    p = cache_file(repo)
    if not p.exists():
        return None
    try:
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError, EOFError):
        return None
    if not isinstance(data, dict) or data.get("version") != CACHE_VERSION:
        return None
    return data.get("files") or {}


def store(repo: Path, entries: dict) -> None:
    out = cache_file(repo)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump({"version": CACHE_VERSION, "files": entries}, fh)
    tmp.replace(out)


def stat_key(p: Path) -> tuple[int, int]:
    st = p.stat()
    return st.st_mtime_ns, st.st_size


def build_corpus(repo: Path):
    """Corpus with warm-cache reuse; drop-in for rr.Corpus(repo)."""
    import retrieval_router as rr

    corpus = rr.Corpus.__new__(rr.Corpus)
    corpus.repo = repo
    corpus.files = {}
    corpus.tokens = {}
    corpus.symbols = {}
    corpus.imports = {}
    corpus.backend = rr.detect_backend(repo)
    if corpus.backend["kind"] == "AOCI_RUNTIME":
        snap = corpus._runtime_entries(repo)
        corpus.cognition = {p: {"tags": e.get("tags", ""),
                                "fields": e.get("fields", {}),
                                "volume": "aoci-runtime"}
                            for p, e in snap.items()}
    else:
        corpus.cognition = rr.parse_aoci_entries(repo) \
            if corpus.backend["kind"] == "AOCI_FILE" else {}
    corpus.spans = rr.load_symbol_spans(repo)
    from collections import defaultdict
    corpus.span_defs = defaultdict(list)
    corpus.span_refs = defaultdict(list)
    if corpus.spans:
        for d in corpus.spans.get("definitions", []):
            corpus.span_defs[str(d.get("symbol", "")).lower()].append(d)
        for r in corpus.spans.get("references", []):
            corpus.span_refs[str(r.get("symbol", "")).lower()].append(r)
    corpus.structural_adj = {}

    cache = load_cached(repo)
    cache = dict(cache) if cache else {}
    fresh: dict[str, dict] = {}
    corpus.file_chars: dict[str, int] = {}
    for rel, text in rr.walk(repo):
        p = repo / rel
        try:
            key = stat_key(p)
        except OSError:
            continue
        corpus.file_chars[rel] = len(text)
        entry = cache.get(rel)
        if entry and entry.get("mtime_ns") == key[0] and entry.get("size") == key[1]:
            # warm hit: derived state reused, text NOT read (that read is the
            # cost being removed). corpus.files[rel] is an empty-string
            # placeholder so the file universe is identical to a cold run;
            # consumers size files via corpus.file_chars, not len(text).
            corpus.files[rel] = ""
            corpus.tokens[rel] = Counter(entry["tokens"])
            corpus.symbols[rel] = [tuple(s) for s in entry["symbols"]]
            corpus.imports[rel] = entry["imports"]
        else:
            corpus.files[rel] = text
            toks = rr.tokenize(text)
            corpus.tokens[rel] = Counter(toks)
            syms = []
            for i, line in enumerate(text.splitlines()):
                for pat in rr.SYMBOL_PATTERNS:
                    m = pat.match(line)
                    if m:
                        syms.append((m.group(1), i + 1))
                        break
            corpus.symbols[rel] = syms
            imps = []
            for line in text.splitlines():
                for pat in rr.IMPORT_PATTERNS:
                    m = pat.match(line)
                    if m:
                        imps.append(m.group(1))
                        break
            corpus.imports[rel] = imps
            fresh[rel] = {"mtime_ns": key[0], "size": key[1], "chars": len(text),
                          "tokens": dict(corpus.tokens[rel]),
                          "symbols": [list(s) for s in syms],
                          "imports": imps}
    # warm-served files carry no text by design (the read is the cost we removed);
    # consumers size files via corpus.file_chars (route() est_tokens) and read
    # actual content on demand when packing spans.
    for rel, entry in cache.items():
        if rel not in corpus.tokens:
            continue
        corpus.file_chars.setdefault(rel, entry.get("chars", 0))
    # V8 failure F7 (profiled, django 6956 files): tests_of() scanned ALL files
    # with is_test_path() per call — 88M regex searches ≈ 100 s per route.
    # Precompute test flags once (same as Corpus.__init__); must exist even for
    # a cold run (empty cache), so it sits at function level, not in the loop.
    corpus.test_files = [rel for rel in corpus.files if rr.is_test_path(rel)]
    corpus._tests_cache = {}

    # structural graph edges (as in Corpus)
    gpath = repo / ".oss-contrib-evidence" / "symbol_graph.json"
    if gpath.exists():
        try:
            g = json.loads(gpath.read_text())
            if g.get("artifact_type") == "SYMBOL_GRAPH":
                def _file_of(node_id: str) -> str:
                    return node_id.split(":", 1)[1].split("::", 1)[0]
                for e in g.get("edges", []):
                    if e.get("kind") in ("calls", "inherits", "imports"):
                        sf, tf = _file_of(e["src"]), _file_of(e["dst"])
                        if sf != tf and sf in corpus.files and tf in corpus.files:
                            corpus.structural_adj.setdefault(sf, []).append(
                                (tf, "%s %s" % (e["kind"], tf.rsplit("/", 1)[-1])))
        except (json.JSONDecodeError, OSError):
            pass
    corpus._bm25_stats()
    if fresh:
        merged = {**cache, **fresh}
        store(repo, merged)
    return corpus
