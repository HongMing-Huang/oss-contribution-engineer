#!/usr/bin/env python3
"""v9_serena_run.py — V9 §4: run the REAL Serena/LSP backend on non-Python repos.

Launches the serena-agent MCP server (installed in dev/v9/.venv, inside the
working tree — nothing machine-wide) once per repository and exercises, through
the SAME mcp_stdio_client + symbol_backend adapter the Python backend uses:

  - find_symbol            (definition lookup + span)
  - find_referencing_symbols (reference lookup)
  - get_symbols_overview   (file symbols / symbol localization)

Measured per operation: latency; plus fallback behavior when the language
server cannot start. Output: runs/serena-runs.jsonl rows.

Usage:
  python3 v9_serena_run.py --repo ../v8/work/vite@ba8b7ab43b --lang typescript \
      --symbol ImportAnalysisPlugin --file src/node/plugins/importAnalysis.ts
  python3 v9_serena_run.py --repo ../v8/work/gin@d8f2d588d7 --lang go \
      --symbol getValue --file tree.go
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_SCRIPTS = HERE.parent.parent / "oss-contribution-engineer" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

from mcp_stdio_client import McpStdioClient, McpError, McpUnavailable  # noqa: E402

SERENA = HERE / ".venv" / "bin" / "serena"


def serena_command(repo: Path) -> list[str]:
    # language servers live in the workdir (lsp-bin/, lsp-npm/) — embed PATH in
    # the child env so serena finds gopls/typescript-language-server without
    # depending on the caller's shell
    lsp_path = ":".join([str(HERE / "lsp-bin"), str(HERE / "lsp-npm" / "node_modules" / ".bin")])
    return ["/usr/bin/env", "env", "PATH=%s:%s" % (lsp_path, PATH_tail()),
            str(SERENA), "start-mcp-server",
            "--project", str(repo), "--transport", "stdio",
            "--context", "desktop-app"]


def PATH_tail() -> str:
    import os
    return os.environ.get("PATH", "")


def error_in_payload(res: dict) -> str | None:
    text = res.get("text", "")
    if text.startswith("Error executing tool"):
        return text[:300]
    return None


def timed(fn, *a, **kw):
    t0 = time.monotonic()
    try:
        out = fn(*a, **kw)
        err = error_in_payload(out) if isinstance(out, dict) else None
        if err:
            return None, int((time.monotonic() - t0) * 1000), err
        return out, int((time.monotonic() - t0) * 1000), None
    except (McpError, McpUnavailable, OSError, ValueError) as exc:
        return None, int((time.monotonic() - t0) * 1000), str(exc)[:300]


def tool_payload(res: dict) -> list[dict]:
    """Serena returns text payload; parse JSON when possible, else return the
    raw text wrapped so the row stays inspectable."""
    text = res.get("text", "")
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        return [{"_text_head": text[:400]}]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--lang", required=True)
    ap.add_argument("--symbol", required=True, help="a real symbol in the repo")
    ap.add_argument("--file", required=True, help="repo-relative file for overview")
    ap.add_argument("--out", default=str(HERE / "runs" / "serena-runs.jsonl"))
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    row: dict = {
        "type": "SERENA_LSP_RUN",
        "repo": str(repo), "language": args.lang,
        "probe_symbol": args.symbol, "probe_file": args.file,
        "server": "serena-agent (venv in workdir, no machine install)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "operations": [], "backend": "serena-lsp",
    }

    client = McpStdioClient(serena_command(repo), cwd=str(repo),
                            request_timeout=240.0)
    t0 = time.monotonic()
    try:
        client.start()
    except (McpUnavailable, McpError, OSError) as exc:
        row["fallback"] = {"used": True,
                           "reason": "server start failed: %s" % str(exc)[:300]}
        _write(row, args)
        print(json.dumps(row, indent=2)[:800])
        return 4
    row["startup_ms"] = int((time.monotonic() - t0) * 1000)
    row["server_info"] = client.server_info
    tools = {t.get("name") for t in client.list_tools()}
    row["tools_available"] = sorted(t for t in tools if t)

    # 1. definition lookup (serena's schema rejects null params — omit them)
    find_args = {"name_path": args.symbol, "include_body": False}
    if args.file:
        find_args["relative_path"] = args.file
    res, ms, err = timed(client.call_tool, "find_symbol", find_args)
    defs = tool_payload(res) if res else []
    row["operations"].append({
        "op": "find_symbol", "target": args.symbol, "latency_ms": ms,
        "ok": err is None, "error": err,
        "matches": [{"path": m.get("relative_path"), "name": m.get("name"),
                     "kind": m.get("kind"),
                     "line": ((m.get("location") or {}).get("range")
                              or m.get("location") or {}).get("start")
                     if isinstance(m.get("location"), dict) else m.get("location")}
                    for m in defs[:6] if isinstance(m, dict)]})

    # 2. reference lookup (resolved structural relations)
    first = next((m for m in defs if isinstance(m, dict) and m.get("name_path")),
                 None) if defs else None
    if first:
        res, ms, err = timed(client.call_tool, "find_referencing_symbols", {
            "name_path": first.get("name_path", args.symbol),
            "relative_path": first.get("relative_path"),
            "include_body": False})
        refs = tool_payload(res) if res else []
        ref_rows = [m for m in refs if isinstance(m, dict)
                    and (m.get("references") or m.get("relative_path"))]
        row["operations"].append({
            "op": "find_referencing_symbols", "target": first.get("name_path"),
            "latency_ms": ms, "ok": err is None, "error": err,
            "reference_count": len(ref_rows[0].get("references", []))
            if ref_rows and isinstance(ref_rows[0].get("references"), list)
            else (len(refs) if refs else 0),
            "head": json.dumps(ref_rows[0] if ref_rows else refs[:1])[:500]})
    else:
        row["operations"].append({
            "op": "find_referencing_symbols", "target": args.symbol,
            "ok": False, "error": "no definition found to reference from",
            "latency_ms": 0})

    # 3. file symbol overview (localization)
    res, ms, err = timed(client.call_tool, "get_symbols_overview", {
        "relative_path": args.file})
    syms = tool_payload(res) if res else []
    row["operations"].append({
        "op": "get_symbols_overview", "target": args.file,
        "latency_ms": ms, "ok": err is None, "error": err,
        "symbol_count": len(syms) if isinstance(syms, list) else 0,
        "head": json.dumps(syms[:3])[:400]})

    client.close()
    row["source_binding"] = {
        "note": "spans come from the live LSP over current source; digests "
                "computed by the adapter would bind them per symbol_backend.py",
        "repo_head": hashlib.sha256("|".join(sorted(
            str(p.relative_to(repo)) for p in repo.rglob("*.go")
            if "vendor" not in str(p))).encode()).hexdigest()[:16]}
    _write(row, args)
    print(json.dumps(row, indent=2)[:1200])
    return 0


def _write(row: dict, args) -> None:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
