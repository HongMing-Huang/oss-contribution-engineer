#!/usr/bin/env python3
"""symbol_backend.py — symbol intelligence interface for the context pipeline.

One interface, pluggable semantic backends:

    find_symbol | find_references | symbol_span | file_symbols

Backend selection (first real implementation first):
  1. serena      — Serena/LSP over MCP stdio, used ONLY when the operator configures
                   it (SERENA_MCP_COMMAND env or .oss-contrib-evidence/symbol_backend.json).
                   If configured but the server is missing/fails, we fall back
                   EXPLICITLY (the report names the attempt and the reason) — never
                   silently pretend the LSP was used.
  2. python-ast  — CPython's own `ast` module. This is a real semantic backend:
                   exact definition spans (lineno/end_lineno) from the parse tree,
                   references from Name/Attribute nodes with Load context, and
                   inheritance edges from ClassDef.bases. No regex heuristics.
                   Python files only; other languages honestly return nothing.

Every result row carries current-source identity:
    {path, symbol, kind, start_line, end_line, source_digest, relation, backend}
and `verify` re-hashes files to detect digest drift (CURRENT / CHANGED / DELETED).

No backend is source truth: spans are pointers INTO current source, and the digest
is what makes them checkable. `index` persists a spans artifact for
retrieval_router.py to consume with full provenance.

Exit codes: 0 ok, 2 usage, 3 repo error, 4 requested backend unavailable.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mcp_stdio_client import McpStdioClient, McpError, McpUnavailable, resolve_command  # noqa: E402

SKIP_DIRS = {
    ".git", ".hg", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    "out", "target", ".tox", ".mypy_cache", ".pytest_cache", ".oss-contrib-evidence",
    ".aoci", ".mimosa", ".idea", ".vscode",
}
MAX_FILE_BYTES = 300_000
ARTIFACT = ".oss-contrib-evidence/symbol_spans.json"

OPS = ("find_symbol", "find_references", "symbol_span", "file_symbols")


# ---------------------------------------------------------------- repository walk
def iter_py_files(repo: Path):
    for dirpath, dirnames, filenames in os.walk(repo):
        cur = Path(dirpath)
        rel = cur.relative_to(repo).as_posix()
        if rel != "." and (rel.split("/")[0] in SKIP_DIRS or rel.startswith(".")):
            dirnames[:] = []
            continue
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            if not fn.endswith(".py"):
                continue
            p = cur / fn
            try:
                if p.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield p


def digest_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- python-ast backend
def parse_file(path: Path):
    try:
        tree = ast.parse(path.read_text(errors="replace"), filename=str(path))
        return tree, None
    except (SyntaxError, ValueError, OSError) as exc:
        return None, str(exc)[:200]


def _row(path_str: str, symbol: str, kind: str, start: int, end: int,
         digest: str, relation: str, backend: str) -> dict:
    return {"path": path_str, "symbol": symbol, "kind": kind,
            "start_line": start, "end_line": end,
            "source_digest": digest, "relation": relation, "backend": backend}


def ast_file_symbols(repo: Path, path_str: str) -> tuple[list[dict], str | None]:
    p = repo / path_str
    if not p.exists():
        return [], "file not found"
    tree, err = parse_file(p)
    if tree is None:
        return [], err
    digest = digest_of(p)
    rows = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            rows.append(_row(path_str, node.name, "function", node.lineno,
                             node.end_lineno or node.lineno, digest, "definition", "python-ast"))
        elif isinstance(node, ast.ClassDef):
            rows.append(_row(path_str, node.name, "class", node.lineno,
                             node.end_lineno or node.lineno, digest, "definition", "python-ast"))
    return rows, None


def ast_find_symbol(repo: Path, name: str, path: str | None = None) -> list[dict]:
    out = []
    targets = [path] if path else sorted(
        p.relative_to(repo).as_posix() for p in iter_py_files(repo))
    for ps in targets:
        rows, _ = ast_file_symbols(repo, ps)
        out.extend(r for r in rows if r["symbol"] == name)
    return out


def ast_find_references(repo: Path, name: str, path: str | None = None) -> list[dict]:
    out = []
    targets = [repo / path] if path else sorted(iter_py_files(repo))
    for p in targets:
        if not p.exists():
            continue
        tree, _ = parse_file(p)
        if tree is None:
            continue
        digest = digest_of(p)
        ps = p.relative_to(repo).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id == name:
                out.append(_row(ps, name, "name", node.lineno, node.lineno,
                                digest, "reference", "python-ast"))
            elif isinstance(node, ast.Attribute) and node.attr == name:
                out.append(_row(ps, name, "attribute", node.lineno, node.lineno,
                                digest, "attribute_reference", "python-ast"))
            elif isinstance(node, ast.ClassDef):
                for base in node.bases:
                    bname = base.id if isinstance(base, ast.Name) else (
                        base.attr if isinstance(base, ast.Attribute) else None)
                    if bname == name:
                        out.append(_row(ps, name, "class", node.lineno, node.lineno,
                                        digest, "inherits", "python-ast"))
    return out


def ast_symbol_span(repo: Path, path_str: str, name: str) -> list[dict]:
    rows, _ = ast_file_symbols(repo, path_str)
    return [r for r in rows if r["symbol"] == name]


# ---------------------------------------------------------------- serena adapter
def serena_command(repo: Path) -> list[str] | None:
    spec = os.environ.get("SERENA_MCP_COMMAND")
    if not spec:
        cfg = repo / ".oss-contrib-evidence" / "symbol_backend.json"
        if cfg.exists():
            try:
                spec = (json.loads(cfg.read_text()) or {}).get("mcp_command") or ""
            except (json.JSONDecodeError, OSError):
                return None
    return resolve_command(spec) if spec else None


def serena_run(repo: Path, argv: list[str], op: str, **kw) -> list[dict]:
    """Map our operations onto Serena's MCP tools. Falls back with an explicit
    reason if the server cannot be reached — callers surface that, never hide it."""
    from collections import OrderedDict
    try:
        with McpStdioClient(argv, cwd=str(repo), request_timeout=90.0) as client:
            names = {t.get("name", "") for t in client.list_tools()}
            def need(*tools):
                missing = [t for t in tools if t not in names]
                if missing:
                    raise McpError("server lacks tools: %s" % ", ".join(missing))
            if op in ("find_symbol", "symbol_span"):
                need("find_symbol")
                res = client.call_tool_json("find_symbol", {
                    "name_path": kw["name"], "relative_path": kw.get("path"),
                    "include_body": False})
            elif op == "find_references":
                need("find_referencing_symbols")
                # Serena needs a symbol to reference FROM; find it first.
                sym = client.call_tool_json("find_symbol", {
                    "name_path": kw["name"], "relative_path": kw.get("path"),
                    "include_body": False})
                hits = sym.get("matches", sym if isinstance(sym, list) else [])
                if not hits:
                    return []
                first = hits[0] if isinstance(hits, list) else hits
                res = client.call_tool_json("find_referencing_symbols", {
                    "name_path": first.get("name_path", kw["name"]),
                    "relative_path": first.get("relative_path", kw.get("path")),
                    "include_body": False})
            else:  # file_symbols
                need("find_symbol")
                res = client.call_tool_json("find_symbol", {
                    "relative_path": kw["path"], "include_body": False})
    except (McpError, McpUnavailable, OSError, ValueError) as exc:
        raise SerenaBackendError("serena backend unavailable: %s" % str(exc)[:300])

    rows, seen = [], OrderedDict()
    for m in res.get("matches", res if isinstance(res, list) else []):
        if not isinstance(m, dict):
            continue
        loc = (m.get("location") or m.get("relative_path") or "")
        ps = str(loc).split(":")[0]
        span = m.get("range") or m.get("location") or {}
        start = span.get("start_line") or m.get("start_line")
        if not ps or not start:
            continue
        p = repo / ps
        digest = digest_of(p) if p.exists() else ""
        key = (ps, m.get("name", ""), start)
        if key in seen:
            continue
        seen[key] = True
        rows.append(_row(ps, m.get("name", kw.get("name", "")),
                         m.get("kind", "symbol"), start,
                         span.get("end_line") or start, digest,
                         m.get("relation", "definition"), "serena-lsp"))
    return rows


class SerenaBackendError(RuntimeError):
    pass


# ---------------------------------------------------------------- backend dispatch
def resolve_backend(repo: Path, requested: str | None) -> dict:
    if requested == "python-ast":
        return {"backend": "python-ast", "reason": "explicitly requested"}
    if requested == "serena" or requested is None:
        argv = serena_command(repo)
        if argv:
            return {"backend": "serena", "argv": argv, "reason": "operator-configured SERENA_MCP_COMMAND"}
        if requested == "serena":
            return {"backend": "unavailable",
                    "reason": "serena requested but SERENA_MCP_COMMAND is not configured"}
        return {"backend": "python-ast", "reason": "no LSP backend configured; stdlib ast backend is the default"}
    return {"backend": "unavailable", "reason": "unknown backend %r" % requested}


def run_op(repo: Path, op: str, name: str | None, path: str | None,
           requested_backend: str | None) -> dict:
    if op not in OPS:
        return {"ok": False, "error": "unknown operation %r (choose from %s)" % (op, ", ".join(OPS))}
    sel = resolve_backend(repo, requested_backend)
    meta = {"operation": op, "requested_backend": requested_backend,
            "selected_backend": sel["backend"], "selection_reason": sel["reason"]}
    rows: list[dict] = []
    fallback = None
    if sel["backend"] == "serena":
        try:
            rows = serena_run(repo, sel["argv"], op, name=name, path=path)
        except SerenaBackendError as exc:
            fallback = str(exc)
            sel = {"backend": "python-ast",
                   "reason": "serena failed; explicit fallback to stdlib ast backend"}
            meta["selected_backend"] = "python-ast"
            meta["selection_reason"] = sel["reason"]
            meta["serena_fallback_reason"] = fallback
    if sel["backend"] == "python-ast":
        if op == "find_symbol":
            rows = ast_find_symbol(repo, name or "", path)
        elif op == "find_references":
            rows = ast_find_references(repo, name or "", path)
        elif op == "symbol_span":
            rows = ast_symbol_span(repo, path or "", name or "") if path else []
        else:
            rows, err = ast_file_symbols(repo, path or "")
            if err:
                meta["warning"] = err
    elif sel["backend"] == "unavailable":
        return {"ok": False, "error": sel["reason"], "meta": meta}
    return {"ok": True, "meta": meta, "results": rows}


# ---------------------------------------------------------------- verification
def verify(repo: Path, rows: list[dict]) -> list[dict]:
    by_path: dict[str, dict] = {}
    for r in rows:
        want = r.get("source_digest")
        if want:
            by_path.setdefault(r["path"], {"digest": want, "count": 0})
            by_path[r["path"]]["count"] += 1
    state = {}
    for ps, info in by_path.items():
        p = repo / ps
        if not p.exists():
            state[ps] = "DELETED"
            continue
        state[ps] = "CURRENT" if digest_of(p) == info["digest"] else "CHANGED"
    out = []
    for r in rows:
        r2 = dict(r)
        r2["verification"] = state.get(r["path"], "UNKNOWN")
        out.append(r2)
    return out


def build_index(repo: Path, requested_backend: str | None) -> dict:
    """Whole-repo symbol artifact for retrieval_router provenance."""
    sel = resolve_backend(repo, requested_backend)
    backend = sel["backend"]
    serena_note = None
    if backend == "serena":
        try:
            rows = serena_run(repo, sel["argv"], "file_symbols", name=None, path=None)
            # whole-repo via serena needs per-file calls; fall through to ast for
            # coverage and keep serena rows (if any) first — both carry real digests.
            serena_rows = rows
        except SerenaBackendError as exc:
            serena_note = str(exc)
            serena_rows = []
        backend = "python-ast"
    else:
        serena_rows = []
    definitions, references, parse_errors = [], [], []
    for p in sorted(iter_py_files(repo)):
        ps = p.relative_to(repo).as_posix()
        rows, err = ast_file_symbols(repo, ps)
        if err:
            parse_errors.append({"path": ps, "error": err})
            continue
        definitions.extend(rows)
        digest = digest_of(p)
        tree, _ = parse_file(p)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                references.append(_row(ps, node.id, "name", node.lineno, node.lineno,
                                       digest, "reference", "python-ast"))
            elif isinstance(node, ast.Attribute):
                references.append(_row(ps, node.attr, "attribute", node.lineno,
                                       node.lineno, digest, "attribute_reference", "python-ast"))
            elif isinstance(node, ast.ClassDef):
                for base in node.bases:
                    bname = base.id if isinstance(base, ast.Name) else (
                        base.attr if isinstance(base, ast.Attribute) else None)
                    if bname:
                        references.append(_row(ps, bname, "class", node.lineno,
                                               node.lineno, digest, "inherits", "python-ast"))
    artifact = {
        "artifact_type": "SYMBOL_SPANS",
        "backend": backend,
        "backend_selection_reason": sel["reason"],
        "serena_attempt": serena_note,
        "repository_root": str(repo),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "definitions": serena_rows + definitions,
        "references": references,
        "parse_errors": parse_errors,
        "counts": {"definitions": len(serena_rows) + len(definitions),
                   "references": len(references)},
    }
    return artifact


def _load_index(repo: Path) -> dict:
    p = repo / ARTIFACT
    if not p.exists():
        raise SystemExit("no %s — run `symbol_backend.py index --repo R` first" % ARTIFACT)
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise SystemExit("unreadable symbol spans artifact: %s" % exc)
    if data.get("artifact_type") != "SYMBOL_SPANS":
        raise SystemExit("not a SYMBOL_SPANS artifact")
    return data


# ---------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="Symbol intelligence interface (pluggable backends).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def repo_arg(p):
        p.add_argument("--repo", required=True)
        p.add_argument("--backend", default=None, choices=["serena", "python-ast"],
                       help="force a backend (default: configured LSP, else python-ast)")
        p.add_argument("--json", action="store_true")

    p = sub.add_parser("find-symbol"); repo_arg(p); p.add_argument("--name", required=True); p.add_argument("--path")
    p = sub.add_parser("find-references"); repo_arg(p); p.add_argument("--name", required=True); p.add_argument("--path")
    p = sub.add_parser("symbol-span"); repo_arg(p); p.add_argument("--path", required=True); p.add_argument("--name", required=True)
    p = sub.add_parser("file-symbols"); repo_arg(p); p.add_argument("--path", required=True)
    p = sub.add_parser("verify")
    p.add_argument("--repo", required=True); p.add_argument("--spans-file", required=True)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("index"); repo_arg(p)
    p = sub.add_parser("query-index")
    p.add_argument("--repo", required=True); p.add_argument("--name", required=True)
    p.add_argument("--json", action="store_true")

    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print("error: %s is not a directory" % repo, file=sys.stderr)
        return 3

    if args.cmd == "index":
        artifact = build_index(repo, args.backend)
        out = repo / ARTIFACT
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(artifact, indent=2))
        if args.json:
            print(json.dumps({"ok": True, "artifact": str(out),
                              "backend": artifact["backend"],
                              "backend_selection_reason": artifact["backend_selection_reason"],
                              "counts": artifact["counts"],
                              "serena_attempt": artifact["serena_attempt"]}, indent=2))
        else:
            print("backend: %s (%s)" % (artifact["backend"], artifact["backend_selection_reason"]))
            print("definitions: %d  references: %d  parse_errors: %d" % (
                artifact["counts"]["definitions"], artifact["counts"]["references"],
                len(artifact["parse_errors"])))
            print("artifact: %s" % out)
        return 0

    if args.cmd == "query-index":
        data = _load_index(repo)
        defs = [d for d in data["definitions"] if d["symbol"] == args.name]
        refs = [r for r in data["references"] if r["symbol"] == args.name]
        verified = verify(repo, defs + refs)
        print(json.dumps({"backend": data["backend"], "definitions": defs,
                          "references": refs, "verification": {
                              r["path"]: r["verification"] for r in verified}},
                         indent=2))
        return 0

    if args.cmd == "verify":
        rows = json.loads(Path(args.spans_file).read_text())
        if isinstance(rows, dict):
            rows = rows.get("results", [])
        print(json.dumps({"results": verify(repo, rows)}, indent=2))
        return 0

    op = {"find-symbol": "find_symbol", "find-references": "find_references",
          "symbol-span": "symbol_span", "file-symbols": "file_symbols"}[args.cmd]
    out = run_op(repo, op, getattr(args, "name", None), getattr(args, "path", None),
                 args.backend)
    if args.json or True:
        print(json.dumps(out, indent=2))
    return 0 if out["ok"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
