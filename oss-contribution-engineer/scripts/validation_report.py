#!/usr/bin/env python3
"""validation_report.py — render a Validation Report from the evidence manifest.

Reads the manifest written by evidence_manifest.py and emits the required table
(Command | Purpose | Executed | Result | Evidence). Skipped/unavailable entries stay
skipped/unavailable — they are never collapsed into PASS. Exits non-zero if any
command FAILED or if unexecuted entries exist, so "everything green" cannot be
silently assumed.

Exit codes: 0 = all executed and passed, 1 = at least one FAIL, 2 = usage,
3 = no manifest, 4 = report contains unexecuted entries (visible incompleteness).
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

EVIDENCE_DIR = ".oss-contrib-evidence"


def load_entries(repo: Path) -> list[dict]:
    manifest = repo / EVIDENCE_DIR / "manifest.jsonl"
    if not manifest.exists():
        print("error: no evidence manifest at %s — record commands with evidence_manifest.py first"
              % manifest, file=sys.stderr)
        raise SystemExit(3)
    entries = []
    for lineno, line in enumerate(manifest.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as e:
            print("error: manifest line %d is not valid JSON: %s" % (lineno, e), file=sys.stderr)
            raise SystemExit(4)
    return entries


def build_report(entries: list[dict]) -> dict:
    rows = []
    for e in entries:
        if e["kind"] == "execution":
            expected_fail = bool(e.get("expected_failure"))
            if e["status"] == "FAIL" and expected_fail:
                shown = "FAIL (unexpected — proof did not hold)"
            elif e["status"] == "PASS" and expected_fail:
                shown = "PASS (expected failure — RED proof)"
            else:
                shown = e["status"]
            rows.append({
                "command": shlex.join(e["command"]),
                "purpose": e["purpose"],
                "executed": True,
                "result": shown,
                "counted_result": e["status"],
                "evidence": "%s (sha256 %s, exit %s, head %s)" % (
                    e["artifact"], e["artifact_sha256"][:12], e["exit_code"],
                    (e.get("git_head") or "n/a")[:12]),
            })
        else:
            rows.append({
                "command": "(not executed)",
                "purpose": e["purpose"],
                "executed": False,
                "result": e["status"],
                "counted_result": e["status"],
                "evidence": "reason: %s" % e.get("reason", ""),
            })
    # expected failures (RED proofs) are evidence, not validation failures
    fails = sum(1 for r in rows if r["counted_result"] == "FAIL")
    unexecuted = sum(1 for r in rows if not r["executed"])
    passed = sum(1 for r in rows if r["counted_result"] == "PASS")
    if fails:
        conclusion = "FAILED"
    elif unexecuted:
        conclusion = "INCOMPLETE — %d validation step(s) not executed; say so in the PR" % unexecuted
    else:
        conclusion = "PASSED"
    return {
        "rows": rows,
        "summary": {"executed": len(rows) - unexecuted, "passed": passed,
                    "failed": fails, "not_executed": unexecuted},
        "conclusion": conclusion,
        "rule": "skipped work is never collapsed into PASS; unexecuted steps are listed, not hidden",
    }


def render_markdown(report: dict) -> str:
    lines = ["# Validation Report", "",
             "| Command | Purpose | Executed | Result | Evidence |",
             "|---------|---------|----------|--------|----------|"]
    for r in report["rows"]:
        lines.append("| `%s` | %s | %s | %s | %s |" % (
            r["command"], r["purpose"],
            "yes" if r["executed"] else "**no**", r["result"], r["evidence"]))
    s = report["summary"]
    lines += ["", "Summary: %d executed, %d passed, %d failed, %d not executed." % (
        s["executed"], s["passed"], s["failed"], s["not_executed"]),
        "Conclusion: **%s**" % report["conclusion"]]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Render a Validation Report from the evidence manifest.")
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--markdown", action="store_true", help="emit the report as markdown")
    ap.add_argument("--out", help="also write the markdown report to this file")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print("error: %s is not a directory" % repo, file=sys.stderr)
        return 2

    report = build_report(load_entries(repo))
    if args.markdown or args.out:
        text = render_markdown(report)
        if args.out:
            Path(args.out).write_text(text + "\n")
        if args.markdown:
            print(text)
    else:
        for r in report["rows"]:
            flag = "" if r["executed"] else "  [NOT EXECUTED]"
            print("%-11s  %s%s" % (r["result"], r["purpose"], flag))
            print("              %s" % r["command"])
        s = report["summary"]
        print("summary: %d executed, %d passed, %d failed, %d not executed" % (
            s["executed"], s["passed"], s["failed"], s["not_executed"]))
        print("conclusion: %s" % report["conclusion"])

    if report["summary"]["failed"]:
        return 1
    if report["summary"]["not_executed"]:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
