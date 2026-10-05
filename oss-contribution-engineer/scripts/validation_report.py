#!/usr/bin/env python3
"""validation_report.py — render a Validation Report from the evidence manifest.

Reads the manifest written by evidence_manifest.py and emits the required table
(Command | Purpose | Executed | Result | Evidence). Skipped/unavailable entries stay
skipped/unavailable — they are never collapsed into PASS. Exits non-zero if any
command FAILED, if unexecuted entries exist, or if head-bound evidence has gone STALE
(recorded at a git HEAD that is no longer current — typical after a review-driven
change), so "everything green" cannot be silently assumed or borrowed from older code.

Exit codes: 0 = all executed and passed, 1 = at least one FAIL, 2 = usage,
3 = no manifest, 4 = report contains unexecuted entries (visible incompleteness),
5 = head-bound evidence is STALE for the current HEAD (rerun before citing PASS).
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

EVIDENCE_DIR = ".oss-contrib-evidence"


def current_git_head(repo: Path) -> str | None:
    p = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                       capture_output=True, text=True, shell=False)
    return p.stdout.strip() if p.returncode == 0 else None


def files_changed_between(repo: Path, old: str, new: str) -> list[str]:
    p = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", old + ".." + new],
                       capture_output=True, text=True, shell=False)
    if p.returncode != 0:
        return []
    skip = (EVIDENCE_DIR + "/", "__pycache__/", ".pyc")
    return [ln for ln in p.stdout.splitlines()
            if ln.strip() and not any(s in ln for s in skip)]


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


def build_report(entries: list[dict], head: str | None = None) -> dict:
    rows = []
    stale_heads = set()
    # head-bound PASS records that cover the CURRENT head — proof the current code
    # state has been validated. Older head-bound records covered by a newer rerun at
    # the current head are SUPERSEDED (visible history, not active evidence); only a
    # head-bound record with no covering rerun is STALE and blocks the conclusion.
    covering_ids = sorted(e["id"] for e in entries
                          if e["kind"] == "execution" and e["status"] == "PASS"
                          and e.get("head_bound") and head is not None
                          and e.get("git_head") == head)
    for e in entries:
        if e["kind"] == "execution":
            expected_fail = bool(e.get("expected_failure"))
            if e["status"] == "FAIL" and expected_fail:
                shown = "FAIL (unexpected — proof did not hold)"
            elif e["status"] == "PASS" and expected_fail:
                shown = "PASS (expected failure — RED proof)"
            else:
                shown = e["status"]
            counted = e["status"]
            if (e["status"] == "PASS" and e.get("head_bound")
                    and head is not None and e.get("git_head")
                    and e["git_head"] != head):
                later_cover = [i for i in covering_ids if i > e["id"]]
                if later_cover:
                    counted = "SUPERSEDED"
                    shown = "SUPERSEDED (rerun as #%d at current HEAD)" % later_cover[0]
                else:
                    stale_heads.add(e["git_head"])
                    counted = "STALE"
                    shown = "STALE (recorded at %s; current HEAD %s)" % (
                        e["git_head"][:12], head[:12])
            rows.append({
                "command": shlex.join(e["command"]),
                "purpose": e["purpose"],
                "executed": True,
                "result": shown,
                "counted_result": counted,
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
    stale = sum(1 for r in rows if r["counted_result"] == "STALE")
    superseded = sum(1 for r in rows if r["counted_result"] == "SUPERSEDED")
    passed = sum(1 for r in rows if r["counted_result"] == "PASS")
    if fails:
        conclusion = "FAILED"
    elif stale:
        conclusion = ("STALE — %d head-bound evidence record(s) predate the current HEAD "
                      "with no rerun covering it; rerun affected validation before citing PASS" % stale)
    elif unexecuted:
        conclusion = "INCOMPLETE — %d validation step(s) not executed; say so in the PR" % unexecuted
    else:
        conclusion = "PASSED"
    return {
        "rows": rows,
        "summary": {"executed": len(rows) - unexecuted, "passed": passed,
                    "failed": fails, "not_executed": unexecuted, "stale": stale,
                    "superseded": superseded},
        "conclusion": conclusion,
        "stale_heads": sorted(stale_heads),
        "head": head,
        "rule": "skipped work is never collapsed into PASS; unexecuted steps are listed, "
                "not hidden; head-bound PASS never survives a moved HEAD without a "
                "covering rerun (older records show SUPERSEDED, never PASS)",
    }


def render_markdown(report: dict, repo: Path | None = None) -> str:
    lines = ["# Validation Report", "",
             "| Command | Purpose | Executed | Result | Evidence |",
             "|---------|---------|----------|--------|----------|"]
    for r in report["rows"]:
        lines.append("| `%s` | %s | %s | %s | %s |" % (
            r["command"], r["purpose"],
            "yes" if r["executed"] else "**no**", r["result"], r["evidence"]))
    s = report["summary"]
    lines += ["", "Summary: %d executed, %d passed, %d failed, %d not executed, %d stale." % (
        s["executed"], s["passed"], s["failed"], s["not_executed"], s["stale"]),
        "Conclusion: **%s**" % report["conclusion"]]
    if report.get("stale_heads") and report.get("head") and repo is not None:
        for old in report["stale_heads"]:
            changed = files_changed_between(repo, old, report["head"])
            if changed:
                lines += ["", "Files changed since stale evidence (rerun what covers them): %s"
                          % ", ".join(changed)]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Render a Validation Report from the evidence manifest.")
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--markdown", action="store_true", help="emit the report as markdown")
    ap.add_argument("--out", help="also write the markdown report to this file")
    ap.add_argument("--head", help="treat this commit as the current HEAD instead of querying git "
                                   "(e.g. a PR head SHA captured from upstream)")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print("error: %s is not a directory" % repo, file=sys.stderr)
        return 2

    head = args.head or current_git_head(repo)
    report = build_report(load_entries(repo), head)
    if args.markdown or args.out:
        text = render_markdown(report, repo)
        if args.out:
            Path(args.out).write_text(text + "\n")
        if args.markdown:
            print(text)
    else:
        for r in report["rows"]:
            flag = "" if r["executed"] else "  [NOT EXECUTED]"
            print("%-11s  %s%s" % (r["result"][:11], r["purpose"], flag))
            print("              %s" % r["command"])
        s = report["summary"]
        print("summary: %d executed, %d passed, %d failed, %d not executed, %d stale" % (
            s["executed"], s["passed"], s["failed"], s["not_executed"], s["stale"]))
        print("conclusion: %s" % report["conclusion"])

    if report["summary"]["failed"]:
        return 1
    if report["summary"]["stale"]:
        return 5
    if report["summary"]["not_executed"]:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
