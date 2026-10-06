#!/usr/bin/env python3
"""mcp_stdio_client.py — minimal MCP (Model Context Protocol) stdio client, stdlib-only.

Speaks the documented MCP transport: JSON-RPC 2.0, one message per line over the
child process's stdin/stdout. This is the client boundary — we never parse a
backend's internal files or scrape its output to fake a session.

Why hand-rolled: the runtime environment is stdlib-only (no MCP SDK, no network
install). The MCP stdio transport is a small documented wire format; a ~200-line
client IS the MCP client path here. It is transport-generic and backend-agnostic —
backends (AOCI runtime, Serena, any MCP server) are addressed purely through
initialize / tools/list / tools/call.

Launch contract (mirrors evidence_manifest.py): the spawned argv is anchored at a
literal "/usr/bin/env" head with shell=False; resolve_command() normalizes every
configured server command into that shape before it reaches a spawn site, so no
shell is involved anywhere.

Exit codes: 0 ok, 2 usage, 4 backend-unavailable (caller decides fallback).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import sys
import threading
import queue
from typing import Optional

PROTOCOL_VERSION = "2024-11-05"
CLIENT_INFO = {"name": "oss-contribution-engineer", "version": "6.0"}


class McpError(RuntimeError):
    pass


class McpUnavailable(RuntimeError):
    """Server could not be launched or did not complete initialization."""


class McpStdioClient:
    """argv must be a non-empty list whose head is the literal "/usr/bin/env"
    (resolve_command() enforces this)."""

    def __init__(self, argv: list[str], cwd: Optional[str] = None,
                 request_timeout: float = 60.0):
        if not argv or argv[0] != "/usr/bin/env":
            raise ValueError('argv must start with the literal "/usr/bin/env"')
        self.argv = list(argv)
        self.cwd = cwd
        self.request_timeout = request_timeout
        self.proc: Optional[subprocess.Popen] = None
        self.server_info: dict = {}
        self.protocol_version: str = ""
        self._next_id = 1
        self._out_q: "queue.Queue[Optional[str]]" = queue.Queue()
        self._err_buf: list[str] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ plumbing
    def start(self) -> dict:
        try:
            self.proc = subprocess.Popen(
                ["/usr/bin/env", *self.argv[1:]],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, shell=False, cwd=self.cwd,
                bufsize=1)
        except OSError as exc:
            raise McpUnavailable("cannot launch %s: %s"
                                 % (self.argv[1] if len(self.argv) > 1 else "?", exc))
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._err_drain, daemon=True).start()
        result = self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": CLIENT_INFO,
        })
        self.protocol_version = result.get("protocolVersion", PROTOCOL_VERSION)
        self.server_info = result.get("serverInfo", {})
        self._notify("notifications/initialized", {})
        return {"server_info": self.server_info, "protocol_version": self.protocol_version}

    def _reader(self):
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            self._out_q.put(line)
        self._out_q.put(None)

    def _err_drain(self):
        assert self.proc and self.proc.stderr
        for line in self.proc.stderr:
            with self._lock:
                self._err_buf.append(line)
            if len(self._err_buf) > 200:
                del self._err_buf[:-100]

    def _send(self, obj: dict):
        assert self.proc and self.proc.stdin
        try:
            self.proc.stdin.write(json.dumps(obj, separators=(",", ":")) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, ValueError):
            raise McpUnavailable("server stdin closed")

    def _notify(self, method: str, params: dict):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: dict) -> dict:
        rid = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        while True:
            try:
                line = self._out_q.get(timeout=self.request_timeout)
            except queue.Empty:
                raise McpError("timeout waiting for response to %s (id=%d)" % (method, rid))
            if line is None:
                raise McpUnavailable("server exited before answering %s%s"
                                     % (method, self._stderr_tail()))
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue  # not a wire message; skip
            if msg.get("id") != rid or ("result" not in msg and "error" not in msg):
                continue  # notification or unrelated response
            if "error" in msg:
                err = msg["error"]
                raise McpError("%s error %s: %s" % (method, err.get("code"), err.get("message")))
            return msg.get("result", {})

    def _stderr_tail(self) -> str:
        with self._lock:
            tail = "".join(self._err_buf[-5:]).strip()
        return ("; stderr: %s" % tail[:400]) if tail else ""

    # ------------------------------------------------------------------ MCP surface
    def list_tools(self) -> list[dict]:
        result = self._request("tools/list", {})
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: Optional[dict] = None) -> dict:
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}})
        content = result.get("content", []) or []
        texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        return {
            "is_error": bool(result.get("isError")),
            "text": "\n".join(t for t in texts if t),
            "structured": result.get("structuredContent"),
            "raw": result,
        }

    def call_tool_json(self, name: str, arguments: Optional[dict] = None) -> dict:
        """call_tool + parse the text payload as JSON (our backends return JSON)."""
        out = self.call_tool(name, arguments)
        if out["is_error"]:
            raise McpError("tool %s returned isError: %s" % (name, out["text"][:300]))
        payload = out["structured"] if isinstance(out["structured"], dict) else None
        if payload is None:
            try:
                payload = json.loads(out["text"])
            except json.JSONDecodeError:
                raise McpError("tool %s returned non-JSON payload" % name)
        if not isinstance(payload, dict):
            raise McpError("tool %s returned non-object payload" % name)
        return payload

    def close(self):
        if not self.proc:
            return
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def resolve_command(spec: str) -> list[str]:
    """Turn a configured command string into a literal-head argv list.

    Whatever the operator configures, the spawned argv head is always the literal
    "/usr/bin/env", so no shell is ever involved.
    """
    parts = shlex.split(spec)
    if not parts:
        raise ValueError("empty command spec")
    if parts[0] == "/usr/bin/env":
        return parts
    return ["/usr/bin/env"] + parts


def tool_surface_digest(tools: list[str]) -> str:
    """AOCI pins its tool surface as sha256 over sorted LF-joined names WITH a
    trailing newline (verified against the pinned constant in
    aoci-spec/aoci-code spec/public/aoci-mcp-runtime-v1.txt)."""
    return hashlib.sha256(("\n".join(sorted(tools)) + "\n").encode()).hexdigest()


def probe(argv: list[str], cwd: Optional[str] = None,
          request_timeout: float = 20.0) -> dict:
    """Launch, initialize, list tools, close. Returns an availability report."""
    try:
        with McpStdioClient(argv, cwd=cwd, request_timeout=request_timeout) as client:
            tools = client.list_tools()
            return {
                "available": True,
                "server_info": client.server_info,
                "protocol_version": client.protocol_version,
                "tools": sorted(t.get("name", "") for t in tools),
                "argv_head": argv[0],
            }
    except (McpUnavailable, McpError, OSError, ValueError) as exc:
        return {"available": False, "reason": str(exc)[:400], "argv_head": argv[0] if argv else None}


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe an MCP stdio server.")
    ap.add_argument("command", help='command string, e.g. "python3 aoci_conformance_server.py --repo ."')
    ap.add_argument("--cwd", default=None)
    args = ap.parse_args()
    argv = resolve_command(args.command)
    report = probe(argv, cwd=args.cwd)
    print(json.dumps(report, indent=2))
    return 0 if report["available"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
