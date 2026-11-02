#!/usr/bin/env python3
"""aoci_runtime.py — AOCI_RUNTIME backend: a real client of a real AOCI runtime.

Talks to an AOCI MCP server over stdio (mcp_stdio_client.py) and enforces the
runtime contract verified against aoci-spec/aoci-code (spec/public/
aoci-mcp-runtime-v1.txt + aoci-overview-delivery-v1.txt, commit 3604ce4, 2026-10-06):

    aoci_rules
      → aoci_overview with cursor="start"
      → follow EVERY next_cursor until completed=true (never skip the chain)
      → submit model_cognition_attestation + host_delivery_confirmation
        (the two proof halves of the delivered body)
      → capture the cognition receipt / identity
      → only then permit aoci_search / aoci_get_entries

Authority boundaries respected (these are the client's duties — the real server
does NOT mechanically enforce them):
  - search never substitutes for or precedes whole-index completion;
  - a partial overview can NEVER masquerade as complete cognition (cognition_state
    stays PARTIAL and reads stay gated);
  - index identity (index_sha256) and refresh_generation are checked on every
    post-overview response; a mismatch invalidates the receipt (drift);
  - aoci.code.txt files are parsed only as AOCI_FILE compatibility elsewhere —
    this module treats the SERVICE as the runtime, never the files.

The official aoci-code binary is NOT bundled (environment constraint: no
downloads). Point this client at any contract-conformant server via
AOCI_MCP_COMMAND / .oss-contrib-evidence/aoci_runtime.json / --mcp-command.
scripts/aoci_conformance_server.py is our own contract-conformant service for
integration runs; its serverInfo.name says "aoci-conformance", never "aoci-code".

If the runtime is unavailable the session artifact records an EXPLICIT fallback
(runtime_attempted=true, runtime_used=false, reason) — retrieval_router.py only
upgrades to AOCI_RUNTIME when the receipt proves a COMPLETE cognition pass.

Exit codes: 0 ok (including explicit fallback), 2 usage, 3 repo error,
4 runtime unavailable and no fallback artifact was writable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mcp_stdio_client import (McpStdioClient, McpError, McpUnavailable,
                              resolve_command, tool_surface_digest)  # noqa: E402

# Pinned AOCI surface (spec/public/aoci-mcp-runtime-v1.txt): sha256 of the sorted
# LF-joined tool names. A server not matching this is not an AOCI runtime.
PINNED_TOOLS = ["aoci_rules", "aoci_overview", "aoci_search", "aoci_get_entries",
                "aoci_header", "aoci_maintain", "aoci_update_entry", "aoci_remove_entry",
                "aoci_report"]
PINNED_SURFACE_SHA256 = "b4a56cb6d4e625189708e2132a45094eecc62a05c6a1bd4d06ddd0471598176e"
SERVER_NAME = "aoci-code"  # official serverInfo.name per machinecontract/capabilities.go

MAX_OVERVIEW_CALLS = 60
SESSION_ARTIFACT = ".oss-contrib-evidence/aoci_runtime_session.json"
FRAS_RE = re.compile(r"^(\S+?)\[([^\]]*)\]:\s*F:(.*?)\s*\|\s*R:(.*?)\s*\|\s*A:(.*?)\s*\|\s*S:(.*)$")
META_TAG = "<<<AOCI_OVERVIEW_CHUNK_META"
BEGIN_TAG = "<<<AOCI_OVERVIEW_BODY_BEGIN"


# ---------------------------------------------------------------- config
def resolve_mcp_command(repo: Path, cli_value: str | None) -> list[str] | None:
    spec = cli_value or os.environ.get("AOCI_MCP_COMMAND")
    if not spec:
        cfg = repo / ".oss-contrib-evidence" / "aoci_runtime.json"
        if cfg.exists():
            try:
                spec = (json.loads(cfg.read_text()) or {}).get("mcp_command") or ""
            except (json.JSONDecodeError, OSError):
                spec = ""
    return resolve_command(spec) if spec else None


# ---------------------------------------------------------------- payload parsing
def parse_overview_payload(text: str) -> tuple[dict | None, list[str]]:
    meta, body, in_meta, in_body = None, [], False, False
    for ln in text.splitlines():
        if ln.startswith(META_TAG):
            in_meta, in_body = True, False
            continue
        if in_meta:
            if meta is None:
                try:
                    meta = json.loads(ln)
                except json.JSONDecodeError:
                    meta = {"parse_error": ln[:200]}
            continue
        if ln.startswith(BEGIN_TAG):
            in_body = True
            continue
        if ln.startswith("<<<AOCI_OVERVIEW_BODY_END"):
            in_body = False
            continue
        if ln.startswith("<<<"):
            continue
        if in_body:
            body.append(ln)
    return meta, body


def parse_fras(body_lines: list[str], first_ordinal: int) -> list[dict]:
    out = []
    for i, ln in enumerate(body_lines):
        m = FRAS_RE.match(ln.strip())
        if m:
            out.append({"ordinal": first_ordinal + i, "object": m.group(1),
                        "tag": m.group(2), "f": m.group(3).strip(),
                        "r": m.group(4).strip(), "a": m.group(5).strip(),
                        "line": ln.strip()})
    return out


def _meta_json(text: str) -> dict:
    for ln in text.splitlines():
        if ln.startswith(META_TAG):
            rest = "\n".join(text.splitlines()[text.splitlines().index(ln) + 1:])
            try:
                return json.loads(rest.strip().splitlines()[0])
            except (json.JSONDecodeError, IndexError):
                return {"parse_error": rest[:200]}
    return {}


# ---------------------------------------------------------------- session
def open_session(repo: Path, argv: list[str], scope: str,
                 keep_client: bool = False):
    """Run the full lifecycle. Returns the session artifact (never raises for
    runtime-side failures — those become explicit fallback records).

    keep_client=True also returns the live McpStdioClient so post-cognition reads
    happen on the SAME connection (attestation state is per-connection, as in the
    real runtime session protocol). Caller must close it."""
    t0 = datetime.now(timezone.utc)
    art = {
        "artifact_type": "AOCI_RUNTIME_SESSION",
        "backend": None,                     # filled when a runtime is actually used
        "runtime_repository_root": str(repo),
        "requested_scope": scope,
        "mcp_server_info": None,
        "mcp_service_version": None,
        "index_identity": None,
        "scope_identity": None,
        "generation": None,
        "scope": None,
        "alignment_state": "unknown",
        "cognition_state": "NOT_STARTED",
        "rules_digest": None,
        "overview_chunks": [],
        "attestation": None,
        "entry_count": None,
        "entries_snapshot": {},
        "receipt_digest": None,
        "generated_at": t0.isoformat(),
        "latency_ms": None,
        "fallback": None,
    }
    tool_errs: list[str] = []

    def fail(reason: str, fallback_to: str) -> dict:
        art["cognition_state"] = "FALLBACK"
        art["fallback"] = {"runtime_attempted": True, "runtime_used": False,
                           "fallback_backend": fallback_to, "reason": reason[:500],
                           "tool_errors": tool_errs[:10]}
        art["latency_ms"] = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
        _write(repo, art)
        return art

    # -- surface verification -------------------------------------------------
    try:
        client = McpStdioClient(argv, cwd=str(repo), request_timeout=90.0)
        client.start()
    except (McpUnavailable, McpError, ValueError, OSError) as exc:
        return fail("launch/initialize failed: %s" % exc, "AOCI_FILE")
    try:
        art["mcp_server_info"] = client.server_info
        art["mcp_service_version"] = (client.server_info or {}).get("version")
        tools = sorted(t.get("name", "") for t in client.list_tools())
        surface = tool_surface_digest(tools)
        art["tool_surface"] = {"tools": tools, "sha256": surface,
                               "matches_pinned_aoci": surface == PINNED_SURFACE_SHA256}
        if surface != PINNED_SURFACE_SHA256:
            return fail("tool surface %s does not match the pinned AOCI contract %s"
                        % (surface[:16], PINNED_SURFACE_SHA256[:16]), "AOCI_FILE")
        if (client.server_info or {}).get("name") == SERVER_NAME:
            art["backend"] = "aoci-official"
        else:
            # disclosed, never impersonated: conformance/compatible servers are
            # recorded under their own name
            art["backend"] = "aoci-contract-compatible:%s" % (client.server_info or {}).get("name")
    except (McpError, McpUnavailable) as exc:
        client.close()
        return fail("tools/list failed: %s" % exc, "AOCI_FILE")

    # -- 1. rules -------------------------------------------------------------
    try:
        rules_out = client.call_tool("aoci_rules", {})
        if rules_out["is_error"]:
            raise McpError(rules_out["text"][:300])
        art["rules_digest"] = hashlib.sha256(rules_out["text"].encode()).hexdigest()
    except (McpError, McpUnavailable) as exc:
        client.close()
        return fail("aoci_rules failed: %s" % exc, "AOCI_FILE")

    # -- 2/3. overview chain ----------------------------------------------------
    identity = None
    entries: list[dict] = []
    challenge = None
    receipt = None
    cursor = "start"
    try:
        for _ in range(MAX_OVERVIEW_CALLS):
            out = client.call_tool("aoci_overview", {"scope": scope, "cursor": cursor})
            if out["is_error"]:
                raise McpError("aoci_overview error: %s" % out["text"][:300])
            meta, body = parse_overview_payload(out["text"])
            if not meta:
                raise McpError("overview response carried no chunk metadata")
            # host truncation guard: a chunk without metadata/completion flags is
            # a delivery failure, never a reason to fall back to search
            chunk_id = meta.get("chunk_sha256", "")[:16]
            if identity is None:
                identity = meta.get("index_sha256")
            elif meta.get("index_sha256") != identity:
                raise McpError("overview_snapshot_changed: index identity changed mid-chain")
            art["overview_chunks"].append({
                "chunk_index": meta.get("chunk_index"),
                "chunk_count": meta.get("chunk_count"),
                "chunk_sha256": meta.get("chunk_sha256"),
                "first_entry_ordinal": meta.get("first_entry_ordinal"),
                "last_entry_ordinal": meta.get("last_entry_ordinal")})
            entries.extend(parse_fras(body, meta.get("first_entry_ordinal") or 1))
            if meta.get("completed"):
                challenge = meta
                break
            nxt = meta.get("next_cursor")
            if not nxt or not meta.get("continuation_required"):
                raise McpError("chain broke: no next_cursor on an incomplete chunk")
            cursor = nxt
        else:
            return fail("overview chain exceeded %d calls; cognition stays PARTIAL"
                        % MAX_OVERVIEW_CALLS, "AOCI_FILE")
    except (McpError, McpUnavailable) as exc:
        client.close()
        art["cognition_state"] = "PARTIAL"
        return fail("overview chain incomplete: %s" % exc, "AOCI_FILE")

    if not challenge:
        client.close()
        art["cognition_state"] = "PARTIAL"
        return fail("overview completed without an attestation challenge", "AOCI_FILE")

    # -- 4. attestation (both proof halves in one call) ------------------------
    ordinals = challenge.get("challenge_ordinals") or []
    by_ord = {e["ordinal"]: e for e in entries}
    answers = []
    for o in ordinals:
        e = by_ord.get(o)
        if e:
            answers.append({"ordinal": o, "object_identity": e["object"],
                            "tag": e["tag"], "f": e["f"]})
    att = {
        "version": "model-cognition-attestation/v1",
        "index_sha256": challenge.get("challenge_index_sha256"),
        "entry_sequence_sha256": challenge.get("challenge_entry_sequence_sha256"),
        "entry_count": challenge.get("challenge_entry_count"),
        "challenge_digest": challenge.get("challenge_digest"),
        "challenge_answers": answers,
        "reported_entry_count": len(entries),
        "truncation_detected": len(entries) != (challenge.get("challenge_entry_count") or -1),
        "host_delivery_confirmation": "delivered:%d/%d chunks untruncated" % (
            len(art["overview_chunks"]), challenge.get("chunk_count") or len(art["overview_chunks"])),
    }
    try:
        out = client.call_tool("aoci_overview", {
            "scope": scope,
            "model_cognition_attestation": json.dumps(att, separators=(",", ":")),
            "host_delivery_confirmation": att["host_delivery_confirmation"]})
        if out["is_error"]:
            raise McpError(out["text"][:300])
        meta = _meta_json(out["text"])
    except (McpError, McpUnavailable) as exc:
        client.close()
        art["cognition_state"] = "PARTIAL"
        return fail("attestation submission failed: %s" % exc, "AOCI_FILE")

    result = meta.get("attestation_result") or {}
    passed = bool(result.get("ChallengePassed")) and not att["truncation_detected"]
    art["attestation"] = {
        "challenge_passed": bool(result.get("ChallengePassed")),
        "challenge_correct": result.get("ChallengeCorrect"),
        "challenge_total": result.get("ChallengeTotal"),
        "truncation_detected": att["truncation_detected"],
        "host_delivery_confirmation": True,
        "answers_submitted": len(answers),
    }
    art["index_identity"] = meta.get("index_sha256") or challenge.get("challenge_index_sha256")
    art["scope_identity"] = meta.get("scope_identity") or challenge.get("scope_identity")
    art["generation"] = meta.get("refresh_generation") or challenge.get("refresh_generation")
    art["scope"] = challenge.get("scope") or scope
    art["entry_count"] = meta.get("entry_count") or challenge.get("challenge_entry_count")
    art["runtime_repository_root"] = meta.get("runtime_repository_root",
                                              str(repo))
    art["alignment_state"] = "aligned" if passed else "attestation_failed"
    art["cognition_state"] = "COMPLETE" if passed else "PARTIAL"
    receipt_fields = {k: art[k] for k in
                      ("artifact_type", "backend", "runtime_repository_root", "scope",
                       "index_identity", "scope_identity", "generation",
                       "mcp_service_version", "alignment_state", "cognition_state",
                       "entry_count", "attestation")}
    art["receipt_digest"] = hashlib.sha256(
        json.dumps(receipt_fields, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if passed:
        # entries snapshot for the router: cognition claims + baseline binding
        baseline = {}
        bp = repo / ".aoci" / "baseline.json"
        if bp.exists():
            try:
                baseline = (json.loads(bp.read_text()) or {}).get("files", {}) or {}
            except (json.JSONDecodeError, OSError):
                baseline = {}
        snap = {}
        for e in entries:
            b = baseline.get(e["object"]) or baseline.get("./" + e["object"]) or {}
            snap[e["object"]] = {"tags": e["tag"],
                                 "fields": {"F": e["f"], "R": e.get("r", "-"),
                                            "A": e.get("a", "-")},
                                 "source_sha256": b.get("sha256", ""),
                                 "ordinal": e["ordinal"]}
        art["entries_snapshot"] = snap
    art["latency_ms"] = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
    _write(repo, art)
    if keep_client:
        # same, already-attested connection stays open for post-cognition reads
        # (attestation state is per-connection); non-serializable, attached after
        # the artifact write. Caller MUST close it.
        art["_client"] = client
    else:
        client.close()
    return art


def _write(repo: Path, art: dict):
    out = repo / SESSION_ARTIFACT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(art, indent=2))


# ---------------------------------------------------------------- post-cognition reads
def load_session(repo: Path) -> dict:
    p = repo / SESSION_ARTIFACT
    if not p.exists():
        raise SystemExit("no %s — run `aoci_runtime.py session --repo R` first" % SESSION_ARTIFACT)
    try:
        art = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise SystemExit("unreadable AOCI session artifact: %s" % exc)
    if art.get("artifact_type") != "AOCI_RUNTIME_SESSION":
        raise SystemExit("not an AOCI_RUNTIME_SESSION artifact")
    return art


def gated_read(repo: Path, argv: list[str], tool: str, arguments: dict) -> dict:
    """search / get-entries: only ever after whole-index cognition is COMPLETE.

    Session/attestation state is per-connection in the runtime protocol, so the
    read re-establishes the full lifecycle on one connection, checks the fresh
    identity against the PERSISTED receipt (cross-session drift), issues the read
    on that same connection, and checks the response identity again (mid-session
    drift). Any mismatch invalidates the persisted receipt."""
    prior = load_session(repo)
    if prior.get("fallback"):
        return {"ok": False, "reason": "session fell back to %s; runtime was never used"
                % prior["fallback"].get("fallback_backend"), "runtime_used": False}
    if prior.get("cognition_state") != "COMPLETE":
        return {"ok": False, "reason": "cognition_state=%s — whole-index cognition is "
                "not complete; reads stay gated" % prior.get("cognition_state"),
                "runtime_used": False}
    art = open_session(repo, argv, prior.get("scope") or "all", keep_client=True)
    client = art.pop("_client", None)
    try:
        if art.get("fallback") or art.get("cognition_state") != "COMPLETE":
            return {"ok": False, "runtime_used": True,
                    "reason": "cognition could not be re-established: %s"
                              % ((art.get("fallback") or {}).get("reason")
                                 or art.get("cognition_state"))}
        if prior.get("index_identity") and \
                art.get("index_identity") != prior["index_identity"]:
            _invalidate(repo, art,
                        "index changed since the persisted receipt (%s → %s)"
                        % (prior["index_identity"][:16], (art.get("index_identity") or "?")[:16]))
            return {"ok": False, "reason": "identity drift detected across sessions; "
                    "receipt invalidated", "drift": True, "runtime_used": True}
        out = client.call_tool(tool, arguments)
        if out["is_error"]:
            return {"ok": False, "reason": out["text"][:300], "runtime_used": True}
        meta = _meta_json(out["text"])
        rid = meta.get("index_sha256")
        if rid and rid != art.get("index_identity"):
            _invalidate(repo, art, "index identity changed since cognition receipt "
                                    "(%s → %s)" % (art.get("index_identity", "?")[:16], rid[:16]))
            return {"ok": False, "reason": "identity drift detected; receipt invalidated",
                    "drift": True, "runtime_used": True}
        gen = meta.get("refresh_generation")
        if gen and art.get("generation") and str(gen) != str(art["generation"]):
            _invalidate(repo, art, "refresh_generation advanced (%s → %s)"
                        % (art["generation"], gen))
            return {"ok": False, "reason": "generation drift detected; receipt invalidated",
                    "drift": True, "runtime_used": True}
        return {"ok": True, "runtime_used": True, "backend": art.get("backend"),
                "identity": rid, "generation": gen, "meta": meta, "text": out["text"]}
    finally:
        if client is not None:
            client.close()


def _invalidate(repo: Path, art: dict, reason: str):
    art["cognition_state"] = "INVALIDATED_DRIFT"
    art["alignment_state"] = "drifted"
    art["invalidation_reason"] = reason
    art["receipt_digest"] = None
    _write(repo, art)


# ---------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="AOCI_RUNTIME backend client (real runtime, explicit fallback).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe")
    p.add_argument("--repo", required=True)
    p.add_argument("--mcp-command")
    p = sub.add_parser("session")
    p.add_argument("--repo", required=True)
    p.add_argument("--mcp-command")
    p.add_argument("--scope", default="all",
                   choices=["all", "project", "meta", "code", "database"])
    p = sub.add_parser("search")
    p.add_argument("--repo", required=True)
    p.add_argument("--mcp-command")
    p.add_argument("--keyword")
    p.add_argument("--tag-filter")
    p = sub.add_parser("get-entries")
    p.add_argument("--repo", required=True)
    p.add_argument("--mcp-command")
    p.add_argument("--paths", required=True, help="comma-separated repo-relative paths")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print("error: %s is not a directory" % repo, file=sys.stderr)
        return 3
    argv = resolve_mcp_command(repo, getattr(args, "mcp_command", None))
    if argv is None:
        art = {"artifact_type": "AOCI_RUNTIME_SESSION",
               "runtime_repository_root": str(repo),
               "cognition_state": "FALLBACK",
               "generated_at": datetime.now(timezone.utc).isoformat(),
               "fallback": {"runtime_attempted": False, "runtime_used": False,
                            "fallback_backend": "AOCI_FILE",
                            "reason": "no AOCI_MCP_COMMAND configured (env, config file, or --mcp-command)"}}
        _write(repo, art)
        print(json.dumps({"ok": True, "cognition_state": "FALLBACK",
                          "runtime_used": False,
                          "fallback": art["fallback"],
                          "reason": art["fallback"]["reason"]}, indent=2))
        return 0

    if args.cmd == "probe":
        from mcp_stdio_client import probe
        report = probe(argv, cwd=str(repo))
        report["pinned_aoci_surface"] = bool(report.get("tools")) and (
            tool_surface_digest(report["tools"]) == PINNED_SURFACE_SHA256)
        print(json.dumps(report, indent=2))
        return 0 if report["available"] and report.get("pinned_aoci_surface") else 4

    if args.cmd == "session":
        art = open_session(repo, argv, args.scope)
        print(json.dumps({"ok": True,
                          "backend": art.get("backend"),
                          "cognition_state": art["cognition_state"],
                          "runtime_used": not art.get("fallback"),
                          "identity": art.get("index_identity"),
                          "generation": art.get("generation"),
                          "entry_count": art.get("entry_count"),
                          "attestation": art.get("attestation"),
                          "latency_ms": art.get("latency_ms"),
                          "fallback": art.get("fallback"),
                          "artifact": str(repo / SESSION_ARTIFACT)}, indent=2))
        return 0

    if args.cmd == "search":
        if not args.keyword and not args.tag_filter:
            print("error: --keyword or --tag-filter required", file=sys.stderr)
            return 2
        out = gated_read(repo, argv, "aoci_search",
                         {"keyword": args.keyword or "", "tag_filter": args.tag_filter or ""})
        print(json.dumps(out, indent=2, default=str))
        return 0 if out["ok"] else 4

    # get-entries
    out = gated_read(repo, argv, "aoci_get_entries", {"paths": args.paths})
    print(json.dumps(out, indent=2, default=str))
    return 0 if out["ok"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
