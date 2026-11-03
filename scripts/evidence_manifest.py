#!/usr/bin/env python3
"""evidence_manifest.py — witnessed command execution for contribution evidence.

Prevents fabricated validation: a result exists only because this script ran the
command (record) or because a skip was explicitly declared with a reason (record-skip).
Each record captures the command, exit code, duration, captured output (with sha256),
the git HEAD at run time, and the environment.

`--head-bound` marks evidence that is only valid for the recorded HEAD (GREEN runs,
suites, lint, build). validation_report.py flags such entries as STALE when the
current HEAD differs. RED proofs and pre-fix baselines are deliberately recorded
WITHOUT the flag — they are supposed to run on older code.

Security: the command is executed as an argv list with shell=False — no shell ever
parses it. The list is anchored through /usr/bin/env purely so PATH resolution happens
outside any shell; privileges are exactly the caller's, and running a command is the
caller's explicit choice (that is the feature: witnessing it).

Evidence lives in <repo>/.oss-contrib-evidence/ (manifest.jsonl + artifacts/).

Usage
-----
  evidence_manifest.py [repo] record --purpose "RED proof" -- <command> [args...]
  evidence_manifest.py [repo] record --purpose "GREEN" --head-bound -- <command> [args...]
  evidence_manifest.py [repo] record-skip --purpose "integration suite" --status SKIPPED --reason "no docker"
  evidence_manifest.py [repo] show [--markdown]
  evidence_manifest.py [repo] verify <record-id>

Status derivation: exit 0 → PASS, non-zero → FAIL, record-skip → SKIPPED | UNAVAILABLE.

Exit codes: 0 = ok, 1 = last record was a FAIL (record mode), 2 = usage, 3 = missing evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

EVIDENCE_DIR = ".oss-contrib-evidence"


def evidence_root(repo: Path) -> Path:
    return repo / EVIDENCE_DIR


def git_head(repo: Path) -> str | None:
    p = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                       capture_output=True, text=True, shell=False)
    return p.stdout.strip() if p.returncode == 0 else None


def next_id(manifest: Path) -> int:
    if not manifest.exists():
        return 1
    return sum(1 for line in manifest.read_text().splitlines() if line.strip()) + 1


def append(manifest: Path, entry: dict) -> None:
    with manifest.open("a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def slugify(text: str, limit: int = 40) -> str:
    slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in text)[:limit].strip("-")
    return slug or "run"


EVIDENCE_TYPES = {"REPRODUCTION", "RED_REGRESSION", "GREEN_REGRESSION",
                  "PACKAGE_TEST", "LINT", "BUILD", "INTEGRATION", "BASELINE",
                  "RECON", "GENERAL"}


def _file_digest(path: str) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _resolve_test_file(raw: str, cwd: str | None, repo: Path) -> Path | None:
    """Resolve a --test-file argument the way a reasonable caller means it:
    absolute / cwd-relative first, then relative to --cwd when the caller gave
    one, then relative to the repository root (a monorepo package run with
    repo-relative paths — real-usage defect: this used to silently drop the
    identity, breaking RED binding). Returns None only if no base finds it."""
    candidates = []
    p = Path(raw)
    if p.is_absolute():
        candidates.append(p)
    else:
        if cwd:
            candidates.append(Path(cwd) / p)
        candidates.append(Path.cwd() / p)
        candidates.append(repo / p)
    for c in candidates:
        if c.exists():
            return c.resolve()
    return None


def cmd_record(repo: Path, purpose: str, command: list[str], expect_fail: bool,
               head_bound: bool = False, evidence_type: str = "GENERAL",
               regression_id: str | None = None,
               test_files: list[str] | None = None,
               cwd: str | None = None) -> int:
    if not command:
        print("error: no command given after '--'", file=sys.stderr)
        return 2
    if any("\x00" in c for c in command):
        print("error: command arguments must not contain NUL bytes", file=sys.stderr)
        return 2
    root = evidence_root(repo)
    art_dir = root / "artifacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    manifest = root / "manifest.jsonl"

    rid = next_id(manifest)
    ts = datetime.now(timezone.utc)
    artifact = art_dir / ("%03d-%s-%s.txt" % (rid, ts.strftime("%Y%m%d-%H%M%S"), slugify(purpose)))

    start = time.monotonic()
    # argv list, shell=False; /usr/bin/env is a fixed loader that resolves $PATH for the
    # program name so no shell layer is involved at any point.
    # V9 failure F4: commands ran from the CALLER's cwd — cwd-dependent tests
    # (glob expansion, relative paths) failed spuriously. --cwd pins the run
    # (recorded in the entry so staleness checks can see it).
    p = subprocess.run(["/usr/bin/env", *command], capture_output=True, text=True,
                       shell=False, cwd=cwd)
    duration_ms = int((time.monotonic() - start) * 1000)

    output = (p.stdout or "") + (("\n--- stderr ---\n" + p.stderr) if p.stderr else "")
    if not output.endswith("\n"):
        output += "\n"
    output += "\n[exit code: %d]\n" % p.returncode
    artifact.write_text(output)
    sha = hashlib.sha256(artifact.read_bytes()).hexdigest()

    # test-file identity: resolve the way the caller means the path (see
    # _resolve_test_file); an unresolvable path is a loud warning, never a
    # silent identity drop (silent drops broke RED binding in real use).
    test_identity = []
    unresolved_tests = []
    for f in test_files or []:
        resolved = _resolve_test_file(f, cwd, repo)
        if resolved is None:
            unresolved_tests.append(f)
            continue
        test_identity.append({"path": str(resolved), "digest": _file_digest(str(resolved))})
    if unresolved_tests:
        print("warning: --test-file not found from cwd, --cwd, or the repo root; "
              "identity NOT recorded for: %s — use an absolute path or a path "
              "relative to --cwd (RED↔GREEN binding needs the identity)"
              % ", ".join(unresolved_tests), file=sys.stderr)

    failed = p.returncode != 0
    if expect_fail and not failed:
        # an expected-failure record that exited 0 means the proof did NOT hold
        status = "FAIL"
    elif expect_fail:
        status = "PASS"
    else:
        status = "PASS" if p.returncode == 0 else "FAIL"

    entry = {
        "id": rid,
        "kind": "execution",
        "timestamp": ts.isoformat(),
        "purpose": purpose,
        "evidence_type": evidence_type,
        "regression_id": regression_id,
        # regression-test identity: digests let the runtime detect a test that was
        # changed after RED (weakening the test to obtain GREEN)
        "test_identity": test_identity,
        "command": command,
        "exit_code": p.returncode,
        "status": status,
        "expected_failure": expect_fail,
        "head_bound": head_bound,
        "duration_ms": duration_ms,
        "artifact": str(artifact.relative_to(repo)),
        "artifact_sha256": sha,
        "git_head": git_head(repo),
        # V9 F4: record the EFFECTIVE cwd (the --cwd value when given), not the
        # caller's — staleness/review can then see where the command really ran
        "cwd": str(Path(cwd).resolve()) if cwd else str(Path.cwd()),
        "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
    }
    append(manifest, entry)
    print("recorded #%d %s — %s" % (rid, entry["status"], purpose))
    print("  command: %s" % shlex.join(command))
    print("  artifact: %s (sha256 %s…)" % (entry["artifact"], sha[:12]))
    return 0 if entry["status"] == "PASS" else 1


def cmd_record_void(repo: Path, entry_id: int, reason: str) -> int:
    """V12 cold-start defect D5: a mistaken record (e.g. a reproduction that
    failed for the WRONG reason) stayed active forever and flipped the final
    Validation Report to FAILED. void marks an entry VOIDED — it stays in the
    manifest (append-only history) but is excluded from conclusions, with the
    human-visible reason."""
    if not reason.strip():
        print("error: a void needs --reason (visibility over silence)", file=sys.stderr)
        return 2
    manifest = evidence_root(repo) / "manifest.jsonl"
    if not manifest.exists():
        print("error: no evidence manifest at %s" % manifest, file=sys.stderr)
        return 3
    target = None
    for line in manifest.read_text().splitlines():
        if line.strip():
            e = json.loads(line)
            if e.get("id") == entry_id:
                target = e
    if target is None:
        print("error: no entry #%d in the manifest" % entry_id, file=sys.stderr)
        return 3
    entry = {
        "id": next_id(manifest),
        "kind": "void",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "voids_entry": entry_id,
        "voided_purpose": target.get("purpose", ""),
        "reason": reason.strip(),
        "executed": False,
        "git_head": git_head(repo),
    }
    append(manifest, entry)
    print("recorded #%d VOIDED entry #%d — %s (%s)"
          % (entry["id"], entry_id, target.get("purpose", ""), reason.strip()))
    return 0


def cmd_record_skip(repo: Path, purpose: str, status: str, reason: str) -> int:
    if status not in ("SKIPPED", "UNAVAILABLE"):
        print("error: --status must be SKIPPED or UNAVAILABLE", file=sys.stderr)
        return 2
    if not reason.strip():
        print("error: a skip needs --reason (visibility over silence)", file=sys.stderr)
        return 2
    manifest = evidence_root(repo) / "manifest.jsonl"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "id": next_id(manifest),
        "kind": "non-execution",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "purpose": purpose,
        "status": status,
        "reason": reason.strip(),
        "executed": False,
        "git_head": git_head(repo),
    }
    append(manifest, entry)
    print("recorded #%d %s — %s (%s)" % (entry["id"], status, purpose, reason.strip()))
    return 0


def load_entries(repo: Path) -> list[dict]:
    manifest = evidence_root(repo) / "manifest.jsonl"
    if not manifest.exists():
        print("error: no evidence manifest at %s" % manifest, file=sys.stderr)
        raise SystemExit(3)
    return [json.loads(line) for line in manifest.read_text().splitlines() if line.strip()]


def cmd_show(repo: Path, markdown: bool) -> int:
    entries = load_entries(repo)
    if markdown:
        print("| # | Command | Purpose | Status | Evidence |")
        print("|---|---------|---------|--------|----------|")
        for e in entries:
            if e["kind"] == "execution":
                cmdtxt = shlex.join(e["command"])
                ev = "%s (sha %s…)" % (e["artifact"], e["artifact_sha256"][:8])
            else:
                cmdtxt = "(not executed)"
                ev = e.get("reason", "")
            print("| %s | `%s` | %s | %s | %s |" % (e["id"], cmdtxt, e["purpose"], e["status"], ev))
    else:
        for e in entries:
            if e["kind"] == "execution":
                print("#%-3d %-4s  %s" % (e["id"], e["status"], e["purpose"]))
                print("      %s" % shlex.join(e["command"]))
                print("      artifact: %s  exit: %s  %sms" % (e["artifact"], e["exit_code"], e["duration_ms"]))
            else:
                print("#%-3d %-4s  %s" % (e["id"], e["status"], e["purpose"]))
                print("      (not executed) reason: %s" % e.get("reason", ""))
    return 0


def cmd_verify(repo: Path, rid: int) -> int:
    for e in load_entries(repo):
        if e["id"] == rid and e["kind"] == "execution":
            artifact = repo / e["artifact"]
            if not artifact.exists():
                print("FAIL: artifact missing: %s" % artifact)
                return 1
            sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
            ok = sha == e["artifact_sha256"]
            print("#%d artifact %s: sha256 %s (%s)" % (rid, e["artifact"], sha[:12],
                                                       "matches" if ok else "MISMATCH"))
            return 0 if ok else 1
    print("error: no execution record with id %d" % rid, file=sys.stderr)
    return 2


def main() -> int:
    ap = argparse.ArgumentParser(description="Witnessed command execution evidence.")
    ap.add_argument("repo", nargs="?", default=".", help="repository root (default: .)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_rec = sub.add_parser("record", help="run a command and record its result")
    p_rec.add_argument("--purpose", required=True)
    p_rec.add_argument("--expect-fail", action="store_true",
                       help="non-zero exit is the expected outcome (e.g. RED proof); "
                            "exiting 0 records FAIL instead")
    p_rec.add_argument("--head-bound", action="store_true",
                       help="evidence is only valid for the recorded HEAD (GREEN, suites, "
                            "lint, build); validation_report marks it STALE after HEAD moves")
    p_rec.add_argument("--evidence-type", default="GENERAL", choices=sorted(EVIDENCE_TYPES),
                       help="typed evidence category — the machine discriminator for "
                            "runtime gates (purpose is for humans)")
    p_rec.add_argument("--regression-id", help="links RED_REGRESSION and GREEN_REGRESSION "
                                               "records of the same regression test")
    p_rec.add_argument("--test-file", action="append",
                       help="regression test file(s) whose digests are recorded as "
                            "identity — changing them after RED invalidates the proof")
    p_rec.add_argument("--cwd", help="working directory for the witnessed command "
                                     "(V9 F4: cwd-dependent tests need this)")
    p_rec.add_argument("command", nargs=argparse.REMAINDER, help="command after '--'")

    p_skip = sub.add_parser("record-skip", help="record a non-execution explicitly")
    p_void = sub.add_parser("void", help="mark a mistaken entry VOIDED (kept in "
                                         "history, excluded from conclusions)")
    p_void.add_argument("--id", type=int, required=True)
    p_void.add_argument("--reason", required=True)
    p_skip.add_argument("--purpose", required=True)
    p_skip.add_argument("--status", required=True, choices=["SKIPPED", "UNAVAILABLE"])
    p_skip.add_argument("--reason", required=True)

    p_show = sub.add_parser("show", help="show the manifest")
    p_show.add_argument("--markdown", action="store_true")

    p_ver = sub.add_parser("verify", help="verify an artifact hash")
    p_ver.add_argument("id", type=int)

    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print("error: %s is not a directory" % repo, file=sys.stderr)
        return 3

    if args.cmd == "record":
        command = [c for c in args.command if c != "--"]
        return cmd_record(repo, args.purpose, command, args.expect_fail, args.head_bound,
                          args.evidence_type, args.regression_id, args.test_file,
                          cwd=args.cwd)
    if args.cmd == "record-skip":
        return cmd_record_skip(repo, args.purpose, args.status, args.reason)
    if args.cmd == "void":
        return cmd_record_void(repo, args.id, args.reason)
    if args.cmd == "show":
        return cmd_show(repo, args.markdown)
    if args.cmd == "verify":
        return cmd_verify(repo, args.id)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
