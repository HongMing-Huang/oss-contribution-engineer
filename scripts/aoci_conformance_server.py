#!/usr/bin/env python3
"""aoci_conformance_server.py — MCP stdio server implementing the AOCI runtime contract.

WHAT THIS IS: a stdlib MCP server that speaks the AOCI-CODE runtime contract as
verified against aoci-spec/aoci-code (spec/public/aoci-mcp-runtime-v1.txt,
aoci-overview-delivery-v1.txt, aoci-object-fras-v2.txt; commit 3604ce4, 2026-10-06):

  - the nine pinned tool names (aoci_rules, aoci_overview, aoci_search,
    aoci_get_entries, aoci_header, aoci_maintain, aoci_update_entry,
    aoci_remove_entry, aoci_report)
  - aoci_overview chunked whole-index delivery: cursor="start", next_cursor
    continuation, completion flag, per-chunk receipts (chunk_sha256, index_sha256,
    entry_count), final-chunk attestation challenge (challenge_ordinals,
    challenge_digest, ...), model_cognition_attestation grading (>=80% ordinals
    fully correct, F judged with Jaccard >= 0.6), host_delivery_confirmation as
    the second proof half
  - index identity (index_sha256 over length-framed volumes), refresh_generation,
    snapshot-change detection (overview_snapshot_changed)
  - aoci_search (keyword/tag_filter, max 30 results) and aoci_get_entries
    (paths, per-entry stale/unbaselined states via .aoci/baseline.json binding)

WHAT THIS IS NOT: the official AOCI-CODE binary. serverInfo.name is
"aoci-conformance", never "aoci-code". It is a contract-conformant service used to
exercise OUR client lifecycle end-to-end without downloading upstream (environment
constraint). Content authored into fixture indexes is mechanical and clearly
fixture-grade — AOCI governance ("model owns meaning") is respected by never
claiming fixture prose is real cognition.

Test-injection flags (for acceptance tests, disabled by default):
  --fail-chunk N        transport error on chunk N (partial delivery scenario)
  --drift-generation    advance index identity + refresh_generation on the FIRST
                        post-attestation read response (mid-session drift scenario)
  --enforce-overview    aoci_search before a passed attestation is refused
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

SERVER_NAME = "aoci-conformance"
SERVER_VERSION = "0.6.0"
PROTO = "2024-11-05"

TOOLS = ["aoci_rules", "aoci_overview", "aoci_search", "aoci_get_entries",
         "aoci_header", "aoci_maintain", "aoci_update_entry", "aoci_remove_entry",
         "aoci_report"]
PINNED_TOOL_SURFACE_SHA256 = "b4a56cb6d4e625189708e2132a45094eecc62a05c6a1bd4d06ddd0471598176e"

BEGIN = "<<<AOCI_OVERVIEW_BODY_BEGIN/v1 scope=%s>>>"
END = "<<<AOCI_OVERVIEW_BODY_END/v1 scope=%s>>>"
SEP = "<<<AOCI_OVERVIEW_CHUNK_BODY/v1>>>"
META = "<<<AOCI_OVERVIEW_CHUNK_META/v1>>>"

FRAS_RE = re.compile(r"^(\S+?)\[([^\]]*)\]:\s*F:(.*?)\s*\|\s*R:(.*?)\s*\|\s*A:(.*?)\s*\|\s*S:(.*)$")
DEFAULT_CHUNK_TOKENS = 7000
MIN_CHUNK, MAX_CHUNK = 4000, 24000
TOKENS_PER_CHAR = 4  # body_estimated_tokens ≈ utf8_bytes / 4


def length_framed(*fields: bytes) -> bytes:
    out = b""
    for f in fields:
        out += len(f).to_bytes(8, "big") + f
    return out


class ConformanceError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class Index:
    def __init__(self, repo: Path):
        self.repo = repo
        self.root = repo / "aoci.txt"
        self.code = repo / "aoci.code.txt"
        if not self.code.exists() and self.root.exists() and \
                self.root.read_text(errors="replace").lstrip().startswith("#AOCI-ROOT-MANIFEST:"):
            # volumes layout: resolve code volume path from the manifest
            for line in self.root.read_text(errors="replace").splitlines():
                m = re.match(r"^#Volume: .*kind=code path=(\S+)", line)
                if m:
                    self.code = repo / m.group(1)
                    break
        if not self.code.exists():
            raise ConformanceError("conformance.no_index",
                                   "no aoci.code.txt / aoci.txt root manifest in %s" % repo)
        self.text = self.code.read_text(errors="replace")
        self.entries = self._parse_entries()
        self.identity = self._composite_identity()
        self.entry_sequence = hashlib.sha256("\n".join(
            "%d:%s:%s" % (i + 1, e["object"], e["tag"]) for i, e in enumerate(self.entries)
        ).encode()).hexdigest()
        baseline = repo / ".aoci" / "baseline.json"
        self.baseline = {}
        if baseline.exists():
            try:
                self.baseline = (json.loads(baseline.read_text()) or {}).get("files", {}) or {}
            except json.JSONDecodeError:
                self.baseline = {}

    def _parse_entries(self) -> list[dict]:
        out = []
        for line in self.text.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("===") or s.startswith("<<<"):
                continue
            m = FRAS_RE.match(s)
            if m:
                out.append({"object": m.group(1), "tag": m.group(2),
                            "F": m.group(3).strip(), "R": m.group(4).strip(),
                            "A": m.group(5).strip(), "S": m.group(6).strip(),
                            "line": s})
        return out

    def _composite_identity(self) -> str:
        root_b = self.root.read_bytes() if self.root.exists() else b""
        code_b = self.code.read_bytes()
        return hashlib.sha256(length_framed(root_b, b"", code_b, b"")).hexdigest()


def jaccard(a: str, b: str) -> float:
    ta = set(re.findall(r"[a-z0-9]+", a.lower()))
    tb = set(re.findall(r"[a-z0-9]+", b.lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


class Session:
    def __init__(self, args):
        self.args = args
        self.index = Index(Path(args.repo).resolve())
        self.chunk_tokens = DEFAULT_CHUNK_TOKENS
        self.gen = 1
        self.delivered = False          # full chain delivered at least once
        self.attested = False           # challenge passed
        self.host_confirmed = False
        self.drift_armed = False        # inject identity drift on next read
        self.read_drift = None
        self.call_count = 0

    # ------------------------------------------------------------------ overview
    def plan_chunks(self) -> list[list[int]]:
        budget_chars = self.chunk_tokens * TOKENS_PER_CHAR
        groups, cur, cur_len = [], [], 0
        for i, e in enumerate(self.index.entries):
            n = len(e["line"]) + 1
            if n > budget_chars:
                raise ConformanceError("overview_entry_exceeds_chunk_budget",
                                       "entry %s exceeds chunk budget" % e["object"])
            if cur and cur_len + n > budget_chars:
                groups.append(cur)
                cur, cur_len = [], 0
            cur.append(i)
            cur_len += n
        if cur:
            groups.append(cur)
        return groups or [[]]

    def overview(self, params: dict) -> str:
        self.call_count += 1
        idx_now = self.index.identity
        scope = params.get("scope") or "all"
        cursor = params.get("cursor") or ""
        attestation_raw = params.get("model_cognition_attestation") or ""

        if attestation_raw:
            return self.grade_attestation(attestation_raw, idx_now)
        if params.get("host_delivery_confirmation"):
            self.host_confirmed = True
            if self.delivered:
                return self.finalize_if_possible(idx_now, scope)

        if not cursor or cursor == "start":
            plans = self.plan_chunks()
            return self.emit_chunk(plans, 0, idx_now, scope)
        parts = cursor.split(":")
        if len(parts) != 4:
            raise ConformanceError("overview_cursor_invalid", "cursor must have 4 parts")
        _, tokens_s, ordinal_s, prev_sha = parts
        if tokens_s != str(self.chunk_tokens):
            raise ConformanceError("overview_chunk_tokens_changed", "chunk budget changed")
        try:
            next_ordinal = int(ordinal_s)
        except ValueError:
            raise ConformanceError("overview_cursor_invalid", "bad ordinal")
        plans = self.plan_chunks()
        # which chunk holds entry ordinal next_ordinal (1-based)?
        flat = 0
        target = None
        seen = 0
        for ci, g in enumerate(plans):
            seen = flat
            flat += len(g)
            if next_ordinal <= flat:
                target = ci
                break
        if target is None:
            raise ConformanceError("overview_cursor_out_of_order", "ordinal past end")
        # chain integrity: cursor must carry the sha of the PREVIOUS chunk body
        want_prev = self.chunk_body_sha(plans, target - 1, idx_now) if target > 0 else "0" * 64
        if prev_sha != want_prev:
            raise ConformanceError("overview_cursor_chain_mismatch",
                                   "cursor prev-sha does not match delivered chain")
        return self.emit_chunk(plans, target, idx_now, scope)

    def chunk_body(self, plans, ci) -> str:
        return "\n".join(self.index.entries[i]["line"] for i in plans[ci])

    def chunk_body_sha(self, plans, ci, idx_now) -> str:
        if ci < 0:
            return "0" * 64
        return hashlib.sha256((idx_now + "\n" + self.chunk_body(plans, ci)).encode()).hexdigest()

    def emit_chunk(self, plans, ci, idx_now, scope) -> str:
        if self.args.fail_chunk and (ci + 1) == self.args.fail_chunk:
            raise ConformanceError("conformance.transport_failure",
                                   "injected transport failure at chunk %d" % (ci + 1))
        count = len(plans)
        body = self.chunk_body(plans, ci)
        last = ci == count - 1
        meta = {
            "delivery_mode": "full" if count == 1 else "chunked_full",
            "chunk_index": ci + 1, "chunk_count": count,
            "chunk_tokens": self.chunk_tokens,
            "first_entry_ordinal": plans[ci][0] + 1 if plans[ci] else 1,
            "last_entry_ordinal": plans[ci][-1] + 1 if plans[ci] else 0,
            "entry_count": len(self.index.entries),
            "index_sha256": idx_now,
            "entry_sequence_sha256": self.index.entry_sequence,
            "chunk_sha256": self.chunk_body_sha(plans, ci, idx_now),
            "body_utf8_bytes": len(body.encode()),
            "completed": last,
            "continuation_required": not last,
            "receipt_version": "overview-chunk-receipt/v1",
        }
        if last:
            meta["completed"] = True
            meta["continuation_required"] = False
            meta["attestation_contract_version"] = "model-cognition-attestation/v1"
            meta["server_delivery_complete"] = True
            meta["runtime_repository_root"] = str(self.index.repo)
            meta["scope"] = scope
            meta["scope_identity"] = idx_now
            meta["refresh_generation"] = str(self.gen)
            meta["mcp_service_version"] = SERVER_VERSION
            ords = self.challenge_ordinals()
            meta["challenge_version"] = "model-cognition-attestation/v1"
            meta["challenge_index_sha256"] = idx_now
            meta["challenge_entry_sequence_sha256"] = self.index.entry_sequence
            meta["challenge_entry_count"] = len(self.index.entries)
            meta["challenge_ordinals"] = ords
            meta["challenge_count"] = len(ords)
            meta["challenge_digest"] = hashlib.sha256(
                ("|".join(str(o) for o in ords)).encode()).hexdigest()
            self.delivered = True
            if self.args.drift_generation:
                self.drift_armed = True
        out = [BEGIN % scope]
        if count > 1:
            out.append(SEP)
        out.append(body)
        out.append(END % scope)
        out.append(META)
        out.append(json.dumps(meta, separators=(",", ":")))
        return "\n".join(out)

    def challenge_ordinals(self) -> list[int]:
        n = len(self.index.entries)
        if n <= 10:
            return list(range(1, n + 1))
        step = n / 10.0
        return sorted({min(n, max(1, int(i * step) + 1)) for i in range(10)})

    def grade_attestation(self, raw: str, idx_now: str) -> str:
        try:
            att = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            raise ConformanceError("overview_cursor_invalid", "attestation not JSON")
        if att.get("index_sha256") != idx_now or \
                att.get("challenge_digest") != hashlib.sha256(
                    ("|".join(str(o) for o in self.challenge_ordinals())).encode()).hexdigest():
            raise ConformanceError("overview_snapshot_changed",
                                   "attestation bound to a different index snapshot")
        ords = self.challenge_ordinals()
        by_ord = {a.get("ordinal"): a for a in att.get("challenge_answers", [])
                  if isinstance(a, dict)}
        correct = 0
        for o in ords:
            a = by_ord.get(o)
            if not a:
                continue
            e = self.index.entries[o - 1]
            if a.get("object_identity") == e["object"] and \
                    a.get("tag") == e["tag"] and jaccard(a.get("f", ""), e["F"]) >= 0.6:
                correct += 1
        total = len(ords)
        passed = total > 0 and correct / total >= 0.8 and \
            att.get("entry_count") == len(self.index.entries)
        self.attested = self.attested or passed
        return "\n".join([META, json.dumps({
            "attestation_result": {
                "ChallengePassed": passed, "ChallengeTotal": total,
                "ChallengeCorrect": correct,
                "DeliveryIntegrity": True, "ModelAttestation": True,
            },
            "completed": True, "continuation_required": False,
            "index_sha256": idx_now, "refresh_generation": str(self.gen),
            "cognition_state": "COMPLETE" if passed else "ATTESTATION_FAILED",
            "model_full_cognition_reliable": passed,
            "entry_count": len(self.index.entries),
            "scope_identity": idx_now,
            "runtime_repository_root": str(self.index.repo),
            "mcp_service_version": SERVER_VERSION,
            "receipt_version": "overview-delivery-receipt/v1",
        }, separators=(",", ":"))])

    def finalize_if_possible(self, idx_now, scope) -> str:
        return "\n".join([META, json.dumps({
            "host_delivery_accepted": True, "index_sha256": idx_now,
            "cognition_state": "COMPLETE" if (self.attested and self.host_confirmed)
            else "PARTIAL"}, separators=(",", ":"))])

    # ------------------------------------------------------------------ reads
    def search(self, params: dict) -> str:
        if self.args.enforce_overview and not self.attested:
            raise ConformanceError("conformance.overview_required",
                                   "whole-index cognition must complete before aoci_search")
        keyword = (params.get("keyword") or "").lower()
        tag_filter = params.get("tag_filter") or ""
        if not keyword and not tag_filter:
            raise ConformanceError("mcp.entries.missing_input",
                                   "keyword or tag_filter required")
        hits = []
        for e in self.index.entries:
            if keyword and keyword not in e["line"].lower():
                continue
            if tag_filter and not self.tag_matches(e["tag"], tag_filter):
                continue
            hits.append(e)
        return "\n".join([META, json.dumps({
            "results": [{"object": h["object"], "path": h["object"], "tag": h["tag"],
                         "line": h["line"]} for h in hits[:30]],
            "total": len(hits), "index_sha256": self.current_identity(),
            "refresh_generation": str(self.gen),
        }, separators=(",", ":"))])

    @staticmethod
    def tag_matches(tag: str, flt: str) -> bool:
        m = re.fullmatch(r"([ABCD])(>=|<=|=)(\d+)", flt.strip())
        if not m:
            return flt in tag
        k, op, v = m.group(1), m.group(2), int(m.group(3))
        mm = re.search(r"%s(\d)" % k, tag)
        if not mm:
            return False
        c = int(mm.group(1))
        return {"=": c == v, ">=": c >= v, "<=": c <= v}[op]

    def get_entries(self, params: dict) -> str:
        if self.args.enforce_overview and not self.attested:
            raise ConformanceError("conformance.overview_required",
                                   "whole-index cognition must complete before aoci_get_entries")
        paths = params.get("paths") or []
        if isinstance(paths, str):
            paths = [p for p in paths.split(",") if p]
        if not paths and not params.get("dir"):
            raise ConformanceError("mcp.entries.missing_input",
                                   "paths or dir required")
        if paths:
            wanted = list(paths)
        else:
            d = params.get("dir").strip("/")
            wanted = [e["object"] for e in self.index.entries
                      if e["object"].startswith(d + "/")][:50]
        out = []
        for p in wanted[:50]:
            e = next((x for x in self.index.entries if x["object"] == p), None)
            if not e:
                out.append({"path": p, "state": "mcp.entries.missing"})
                continue
            b = self.index.baseline.get(p) or self.index.baseline.get("./" + p) or {}
            src = self.index.repo / p
            row = {"path": p, "tag": e["tag"], "line": e["line"],
                   "index_sha256": self.current_identity(),
                   "refresh_generation": str(self.gen)}
            if src.exists():
                cur = hashlib.sha256(src.read_bytes()).hexdigest()
                row["source_sha256"] = b.get("sha256", "")
                row["current_source_sha256"] = cur
                row["state"] = "current" if (not b or b.get("sha256") == cur) \
                    else "mcp.entries.stale"
            else:
                row["state"] = "mcp.entries.missing"
            if not b and src.exists():
                row["state"] = "mcp.entries.unbaselined"
            out.append(row)
        return "\n".join([META, json.dumps({"entries": out}, separators=(",", ":"))])

    def current_identity(self) -> str:
        if self.drift_armed:
            # one-shot mid-session drift: identity + generation advance on the
            # first post-attestation read response
            self.drift_armed = False
            self.gen += 1
            self.read_drift = hashlib.sha256(
                (self.index.identity + ":drifted").encode()).hexdigest()
        return self.read_drift or self.index.identity

    # ------------------------------------------------------------------ rules
    def rules(self) -> str:
        return (
            "AOCI Runtime Contract (session level) — conformance copy\n"
            "Upstream authority: aoci-spec/aoci-code spec/public/aoci-mcp-runtime-v1.txt\n"
            "1. Call aoci_rules once per session.\n"
            "2. Call aoci_overview; while continuation_required=true, auto-submit the\n"
            "   exact next_cursor until completed=true. Never substitute search,\n"
            "   entry reads, memory, or source files for the complete Whole-Index.\n"
            "3. Complete the attestation challenge; host_delivery_confirmation and\n"
            "   model_cognition_attestation are the two proof halves.\n"
            "4. aoci_search / aoci_get_entries are for local uncertainty only, AFTER\n"
            "   whole-index cognition. They never replace or repair the overview.\n"
            "5. Model owns meaning; the runtime owns governance. F/R/A/S prose is\n"
            "   model-authored only. All-green checks prove structural contracts,\n"
            "   not semantic correctness.\n"
            "conformance_note: this service implements the documented contract for\n"
            "client integration testing; it is not the official aoci-code binary.\n")

    def header(self) -> str:
        return "#AOCI-META-VOLUME: 1 (conformance fixture header)"


def dispatch(sess: Session, method: str, params: dict, tools_enabled: bool):
    if method == "initialize":
        return {"protocolVersion": PROTO, "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION}}
    if method == "tools/list":
        if not tools_enabled:
            return {"tools": []}
        return {"tools": [{"name": t, "description": "AOCI conformance tool: %s" % t,
                           "inputSchema": {"type": "object"}} for t in TOOLS]}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if not tools_enabled:
            raise ConformanceError("conformance.tools_disabled", "tools disabled by flag")
        if name == "aoci_rules":
            text = sess.rules()
        elif name == "aoci_header":
            text = sess.header()
        elif name == "aoci_overview":
            text = sess.overview(args)
        elif name == "aoci_search":
            text = sess.search(args)
        elif name == "aoci_get_entries":
            text = sess.get_entries(args)
        elif name in ("aoci_maintain", "aoci_update_entry", "aoci_remove_entry",
                      "aoci_report"):
            text = "\n".join([META, json.dumps(
                {"conformance": "write-path tool present for surface fidelity; not exercised"},
                separators=(",", ":"))])
        else:
            raise ConformanceError("conformance.unknown_tool", name or "")
        return {"content": [{"type": "text", "text": text}], "isError": False}
    raise ConformanceError("conformance.unknown_method", method)


def serve(args) -> int:
    sess = Session(args)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "id" not in msg or "method" not in msg:
            continue  # notification
        try:
            result = dispatch(sess, msg["method"], msg.get("params") or {},
                              tools_enabled=not args.no_tools)
            resp = {"jsonrpc": "2.0", "id": msg["id"], "result": result}
        except ConformanceError as exc:
            resp = {"jsonrpc": "2.0", "id": msg["id"],
                    "error": {"code": -32000, "message": str(exc), "data": {"code": exc.code}}}
        except Exception as exc:  # fail closed, never crash the wire
            resp = {"jsonrpc": "2.0", "id": msg["id"],
                    "error": {"code": -32603, "message": str(exc)[:300],
                              "data": {"code": "conformance.internal"}}}
        sys.stdout.write(json.dumps(resp, separators=(",", ":")) + "\n")
        sys.stdout.flush()
    return 0


def build_fixture(args) -> int:
    """Mechanical fixture index over a repo: root manifest + code volume + baseline.
    F lines are fixture placeholders quoting the file's first line — they exercise
    transport/cursor/attestation mechanics and are NOT model-authored cognition."""
    repo = Path(args.repo).resolve()
    files = []
    for dirpath, dirnames, filenames in os.walk(repo):
        rel = Path(dirpath).relative_to(repo).as_posix()
        if rel != "." and (rel.split("/")[0] in SKIP or rel.startswith(".")):
            dirnames[:] = []
            continue
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP and not d.startswith("."))
        for fn in sorted(filenames):
            if fn.endswith((".pyc", ".lock")) or fn.startswith("."):
                continue
            p = Path(dirpath) / fn
            if p.stat().st_size <= 200_000:
                files.append(p.relative_to(repo).as_posix())
    vol_lines = ["#AOCI-CODE-VOLUME: 1", "#Object-Protocol: repository-cognition-object/v2", ""]
    baseline_files = {}
    cur_dir = None
    for rel in sorted(files):
        d = "/".join(rel.split("/")[:-1])
        if d != cur_dir:
            vol_lines.append("===/%s/===" % d)
            cur_dir = d
        try:
            first = next((ln.strip() for ln in (repo / rel).read_text(errors="replace").splitlines()
                          if ln.strip()), "(empty)")
        except OSError:
            first = "(unreadable)"
        fline = "%s[EG5T]: F:fixture: %s | R:- | A:- | S:-" % (rel, first[:120])
        vol_lines.append(fline)
        baseline_files[rel] = {"role": "source",
                               "sha256": hashlib.sha256((repo / rel).read_bytes()).hexdigest(),
                               "size": (repo / rel).stat().st_size}
    (repo / "aoci.code.txt").write_text("\n".join(vol_lines) + "\n")
    (repo / "aoci.txt").write_text(
        "#AOCI-ROOT-MANIFEST: 1\n#Format-Version: cognition-volumes/v1\n"
        "#Locale: en-US\n#Project: conformance-fixture\n"
        "#Volume: id=code kind=code path=aoci.code.txt format=object-fras-v2 depends=meta state=enabled\n")
    adir = repo / ".aoci"
    adir.mkdir(exist_ok=True)
    (adir / "baseline.json").write_text(json.dumps(
        {"version": 1, "files": baseline_files}, indent=2))
    print(json.dumps({"ok": True, "entries": len(files),
                      "code_volume": str(repo / "aoci.code.txt")}))
    return 0


SKIP = {".git", "__pycache__", ".venv", "venv", ".oss-contrib-evidence", ".aoci",
        ".mimosa", "node_modules", ".pytest_cache", ".mypy_cache"}


def main() -> int:
    ap = argparse.ArgumentParser(description="AOCI contract conformance MCP stdio server.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--repo", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--repo", required=True)
    s.add_argument("--fail-chunk", type=int, default=0)
    s.add_argument("--drift-generation", action="store_true")
    s.add_argument("--enforce-overview", action="store_true")
    s.add_argument("--no-tools", action="store_true")
    ap.add_argument("--build", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.cmd == "build":
        return build_fixture(args)
    return serve(args)


if __name__ == "__main__":
    raise SystemExit(main())
