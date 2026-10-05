#!/usr/bin/env python3
"""cognition_receipt.py — Task Cognition Receipt: persistent, digest-bound context state.

The receipt records what a task actually read (paths + sha256 + ranges + why), the goal
contract digest, the cognition backend and its alignment, decisions, evidence refs, and
the next action — so a compacted context can be RECONSTRUCTED from persistent artifacts
instead of hallucinated from fading model memory.

Subcommands: open · record-read · verify · close · show · reconstruct

Storage: <repo>/.oss-contrib-evidence/cognition/receipt-<task_id>.json
Exit codes: 0 ok, 2 usage, 3 missing receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def receipt_path(repo: Path, task_id: str) -> Path:
    return repo / ".oss-contrib-evidence" / "cognition" / ("receipt-%s.json" % task_id)


def load(repo: Path, task_id: str) -> dict:
    p = receipt_path(repo, task_id)
    if not p.exists():
        print("error: no receipt for task %s at %s" % (task_id, p), file=sys.stderr)
        raise SystemExit(3)
    return json.loads(p.read_text())


def save(repo: Path, receipt: dict) -> None:
    body = {k: v for k, v in receipt.items() if k != "digest"}
    receipt["digest"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    p = receipt_path(repo, receipt["task_id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


def git_head(repo: Path) -> str:
    p = subprocess_run(["git", "-C", str(repo), "rev-parse", "HEAD"])
    return p.strip() or "unknown"


def subprocess_run(argv: list[str]) -> str:
    import subprocess
    p = subprocess.run(argv, capture_output=True, text=True, shell=False)
    return p.stdout


def cmd_open(args) -> int:
    repo = Path(args.repo).resolve()
    if receipt_path(repo, args.task_id).exists() and not args.fresh:
        print("error: receipt exists for %s (use --fresh to start a new generation)" % args.task_id,
              file=sys.stderr)
        return 2
    backend = {"kind": args.backend, "identity": args.backend_identity or "unspecified",
               "aligned_state": args.aligned or "absent"}
    receipt = {
        "receipt_version": 1,
        "task_id": args.task_id,
        "repository": args.repository or repo.name,
        "base_sha": git_head(repo),
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "goal_digest": args.goal_digest or "none",
        "cognition_backend": backend,
        "subsystems_understood": [],
        "sources_read": [],
        "tests_read": [],
        "history_evidence": [],
        "external_contracts": [],
        "decisions": [],
        "evidence_refs": [],
        "unresolved_questions": [],
        "context_pack_digest": None,
        "next_action": args.next_action or "context plan",
        "closed": False,
    }
    save(repo, receipt)
    print("receipt opened: %s (base %s, backend %s/%s)" % (
        receipt_path(repo, args.task_id), receipt["base_sha"][:12], backend["kind"], backend["aligned_state"]))
    return 0


def cmd_record_read(args) -> int:
    repo = Path(args.repo).resolve()
    receipt = load(repo, args.task_id)
    for path in args.paths:
        p = repo / path
        if not p.is_file():
            print("warning: %s does not exist; skipped" % path, file=sys.stderr)
            continue
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        entry = {"path": path, "read_at": datetime.now(timezone.utc).isoformat(),
                 "digest": digest, "ranges": args.ranges or ["full"], "why": args.why or ""}
        bucket = "tests_read" if ("/test" in path or path.endswith(("_test.py", ".test.js")) or "_test." in path) else "sources_read"
        receipt[bucket].append(entry)
    save(repo, receipt)
    print("recorded %d read(s) into %s" % (len(args.paths), args.task_id))
    return 0


def cmd_verify(args) -> int:
    repo = Path(args.repo).resolve()
    receipt = load(repo, args.task_id)
    changed = missing = current = 0
    print("Source verification (%s, base %s):" % (args.task_id, receipt["base_sha"][:12]))
    for e in receipt["sources_read"] + receipt["tests_read"]:
        p = repo / e["path"]
        if not p.exists():
            print("  DELETED %s" % e["path"])
            missing += 1
            continue
        now = hashlib.sha256(p.read_bytes()).hexdigest()
        if now == e["digest"]:
            print("  CURRENT %s (%s)" % (e["path"], e.get("ranges", ["full"])[0]))
            current += 1
        else:
            print("  CHANGED %s — re-read before any edit or claim" % e["path"])
            changed += 1
    print("summary: %d current, %d changed, %d deleted" % (current, changed, missing))
    return 0 if changed == 0 and missing == 0 else 1


def cmd_close(args) -> int:
    repo = Path(args.repo).resolve()
    receipt = load(repo, args.task_id)
    receipt["unresolved_questions"] = list(args.unresolved or receipt["unresolved_questions"])
    receipt["context_pack_digest"] = args.pack_digest or receipt["context_pack_digest"]
    receipt["next_action"] = args.next_action or receipt["next_action"]
    receipt["evidence_refs"] = list(dict.fromkeys(receipt["evidence_refs"] + (args.evidence or [])))
    receipt["closed"] = True
    receipt["closed_at"] = datetime.now(timezone.utc).isoformat()
    save(repo, receipt)
    print("receipt closed: %s" % args.task_id)
    return 0


def cmd_show(args) -> int:
    receipt = load(Path(args.repo).resolve(), args.task_id)
    print(json.dumps(receipt, indent=2))
    return 0


def cmd_reconstruct(args) -> int:
    receipt = load(Path(args.repo).resolve(), args.task_id)
    print("RESULT       RECONSTRUCTED (from receipt %s, task %s)" % (receipt["digest"][:12], receipt["task_id"]))
    print("STATE        base %s | backend %s/%s | goal %s" % (
        receipt["base_sha"][:12],
        receipt["cognition_backend"]["kind"], receipt["cognition_backend"]["aligned_state"],
        receipt["goal_digest"][:12] if receipt["goal_digest"] != "none" else "none"))
    print("READ         %d sources, %d tests — run 'verify' before trusting any of them" % (
        len(receipt["sources_read"]), len(receipt["tests_read"])))
    for d in receipt["decisions"][-3:]:
        print("DECISION     %s (%s)" % (d["decision"], d["reason"]))
    for q in receipt["unresolved_questions"]:
        print("UNRESOLVED   %s" % q)
    print("NEXT         %s" % receipt["next_action"])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Task Cognition Receipt management.")
    ap.add_argument("repo")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("open")
    p.add_argument("--task-id", required=True)
    p.add_argument("--goal-digest")
    p.add_argument("--repository")
    p.add_argument("--backend", default="LIGHTWEIGHT_FALLBACK",
                   choices=["AOCI_NATIVE", "NATIVE_PROJECT_MEMORY", "LIGHTWEIGHT_FALLBACK"])
    p.add_argument("--backend-identity")
    p.add_argument("--aligned", choices=["aligned", "drifted", "stale", "unverified", "absent"])
    p.add_argument("--next-action")
    p.add_argument("--fresh", action="store_true")
    p.set_defaults(func=cmd_open)

    p = sub.add_parser("record-read")
    p.add_argument("--task-id", required=True)
    p.add_argument("paths", nargs="+")
    p.add_argument("--ranges", action="append")
    p.add_argument("--why")
    p.set_defaults(func=cmd_record_read)

    p = sub.add_parser("verify")
    p.add_argument("--task-id", required=True)
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("close")
    p.add_argument("--task-id", required=True)
    p.add_argument("--unresolved", action="append")
    p.add_argument("--pack-digest")
    p.add_argument("--next-action")
    p.add_argument("--evidence", action="append")
    p.set_defaults(func=cmd_close)

    p = sub.add_parser("show")
    p.add_argument("--task-id", required=True)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("reconstruct")
    p.add_argument("--task-id", required=True)
    p.set_defaults(func=cmd_reconstruct)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
