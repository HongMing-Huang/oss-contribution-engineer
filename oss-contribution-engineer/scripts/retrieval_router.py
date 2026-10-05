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

def detect_backend(repo: Path) -> dict:
    aoci = (repo / "aoci.code.txt").exists() or (repo / "aoci.txt").exists()
    mem = (repo / ".oss-contrib-evidence" / "goals").exists()
    if aoci:
        state, detail = aoci_alignment(repo)
        return {"kind": "AOCI_NATIVE", "identity": "aoci volumes", "aligned_state": state,
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
        self.cognition = parse_aoci_entries(repo) if self.backend["kind"] == "AOCI_NATIVE" else {}
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
            if is_test_path(rel):
                imps: list[str] = []
                for line in text.splitlines():
                    for pat in IMPORT_PATTERNS:
                        m = pat.match(line)
                        if m:
                            imps.append(m.group(1))
                            break
                self.imports[rel] = imps
        self._bm25_stats()

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


def signal_rankings(corpus: Corpus, query: str, args) -> dict[str, list[str]]:
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

    return {"lexical": [r for r, _ in lexical], "path": [r for r, _ in path],
            "symbol": [r for r, _ in symbol], "test": [r for r, _ in testrel],
            "history": [r for r, _ in history],
            "cognition": list(corpus.cognition.keys()) if corpus.cognition else []}


TASK_PRIORS = {
    "explore":        {"cognition": 1.5, "path": 1.2, "graph": 1.0},
    "code2test":      {"test": 1.5, "symbol": 1.2, "lexical": 1.0},
    "comment2context":{"symbol": 1.4, "path": 1.0, "lexical": 0.8},
    "trace2code":     {"lexical": 1.5, "history": 1.2, "symbol": 1.0},
    "edit2ripple":    {"graph": 1.5, "test": 1.2, "symbol": 1.0},
    "issue2code":     {"lexical": 1.2, "symbol": 1.2, "cognition": 1.0},
    "review":         {"graph": 1.2, "history": 1.0, "symbol": 1.0},
    "bug_hunt":       {"history": 1.5, "lexical": 1.0, "test": 1.0},
}


def rrf_fuse(rankings: dict[str, list[str]], task_type: str, top_n: int = 40):
    priors = TASK_PRIORS.get(task_type, {})
    fused: dict[str, float] = defaultdict(float)
    why: dict[str, list[str]] = defaultdict(list)
    for family, ranking in rankings.items():
        w = priors.get(family, 1.0)
        for i, path in enumerate(ranking[:top_n]):
            fused[path] += w / (RRF_K + i + 1)
            if len(why[path]) < 4:
                why[path].append("%s#%d" % (family, i + 1))
    return sorted(fused.items(), key=lambda kv: -kv[1]), why


def graph_expand(corpus: Corpus, seeds: list[tuple[str, float]], max_depth: int,
                 max_nodes: int) -> list[tuple[str, float, str]]:
    """Priority-queue expansion over imports/tests edges. Never BFS; pruned by score."""
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
        out.append((path, score, via))
        if depth >= max_depth:
            continue
        neighbors = []
        for imp in corpus.imports.get(path, []):
            stem = imp.rsplit("/", 1)[-1].split(".")[0]
            neighbors.extend(("imports", p) for p in prod_by_stem.get(stem, []))
        stem = module_stem(path)
        for t in corpus.tests_of(path):
            neighbors.append(("tests", t))
        for edge, n in neighbors:
            if n in seen:
                continue
            seen.add(n)
            parent_score = dict((p, s) for p, s, _ in out).get(path, 0.1)
            nscore = parent_score * (0.5 ** (depth + 1))
            if nscore > 0.02:
                heapq.heappush(frontier, (nscore, depth + 1, n, "%s from %s" % (edge, path)))
    extra = [(p, s, v) for p, s, v in out if p not in {x for x, _ in seeds}]
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
    rankings = signal_rankings(corpus, query, None)
    if signals:
        rankings = {k: v for k, v in rankings.items() if k in signals}
    fused, why = rrf_fuse(rankings, task_type)
    expanded = graph_expand(corpus, fused[:5], max_depth, max_nodes) if fused else []
    graph_rank = {p: i for i, (p, _, _) in enumerate(sorted(expanded, key=lambda x: -x[1]))}
    merged = dict(fused)
    for p, s, _ in expanded:
        w = TASK_PRIORS.get(task_type, {}).get("graph", 1.0)
        merged[p] = merged.get(p, 0.0) + w / (RRF_K + graph_rank.get(p, 20) + 1)
        why.setdefault(p, []).append("graph:%s" % _[:40])

    ranked = sorted(merged.items(), key=lambda kv: -kv[1])[:top_k]
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
        candidates.append({
            "rank": i, "path": path,
            "rrf": round(score, 5),
            "signals": {f: (rankings[f].index(path) + 1) for f in rankings if path in rankings[f][:top_k]},
            "reason": "; ".join(why.get(path, [])) or "fused",
            "radius": 1 if i <= max(1, top_k // 2) else 2,
            "is_test": is_test_path(path),
            "est_tokens": len(text) // 4,
        })
    return {
        "backend": corpus.backend,
        "task_type": task_type,
        "query": query,
        "generated": datetime.now(timezone.utc).isoformat(),
        "candidates": candidates,
        "abstention": abstention,
        "limits": ["history window: 200 commits", "max file bytes: %d" % MAX_FILE_BYTES,
                   "graph expansion: depth<=%d nodes<=%d (priority queue, distance penalty 0.5^depth)"
                   % (max_depth, max_nodes)],
        "provenance": {"families_run": list(rankings.keys()),
                       "files_scanned": len(corpus.files),
                       "generated_by": "retrieval_router.py v1"},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Hybrid retrieval router (deterministic, offline).")
    ap.add_argument("repo")
    ap.add_argument("query")
    ap.add_argument("--task-type", default="issue2code",
                    choices=list(TASK_PRIORS))
    ap.add_argument("--signals", help="comma subset: lexical,path,symbol,test,history,cognition,graph")
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
