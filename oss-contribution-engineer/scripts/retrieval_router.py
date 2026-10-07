#!/usr/bin/env python3
"""retrieval_router.py — Adaptive Repository Context Acquisition (hybrid retrieval).

Finds candidate files an agent needs for a task WITHOUT loading the repository into
context. Combines independent signal families, routes by task type, fuses with RRF,
expands through a bounded priority-queue graph, and is allowed to return nothing
(NO_RELEVANT_LOCAL_CONTEXT report). Deterministic, stdlib-only, zero network.

Signal families: lexical (BM25) · path · symbol · test-relations · history (git) ·
cognition (AOCI volumes if present and aligned, else this skill's persisted profile) ·
graph expansion. No family is authoritative; ranking is ordering evidence, never a
calibrated probability (Agent Retrieval Bench: top-score abstention thresholds do not
transfer across corpora — abstention is reported with factors, not pseudo-probabilities).

Exit codes: 0 ok, 2 usage, 3 repo error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

SKIP_DIRS = {
    ".git", ".hg", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    "out", "target", "vendor", "third_party", ".tox", ".nox", ".mypy_cache",
    ".pytest_cache", "site-packages", ".next", "coverage", "_build", "deps",
    ".oss-contrib-evidence", ".aoci", ".mimosa", ".idea", ".vscode",
}
MAX_FILE_BYTES = 300_000
MAX_FILES = 8000
K1, B = 1.5, 0.75          # BM25
RRF_K = 60.0

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def split_identifier(tok: str) -> list[str]:
    parts = re.split(r"[_\-]+", tok) if ("_" in tok or "-" in tok) else [tok]
    out = []
    for p in parts:
        chunks = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z][a-z]*|[a-z]+|\d+", p)
        out.extend(c for c in chunks if len(c) >= 3)
    return out


def tokenize(text: str) -> list[str]:
    toks = []
    for raw in TOKEN_RE.findall(text):
        toks.append(raw.lower())
        if len(raw) >= 8:
            toks.extend(t.lower() for t in split_identifier(raw))
    return toks


SYMBOL_PATTERNS = [
    re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)", re.M),          # python
    re.compile(r"^\s*class\s+([A-Za-z_]\w*)", re.M),
    re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)", re.M),  # js/ts
    re.compile(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)", re.M),
    re.compile(r"^\s*(?:export\s+)?interface\s+([A-Za-z_$][\w$]*)", re.M),
    re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)", re.M),     # go
    re.compile(r"^\s*type\s+([A-Za-z_]\w*)\s+struct", re.M),
    re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)", re.M),  # rust
    re.compile(r"^\s*(?:pub\s+)?struct\s+([A-Za-z_]\w*)", re.M),
    re.compile(r"^\s*(?:pub\s+)?(?:unsafe\s+)?trait\s+([A-Za-z_]\w*)", re.M),
    re.compile(r"^\s*(?:public|private|protected)?\s*(?:final\s+)?class\s+([A-Za-z_]\w*)", re.M),  # java
    re.compile(r"^\s*(?:public|private)\s+\w[\w<>\[\]]*\s+([A-Za-z_]\w*)\s*\([^;]*\)\s*\{", re.M),
    re.compile(r"^\s*(?:static\s+)?(?:inline\s+)?[A-Za-z_][\w\s\*]*\s+\**([A-Za-z_]\w*)\s*\([^;]*\)\s*\{", re.M),  # c
]

IMPORT_PATTERNS = [
    re.compile(r"^\s*(?:from|import)\s+[\w.]*?([\w]+)", re.M),           # python
    re.compile(r"^\s*import\s+.*?['\"]([^'\"]+)['\"]", re.M),            # js
    re.compile(r"^\s*import\s+(?:[\w.]+\s+)?\"([\w./-]+)\"", re.M),      # go
    re.compile(r"^\s*use\s+([\w:]+)", re.M),                             # rust
    re.compile(r"#\s*include\s+[\"<]([^\">]+)[\">]", re.M),              # c
]

TEST_NAME_RES = [re.compile(r"(^|/)(tests?|__tests__)(/|$)"),
                 re.compile(r"(^|/)(test_)?[\w.]*_test\.\w+$"),
                 re.compile(r"(^|/)test_[\w.]+\.\w+$"),
                 re.compile(r"(^|/)[\w.-]+\.(spec|test)\.\w+$")]


def is_test_path(path: str) -> bool:
    return any(r.search(path) for r in TEST_NAME_RES)


# ---------------------------------------------------------------- repository scan

def walk(repo: Path):
    n = 0
    for dirpath, dirnames, filenames in __import__("os").walk(repo):
        cur = Path(dirpath)
        rel = cur.relative_to(repo).as_posix()
        if rel not in (".", "") and (rel.split("/")[0] in SKIP_DIRS or rel.startswith(".")):
            dirnames[:] = []
            continue
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            if fn.startswith(".") or fn.endswith((".lock", ".min.js", ".map", ".pyc")):
                continue
            p = cur / fn
            try:
                if p.stat().st_size > MAX_FILE_BYTES:
                    continue
                text = p.read_text(errors="replace")
            except OSError:
                continue
            n += 1
            if n > MAX_FILES:
                return
            yield rel_path(repo, p), text


def rel_path(repo: Path, p: Path) -> str:
    return p.relative_to(repo).as_posix()


def module_stem(path: str) -> str:
    base = path.rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[0]


# ---------------------------------------------------------------- cognition backend

AOCI_SESSION_ARTIFACT = ".oss-contrib-evidence/aoci_runtime_session.json"
SYMBOL_SPANS_ARTIFACT = ".oss-contrib-evidence/symbol_spans.json"


def load_aoci_runtime_session(repo: Path) -> dict | None:
    """A persisted AOCI_RUNTIME session receipt (written by aoci_runtime.py).

    Consumed ONLY when the receipt proves a complete cognition pass; a session
    that ended in explicit fallback or partial overview is NOT a runtime backend —
    the router then falls through to AOCI_FILE / native / lightweight and says so.
    """
    p = repo / AOCI_SESSION_ARTIFACT
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or data.get("artifact_type") != "AOCI_RUNTIME_SESSION":
        return None
    if data.get("fallback") or data.get("cognition_state") != "COMPLETE":
        return None
    return data


def load_symbol_spans(repo: Path) -> dict | None:
    p = repo / SYMBOL_SPANS_ARTIFACT
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or data.get("artifact_type") != "SYMBOL_SPANS":
        return None
    return data


def detect_backend(repo: Path) -> dict:
    session = load_aoci_runtime_session(repo)
    if session:
        return {"kind": "AOCI_RUNTIME",
                "identity": session.get("index_identity", ""),
                "aligned_state": session.get("alignment_state", "unknown"),
                "detail": "runtime session via %s %s @ generation %s (whole-index cognition %s)"
                          % (session.get("mcp_server_info", {}).get("name", "?"),
                             session.get("mcp_service_version", "?"),
                             session.get("generation", "?"),
                             session.get("cognition_state")),
                "cognition_state": session.get("cognition_state"),
                "generation": session.get("generation"),
                "session_artifact": AOCI_SESSION_ARTIFACT}
    aoci = (repo / "aoci.code.txt").exists() or (repo / "aoci.txt").exists()
    mem = (repo / ".oss-contrib-evidence" / "goals").exists()
    if aoci:
        state, detail = aoci_alignment(repo)
        return {"kind": "AOCI_FILE", "identity": "aoci volumes (file parser; no runtime session found)", "aligned_state": state,
                "detail": detail}
    if mem:
        return {"kind": "NATIVE_PROJECT_MEMORY", "identity": "goals/receipts", "aligned_state": "absent",
                "detail": "no aoci volumes; using persisted project artifacts"}
    return {"kind": "LIGHTWEIGHT_FALLBACK", "identity": "on-demand", "aligned_state": "absent",
            "detail": "no persisted cognition; deterministic collection only"}


def parse_aoci_entries(repo: Path) -> dict[str, dict]:
    """Parse FRAS lines: path[TAGS]: F:... | R:... | A:... | S:..."""
    entries: dict[str, dict] = {}
    for vol in ("aoci.code.txt", "aoci.txt"):
        p = repo / vol
        if not p.exists():
            continue
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            m = re.match(r"^([^\[\]:]+)(\[[^\]]*\])?:\s*(.*)$", line.strip())
            if not m or "|" not in m.group(3):
                continue
            path, tags, rest = m.group(1).strip(), m.group(2) or "", m.group(3)
            fields = {}
            for part in rest.split("|"):
                if len(part) > 2 and part[1] == ":":
                    fields[part[0]] = part[2:].strip()
            entries[path] = {"tags": tags.strip("[]"), "fields": fields, "volume": vol}
    return entries


def aoci_alignment(repo: Path) -> tuple[str, str]:
    """Best-effort alignment check: re-hash sampled bound sources against baseline."""
    baseline = repo / ".aoci" / "baseline.json"
    entries = parse_aoci_entries(repo)
    if not entries:
        return "absent", "no parseable entries"
    digests = None
    if baseline.exists():
        try:
            data = json.loads(baseline.read_text())
            # accept any {path: digest} shaped mapping at top level or one level deep
            for v in data.values() if isinstance(data, dict) else []:
                if isinstance(v, dict) and all(isinstance(x, str) for x in v.values()):
                    digests = v
                    break
            if digests is None and isinstance(data, dict):
                digests = {k: v for k, v in data.items()
                           if isinstance(k, str) and isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v)}
        except (json.JSONDecodeError, OSError):
            return "unbaselined", "baseline unreadable"
    if not digests:
        return "unverified", "no per-file digests found; treat entries as a map only"
    checked = matched = 0
    for path in list(entries)[:8]:
        src = repo / path
        want = digests.get(path) or digests.get("./" + path)
        if want:
            checked += 1
            got = hashlib.sha256(src.read_bytes()).hexdigest() if src.exists() else ""
            if got == want:
                matched += 1
    if checked == 0:
        return "unverified", "no sampled entry bound in baseline"
    if matched == checked:
        return "aligned", "%d/%d sampled entries match" % (matched, checked)
    return "drifted", "%d/%d sampled entries match — cognition is a map, not truth" % (matched, checked)


# ---------------------------------------------------------------- signals

class Corpus:
    def __init__(self, repo: Path):
        self.repo = repo
        self.files: dict[str, str] = {}
        self.tokens: dict[str, Counter] = {}
        self.symbols: dict[str, list[tuple[str, int]]] = {}
        self.imports: dict[str, list[str]] = {}
        self.backend = detect_backend(repo)
        if self.backend["kind"] == "AOCI_RUNTIME":
            # runtime session snapshot is a MAP of cognition claims, same shape as
            # the file parser's — ranking signal, never source truth
            snap = self._runtime_entries(repo)
            self.cognition = {
                path: {"tags": e.get("tags", ""), "fields": e.get("fields", {}),
                       "volume": "aoci-runtime"}
                for path, e in snap.items()}
        else:
            self.cognition = parse_aoci_entries(repo) if self.backend["kind"] == "AOCI_FILE" else {}
        self.spans = load_symbol_spans(repo)
        self.span_defs: dict[str, list[dict]] = defaultdict(list)
        self.span_refs: dict[str, list[dict]] = defaultdict(list)
        if self.spans:
            for d in self.spans.get("definitions", []):
                self.span_defs[str(d.get("symbol", "")).lower()].append(d)
            for r in self.spans.get("references", []):
                self.span_refs[str(r.get("symbol", "")).lower()].append(r)
        # structural graph (symbol_graph.json): calls/inherits edges lifted to
        # file level so bounded expansion can follow real semantic relations.
        # Built AFTER the file walk (adjacency is filtered against scanned files).
        self.structural_adj: dict[str, list[tuple[str, str]]] = {}
        for rel, text in walk(repo):
            self.files[rel] = text
            self.tokens[rel] = Counter(tokenize(text))
            syms: list[tuple[str, int]] = []
            for i, line in enumerate(text.splitlines()):
                for pat in SYMBOL_PATTERNS:
                    m = pat.match(line)
                    if m:
                        syms.append((m.group(1), i + 1))
                        break
            self.symbols[rel] = syms
            imps: list[str] = []
            for line in text.splitlines():
                for pat in IMPORT_PATTERNS:
                    m = pat.match(line)
                    if m:
                        imps.append(m.group(1))
                        break
            self.imports[rel] = imps
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
                            if sf != tf and sf in self.files and tf in self.files:
                                self.structural_adj.setdefault(sf, []).append(
                                    (tf, "%s %s" % (e["kind"], tf.rsplit("/", 1)[-1])))
            except (json.JSONDecodeError, OSError):
                pass
        self._bm25_stats()

    def _runtime_entries(self, repo: Path) -> dict:
        p = repo / AOCI_SESSION_ARTIFACT
        try:
            data = json.loads(p.read_text())
            return data.get("entries_snapshot", {}) or {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _bm25_stats(self):
        self.df: Counter = Counter()
        for c in self.tokens.values():
            self.df.update(c.keys())
        self.N = len(self.tokens)
        self.avgdl = (sum(sum(c.values()) for c in self.tokens.values()) / self.N) if self.N else 1

    def bm25(self, query_tokens: list[str]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for t in set(query_tokens):
            idf = math.log(1 + (self.N - self.df[t] + 0.5) / (self.df[t] + 0.5))
            if idf <= 0:
                continue
            for rel, c in self.tokens.items():
                tf = c.get(t, 0)
                if not tf:
                    continue
                dl = sum(c.values())
                scores[rel] = scores.get(rel, 0.0) + idf * (
                    tf * (K1 + 1)) / (tf + K1 * (1 - B + B * dl / self.avgdl))
        # cognition text boosts the file's lexical field (claims are leads, not truth)
        return scores

    def cognition_lexical(self, query_tokens: list[str]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for path, entry in self.cognition.items():
            text = " ".join(entry["fields"].values()) + " " + entry["tags"]
            hit = sum(1 for t in set(query_tokens) if t in tokenize(text))
            if hit:
                scores[path] = float(hit)
        return scores

    def tests_of(self, prod: str) -> list[str]:
        stem = module_stem(prod)
        out = []
        for rel in self.files:
            if not is_test_path(rel):
                continue
            if stem and stem in rel:
                out.append(rel)
            elif any(stem in (imp or "") for imp in self.imports.get(rel, [])):
                out.append(rel)
        return out


def repomap_rank(corpus: "Corpus", qtokens: list[str], qidents: list[str],
                 lexical_scores: dict[str, float], iterations: int = 30, d: float = 0.85) -> list[str]:
    """RepoMap-style structural prior (Aider's idea, reimplemented stdlib-only):
    PageRank over a file graph (importer -> imported, test -> production), with
    query personalization playing the role of Aider's chat-file multiplier."""
    files = list(corpus.files)
    n = len(files)
    if n == 0:
        return []
    stem_map: dict[str, list[str]] = defaultdict(list)
    for f in files:
        if not is_test_path(f):
            stem_map[module_stem(f)].append(f)

    edges: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for f in files:
        counts: Counter = Counter()
        for imp in corpus.imports.get(f, []):
            stem = imp.rsplit("/", 1)[-1].split(".")[0]
            for t in stem_map.get(stem, []):
                if t != f:
                    counts[t] += 1
        if is_test_path(f):
            for imp in corpus.imports.get(f, []):
                stem = imp.rsplit("/", 1)[-1].split(".")[0]
                for t in stem_map.get(stem, []):
                    counts[t] += 0  # test->prod edges already added below
        else:
            for t in corpus.tests_of(f):
                counts[t] += 1  # production hands mass to its tests
        for t, c in counts.items():
            if c:
                edges[f][t] += math.sqrt(c)

    # personalization: query-mentioned symbols/paths/lexical hits (the "chat" analog)
    pers: dict[str, float] = defaultdict(float)
    sym_hits = set()
    for rel, syms in corpus.symbols.items():
        names = {s.lower() for s, _ in syms}
        if any(q.lower() in names for q in qidents):
            sym_hits.add(rel)
    for rel in sym_hits:
        pers[rel] += 3.0
    for rel, s in sorted(lexical_scores.items(), key=lambda kv: -kv[1])[:10]:
        pers[rel] += 2.0
    for rel in files:
        segs = tokenize(rel.replace("/", " "))
        if any(t in segs for t in set(qtokens)):
            pers[rel] += 1.0

    rank = {f: 1.0 / n for f in files}
    pers_total = sum(pers.values()) or 1.0
    for _ in range(iterations):
        dangling = sum(rank[f] for f in files if f not in edges or not edges[f])
        new = {}
        for f in files:
            base = (1 - d) * (pers.get(f, 0.0) / pers_total if pers else 1.0 / n)
            base += d * dangling / n
            new[f] = base
        for src, dsts in edges.items():
            total = sum(dsts.values())
            if not total or rank[src] == 0.0:
                continue
            share = rank[src]
            for dst, w in dsts.items():
                new[dst] += d * share * (w / total)
        rank = new
    return sorted(files, key=lambda f: -rank[f])


def signal_rankings(corpus: "Corpus", query: str, args) -> dict[str, list[str]]:
    qtokens = tokenize(query)
    qidents = [t for t in dict.fromkeys(
        raw for raw in TOKEN_RE.findall(query) if len(raw) >= 4 and any(c.isalpha() for c in raw))]

    lexical = sorted(corpus.bm25(qtokens).items(), key=lambda kv: -kv[1])
    cog_lex = corpus.cognition_lexical(qtokens)
    if cog_lex:
        # merge as its own family: cognition claims boost ranking independently
        lexical = sorted({**dict(lexical), **{k: v * 2.0 for k, v in cog_lex.items()}}.items(),
                         key=lambda kv: -kv[1])

    path_scores = {}
    for rel in corpus.files:
        segs = tokenize(rel.replace("/", " "))
        hit = sum(1 for t in set(qtokens) if t in segs)
        if hit:
            path_scores[rel] = float(hit) / (1 + rel.count("/"))
    path = sorted(path_scores.items(), key=lambda kv: -kv[1])

    sym_scores = {}
    for rel, syms in corpus.symbols.items():
        names = {s.lower() for s, _ in syms}
        hit = sum(1 for q in qidents if q.lower() in names)
        if hit:
            sym_scores[rel] = float(hit)
    symbol = sorted(sym_scores.items(), key=lambda kv: -kv[1])

    # symbol_backend family: exact spans from a semantic backend (symbol_backend.py
    # artifact). Provenance kept per candidate; spans are pointers, digests checked
    # at evidence time — the backend is not source truth.
    sb_scores: dict[str, float] = {}
    if corpus.spans:
        for q in qidents:
            ql = q.lower()
            for d in corpus.span_defs.get(ql, []):
                if d["path"] in corpus.files:
                    sb_scores[d["path"]] = sb_scores.get(d["path"], 0.0) + 2.0
            for r in corpus.span_refs.get(ql, []):
                if r["path"] in corpus.files:
                    sb_scores[r["path"]] = sb_scores.get(r["path"], 0.0) + 1.0
    symbol_backend = sorted(sb_scores.items(), key=lambda kv: -kv[1])

    test_scores = {}
    for rel in corpus.files:
        if is_test_path(rel):
            continue
        for t in corpus.tests_of(rel):
            test_scores[t] = test_scores.get(t, 0.0) + 1.0
    testrel = sorted(test_scores.items(), key=lambda kv: -kv[1])

    history: list[tuple[str, float]] = []
    p = subprocess.run(
        ["git", "-C", str(corpus.repo), "log", "--name-only", "--oneline", "-n", "200"],
        capture_output=True, text=True, shell=False)
    if p.returncode == 0:
        rec: Counter = Counter()
        age = 0
        for i, line in enumerate(p.stdout.splitlines()):
            if re.fullmatch(r"[0-9a-f]{7,}", line.strip()):
                age = i
                continue
            f = line.strip()
            if f in corpus.files:
                rec[f] += 1.0 / math.log(2 + age / 6)
        history = sorted(rec.items(), key=lambda kv: -kv[1])

    repomap = repomap_rank(corpus, qtokens, qidents, dict(lexical))

    return {"lexical": [r for r, _ in lexical], "path": [r for r, _ in path],
            "symbol": [r for r, _ in symbol], "test": [r for r, _ in testrel],
            "history": [r for r, _ in history],
            "repomap": repomap,
            "symbol_backend": [r for r, _ in symbol_backend],
            "cognition": list(corpus.cognition.keys()) if corpus.cognition else []}


DIRECT_FAMILIES = {"lexical", "symbol", "test", "history", "cognition", "path",
                   "symbol_backend"}
STRUCTURAL_FAMILIES = {"repomap", "graph"}

# Workflow-aware routing: each policy decides WHICH families run, their RRF weights,
# and how structural-only candidates (repomap/graph with no direct evidence) are
# treated. Priors are initial hypotheses derived from Agent Retrieval Bench
# (arXiv 2607.24882) per-workflow results plus our own measured fd/click data; they
# are hypotheses to validate via routing-regret reporting, not assumed constants.
# The hub guard is constructive: unless a policy declares structural_first, direct
# candidates always outrank structural-only ones, so a central hub can never
# displace a direct lexical/symbol/test hit.
ROUTING_POLICIES = {
    "trace2code": {
        "signals": ["lexical", "symbol", "history", "test"],
        "weights": {"lexical": 1.5, "history": 1.2, "symbol": 1.0},
        "structural": {"families": ["graph"], "max_share": 0.34},
        "structural_first": False,
        "prior_source": "ARB: trace2code favors lexical/RepoMap, embeddings weak; "
                        "our fd data showed repomap hub displacement — graph allowed, "
                        "capped, direct-first",
    },
    "code2test": {
        "signals": ["test", "symbol", "lexical", "path"],
        "weights": {"test": 1.5, "symbol": 1.2, "lexical": 1.0},
        "structural": {"families": [], "max_share": 0.0},
        "structural_first": False,
        "prior_source": "ARB: code2test = test relations dominate",
    },
    "comment2context": {
        "signals": ["symbol", "path", "lexical"],
        "weights": {"symbol": 1.4, "path": 1.0, "lexical": 0.8},
        "structural": {"families": [], "max_share": 0.0},
        "structural_first": False,
        "prior_source": "ARB winner was embedding-based; without embeddings, "
                        "symbol+path neighborhood",
    },
    "edit2ripple": {
        "signals": ["test", "symbol", "lexical", "path"],
        "weights": {"test": 1.2, "symbol": 1.0, "lexical": 0.8},
        "structural": {"families": ["graph"], "max_share": 0.5},
        "structural_first": False,
        "prior_source": "ripple = dependency expansion matters, generic centrality not",
    },
    "explore": {
        "signals": ["cognition", "path", "lexical", "repomap"],
        "weights": {"cognition": 1.5, "path": 1.2, "lexical": 1.0, "repomap": 1.2},
        "structural": {"families": ["repomap"], "max_share": 0.6},
        "structural_first": True,
        "prior_source": "survey-shaped task: structural centrality may legitimately lead",
    },
    "issue2code": {
        "signals": ["lexical", "symbol", "symbol_backend", "cognition", "history"],
        "weights": {"lexical": 1.2, "symbol": 1.2, "symbol_backend": 1.4, "cognition": 1.0},
        "structural": {"families": ["graph"], "max_share": 0.25},
        "structural_first": False,
        "prior_source": "general localization mix; structure as capped support only; "
                        "semantic symbol spans outrank lexical name scans when present",
    },
    "review": {
        "signals": ["symbol", "symbol_backend", "history", "lexical"],
        "weights": {"symbol": 1.2, "symbol_backend": 1.2, "history": 1.0, "lexical": 1.0},
        "structural": {"families": ["graph"], "max_share": 0.4},
        "structural_first": False,
        "prior_source": "review context = changed symbols + their history",
    },
    "bug_hunt": {
        "signals": ["history", "lexical", "test"],
        "weights": {"history": 1.5, "lexical": 1.0, "test": 1.0},
        "structural": {"families": ["graph"], "max_share": 0.25},
        "structural_first": False,
        "prior_source": "hunting = recent-fix history + sibling tests",
    },
}


def classify_candidates(rankings: dict[str, list[str]], top_n: int = 40) -> dict[str, str]:
    """direct = hit by ≥1 query-specific family; structural = repomap/graph only."""
    cls: dict[str, str] = {}
    for family, ranking in rankings.items():
        tag = "direct" if family in DIRECT_FAMILIES else "structural"
        for p in ranking[:top_n]:
            if cls.get(p) != "direct":
                cls[p] = tag
    return cls


def rrf_fuse(rankings: dict[str, list[str]], weights: dict[str, float],
             top_n: int = 40):
    fused: dict[str, float] = defaultdict(float)
    why: dict[str, list[str]] = defaultdict(list)
    for family, ranking in rankings.items():
        w = weights.get(family, 1.0)
        for i, path in enumerate(ranking[:top_n]):
            fused[path] += w / (RRF_K + i + 1)
            if len(why[path]) < 4:
                why[path].append("%s#%d" % (family, i + 1))
    return sorted(fused.items(), key=lambda kv: -kv[1]), why


def build_evidence(path: str, rankings: dict[str, list[str]], corpus: Corpus,
                   qidents: list[str], graph_via: dict[str, str],
                   graph_depth: dict[str, int], why: list[str]) -> list[dict]:
    """Structured per-arm evidence: why this candidate exists. Ranking signals,
    not probabilities."""
    ev = []
    for family, ranking in rankings.items():
        if path in ranking[:40]:
            rank = ranking.index(path) + 1
            item = {"family": family, "rank": rank}
            if family == "symbol":
                names = {s.lower() for s, _ in corpus.symbols.get(path, [])}
                exact = any(q.lower() in names for q in qidents)
                item["match"] = "exact" if exact else "partial"
            elif family == "symbol_backend":
                backend = (corpus.spans or {}).get("backend", "unknown")
                item["backend"] = backend
                hit = None
                for q in qidents:
                    ql = q.lower()
                    for d in corpus.span_defs.get(ql, []):
                        if d["path"] == path and (hit is None or hit.get("weight", 0) < 2):
                            hit = {"symbol": d["symbol"], "kind": d["kind"],
                                   "line": d["start_line"], "relation": d["relation"],
                                   "digest": d.get("source_digest", ""), "weight": 2}
                    for r in corpus.span_refs.get(ql, []):
                        if r["path"] == path and hit is None:
                            hit = {"symbol": r["symbol"], "kind": r.get("kind"),
                                   "line": r["start_line"], "relation": r["relation"],
                                   "digest": r.get("source_digest", ""), "weight": 1}
                if hit:
                    item["match"] = "definition" if hit["weight"] >= 2 else "reference"
                    item["symbol"] = hit["symbol"]
                    item["line"] = hit["line"]
                    item["relation"] = hit["relation"]
                    src = corpus.repo / path
                    if src.exists() and hit["digest"]:
                        item["source_digest_state"] = (
                            "CURRENT" if hashlib.sha256(src.read_bytes()).hexdigest()
                            == hit["digest"] else "CHANGED")
                    else:
                        item["source_digest_state"] = "UNKNOWN"
                item["note"] = ("spans come from a semantic backend; current source "
                                "remains authoritative")
            elif family == "cognition" and corpus.backend["kind"] == "AOCI_RUNTIME":
                item["backend"] = "aoci-runtime@%s" % corpus.backend.get("generation", "?")
                item["note"] = "runtime cognition claim (map, not source truth)"
            elif family == "graph":
                item["relation"] = graph_via.get(path, "expanded")
                item["distance"] = graph_depth.get(path)
            elif family == "repomap":
                n = len(ranking)
                item["centrality"] = "high" if rank <= max(3, n // 20) else (
                    "mid" if rank <= max(5, n // 5) else "low")
                item["note"] = "supporting evidence only unless policy is structural_first"
            ev.append(item)
    return ev


def reason_phrase(evidence: list[dict]) -> str:
    parts = []
    for e in evidence:
        if e["family"] == "symbol":
            parts.append("%s symbol match" % e["match"])
        elif e["family"] == "symbol_backend":
            parts.append("%s via %s (%s@L%s)" % (e.get("match", "span"), e.get("backend"),
                                                 e.get("symbol"), e.get("line")))
        elif e["family"] == "cognition" and "backend" in e:
            parts.append("cognition hit [%s]" % e["backend"])
        elif e["family"] == "graph":
            parts.append("direct dependency (distance %s)" % e.get("distance"))
        elif e["family"] == "repomap":
            parts.append("%s centrality (support)" % e["centrality"])
        else:
            parts.append("%s hit" % e["family"])
    return " + ".join(parts) or "fused"


def graph_expand(corpus: Corpus, seeds: list[tuple[str, float]], max_depth: int,
                 max_nodes: int) -> list[tuple[str, float, str, int]]:
    """Priority-queue expansion over imports/tests edges. Never BFS; pruned by score.
    Returns (path, score, via, depth)."""
    import heapq
    prod_by_stem = defaultdict(list)
    for rel in corpus.files:
        if not is_test_path(rel):
            prod_by_stem[module_stem(rel)].append(rel)
    seen = {s for s, _ in seeds}
    frontier = [(score * 1.0, 0, path, "seed") for path, score in seeds[:5]]
    heapq.heapify(frontier)
    out = []
    while frontier and len(out) < max_nodes:
        score, depth, path, via = heapq.heappop(frontier)
        out.append((path, score, via, depth))
        if depth >= max_depth:
            continue
        neighbors = []
        for imp in corpus.imports.get(path, []):
            stem = imp.rsplit("/", 1)[-1].split(".")[0]
            neighbors.extend(("imports %s" % module_stem(stem), p) for p in prod_by_stem.get(stem, []))
        stem = module_stem(path)
        for t in corpus.tests_of(path):
            neighbors.append(("tests %s" % stem, t))
        # semantic structural edges from the symbol graph (calls/inherits/imports
        # with relation labels) — provenance carried on the expansion itself
        neighbors.extend((label, target)
                         for target, label in corpus.structural_adj.get(path, []))
        for edge, n in neighbors:
            if n in seen:
                continue
            seen.add(n)
            parent_score = dict((p, s) for p, s, _, _ in out).get(path, 0.1)
            nscore = parent_score * (0.5 ** (depth + 1))
            if nscore > 0.02:
                heapq.heappush(frontier, (nscore, depth + 1, n, edge))
    extra = [(p, s, v, d) for p, s, v, d in out if p not in {x for x, _ in seeds}]
    return extra


def route(repo_path: str, query: str, task_type: str, signals: list[str] | None,
          top_k: int, max_depth: int, max_nodes: int) -> dict:
    repo = Path(repo_path).resolve()
    if not repo.is_dir():
        print("error: %s is not a directory" % repo, file=sys.stderr)
        raise SystemExit(3)
    corpus = Corpus(repo)
    if not corpus.files:
        return {"backend": corpus.backend, "candidates": [], "abstention":
                {"returned": False, "factors": {"reason": "no files scanned"}}, "limits": []}
    t0 = datetime.now()
    all_rankings = signal_rankings(corpus, query, None)

    # --- routing policy: which families run this workflow? --------------------
    policy = ROUTING_POLICIES.get(task_type, ROUTING_POLICIES["issue2code"])
    ablation_override = bool(signals)
    if ablation_override:
        # explicit arm override (evaluation ablations): merge everything requested,
        # legacy behavior — routing policy bypassed ON PURPOSE and recorded
        run_families = [f for f in all_rankings if f in signals]
        weights = {f: 1.0 for f in run_families}
        structural_cfg = {"families": [f for f in signals if f in STRUCTURAL_FAMILIES],
                          "max_share": 1.0}
        structural_first = False
        routing_mode = "ablation-override"
    else:
        run_families = [f for f in all_rankings if f in policy["signals"]]
        weights = {f: policy["weights"].get(f, 1.0) for f in run_families}
        structural_cfg = policy["structural"]
        structural_first = policy["structural_first"]
        routing_mode = "policy:%s" % task_type
    rankings = {f: all_rankings[f] for f in run_families}

    qidents = [t for t in dict.fromkeys(
        raw for raw in TOKEN_RE.findall(query) if len(raw) >= 4 and any(c.isalpha() for c in raw))]
    fused, why = rrf_fuse(rankings, weights)
    expanded = graph_expand(corpus, fused[:5], max_depth, max_nodes) \
        if (fused and "graph" in structural_cfg["families"]) else []
    graph_rank = {p: i for i, (p, _, _, _) in enumerate(sorted(expanded, key=lambda x: -x[1]))}
    merged = dict(fused)
    for p, s, via, depth in expanded:
        w = weights.get("graph", 1.0)
        merged[p] = merged.get(p, 0.0) + w / (RRF_K + graph_rank.get(p, 20) + 1)
        why.setdefault(p, []).append("graph distance %d via %s" % (depth, via))

    ranked_all = sorted(merged.items(), key=lambda kv: -kv[1])
    klass = classify_candidates(rankings | ({"graph": [p for p, _, _, _ in expanded]} if expanded else {}))

    # --- no-regret guard: structural candidates fill only REMAINING slots ------
    # (constructive guarantee: a repomap/graph-only hub can never displace a
    #  direct lexical/symbol/test hit unless the policy declares structural_first)
    direct_order = [(p, s) for p, s in ranked_all if klass.get(p) == "direct"]
    structural_order = [(p, s) for p, s in ranked_all if klass.get(p) == "structural"]
    if structural_first:
        final_order = structural_order + direct_order
        guard = "structural_first policy (explore): centrality may lead"
    else:
        final_order = direct_order + structural_order
        guard = ("direct-first: structural-only candidates fill remaining slots; "
                 "displacement of direct evidence is impossible by construction")
    ranked = final_order[:top_k]
    structural_admitted = sum(1 for p, _ in ranked if klass.get(p) == "structural")
    max_structural = int(math.ceil(top_k * structural_cfg["max_share"])) \
        if structural_cfg["max_share"] < 1.0 else top_k
    demoted = []
    if structural_admitted > max_structural and not structural_first:
        # enforce share cap: keep the first max_structural structural candidates
        new_ranked, seen_struct = [], 0
        for p, s in ranked:
            if klass.get(p) == "structural":
                seen_struct += 1
                if seen_struct > max_structural:
                    demoted.append(p)
                    continue
            new_ranked.append((p, s))
        # refill freed slots from structural_order beyond current cut
        present = {p for p, _ in new_ranked}
        for p, s in structural_order:
            if len(new_ranked) >= top_k:
                break
            if p not in present and p not in demoted:
                new_ranked.append((p, s))
        ranked = new_ranked[:top_k]
    routing_decision = {
        "mode": routing_mode,
        "policy_signals": policy["signals"] if not ablation_override else run_families,
        "weights": weights,
        "guard": guard,
        "structural_max_share": structural_cfg["max_share"],
        "structural_admitted": sum(1 for p, _ in ranked if klass.get(p) == "structural"),
        "direct_in_topk": sum(1 for p, _ in ranked if klass.get(p) == "direct"),
        "demoted_over_quota": demoted,
        "prior_source": policy["prior_source"] if not ablation_override else
                        "explicit --signals ablation; priors bypassed",
        "latency_ms": int((datetime.now() - t0).total_seconds() * 1000),
    }

    graph_via = {p: v for p, _, v, _ in expanded}
    graph_depth = {p: d for p, _, _, d in expanded}
    fam_tops = {f: (v[0] if v else None) for f, v in rankings.items()}
    abstention = {
        "returned": bool(ranked),
        "factors": {
            "family_top_candidates": fam_tops,
            "query_identifiers_matched_in_symbols": bool(rankings.get("symbol")),
            "cognition_domains_available": bool(corpus.cognition),
            "note": "ARB 2607.24882: top-score thresholds are NOT reliable abstention "
                    "signals on natural no-gold cases; the agent decides with these "
                    "factors, not from a pseudo-probability",
        },
    }
    candidates = []
    for i, (path, score) in enumerate(ranked, 1):
        text = corpus.files[path]
        evidence = build_evidence(path, rankings, corpus, qidents,
                                  graph_via, graph_depth, why.get(path, []))
        if any(e["family"] == "graph" for e in evidence) and path in graph_via:
            for e in evidence:
                if e["family"] == "graph":
                    e["relation"] = graph_via[path]
        candidates.append({
            "rank": i, "path": path,
            "rrf": round(score, 5),
            "evidence_class": klass.get(path, "structural"),
            "evidence": evidence,
            "signals": {f: (rankings[f].index(path) + 1) for f in rankings
                        if path in rankings[f][:top_k]},
            "reason": reason_phrase(evidence) or "; ".join(why.get(path, [])) or "fused",
            "radius": 1 if i <= max(1, top_k // 2) else 2,
            "is_test": is_test_path(path),
            "est_tokens": len(text) // 4,
        })
    backends_used: dict = {"cognition": {"kind": corpus.backend["kind"],
                                         "identity": corpus.backend.get("identity", ""),
                                         "aligned_state": corpus.backend.get("aligned_state", "")}}
    if corpus.spans:
        backends_used["symbol_backend"] = {
            "backend": corpus.spans.get("backend"),
            "generated_at": corpus.spans.get("generated_at"),
            "selection_reason": corpus.spans.get("backend_selection_reason"),
            "serena_attempt": corpus.spans.get("serena_attempt"),
            "definitions": (corpus.spans.get("counts") or {}).get("definitions"),
            "references": (corpus.spans.get("counts") or {}).get("references"),
        }
    return {
        "backend": corpus.backend,
        "task_type": task_type,
        "query": query,
        "generated": datetime.now(timezone.utc).isoformat(),
        "routing_decision": routing_decision,
        "candidates": candidates,
        "abstention": abstention,
        "backends": backends_used,
        "limits": ["history window: 200 commits", "max file bytes: %d" % MAX_FILE_BYTES,
                   "graph expansion: depth<=%d nodes<=%d (priority queue, distance penalty 0.5^depth)"
                   % (max_depth, max_nodes)],
        "provenance": {"families_run": list(rankings.keys()),
                       "files_scanned": len(corpus.files),
                       "backend_principle": "no backend is source truth; current source remains authoritative",
                       "generated_by": "retrieval_router.py v3 (routing policies + external backends)"},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Hybrid retrieval router (deterministic, offline).")
    ap.add_argument("repo")
    ap.add_argument("query")
    ap.add_argument("--task-type", default="issue2code",
                    choices=list(ROUTING_POLICIES))
    ap.add_argument("--signals", help="comma subset: lexical,path,symbol,symbol_backend,test,history,cognition,graph")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--max-depth", type=int, default=2)
    ap.add_argument("--max-nodes", type=int, default=50)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    signals = [s.strip() for s in args.signals.split(",")] if args.signals else None
    report = route(args.repo, args.query, args.task_type, signals, args.top_k,
                   args.max_depth, args.max_nodes)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    b = report["backend"]
    print("backend: %s (%s) — %s" % (b["kind"], b["aligned_state"], b["detail"]))
    for c in report["candidates"]:
        print("  #%-2d [%s%s] %s (%s)" % (
            c["rank"], "R%d " % c["radius"], "test] " if c["is_test"] else "]    ",
            c["path"], ", ".join("%s@%d" % (f, r) for f, r in c["signals"].items())))
    ab = report["abstention"]
    if not ab["returned"]:
        print("NO_RELEVANT_LOCAL_CONTEXT — factors: %s" % json.dumps(ab["factors"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
