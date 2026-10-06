#!/usr/bin/env python3
"""duplicate_work_scan.py — deterministic duplicate-work evidence for an issue or topic.

The script does not touch the network. Data is captured by whatever platform tooling
the caller already has permission to use (the `gh` CLI, a GitHub platform tool, or a
forge's own client); this script then parses and aggregates that captured JSON — the
fiddly part (timeline events, cross-references, referencing commits) — into a summary
that feeds the DEDUPLICATE gate.

Usage
-----
  # 1) print the exact capture commands to run with gh (or take them from a platform tool)
  duplicate_work_scan.py commands --slug OWNER/REPO --issue 123

  # 2) capture with your tooling, then parse:
  duplicate_work_scan.py parse-issue --issue-file issue.json --timeline-file t1.json [--timeline-file t2.json ...]
  duplicate_work_scan.py parse-search --results-file search.json

`parse-issue` accepts the REST JSON bodies (works with gh output or equivalent
platform-tool output). Data may be incomplete — say so when classifying.

Exit codes: 0 = parsed, 2 = usage error, 3 = missing input file, 4 = malformed JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def load_json(path: Path):
    try:
        text = path.read_text(errors="replace")
    except OSError as e:
        print("error: cannot read %s: %s" % (path, e), file=sys.stderr)
        raise SystemExit(3)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print("error: %s is not valid JSON: %s" % (path, e), file=sys.stderr)
        raise SystemExit(4)


def capture_commands(slug: str, number: int) -> list[str]:
    pages = ["repos/%s/issues/%d/timeline?per_page=100&page=%d" % (slug, number, p)
             for p in (1, 2, 3)]
    cmds = ["gh api repos/%s/issues/%d > issue.json" % (slug, number)]
    cmds += ["gh api '%s' > timeline-p%d.json" % (q, i + 1) for i, q in enumerate(pages)]
    cmds.append("# optional: gh search issues '<keywords>' --repo %s --include-prs --json "
                "number,title,state,url,updatedAt > search.json" % slug)
    return cmds


def repository_identity(repo: Path) -> str:
    """Deterministic repository identity: origin slug (owner/repo) when a remote
    exists, else 'local-' + first 12 hex of sha256(realpath). Mirrors
    contribution_session.repository_identity so bundles bind to sessions."""
    p = subprocess.run(["git", "-C", str(repo), "remote", "get-url", "origin"],
                       capture_output=True, text=True, shell=False)
    if p.returncode == 0:
        m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", p.stdout.strip())
        if m:
            return m.group(1)
    root = subprocess.run(["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True, shell=False)
    fp = hashlib.sha256(
        str(Path(root.stdout.strip() or str(repo)).resolve()).encode()).hexdigest()[:12]
    return "local-" + fp


def digest_of(body: dict) -> str:
    payload = {k: v for k, v in body.items() if k != "digest"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def build_bundle(repo: Path, issue_file: Path | None, timeline_files: list[Path],
                 search_files: list[Path], base_sha: str | None = None) -> dict:
    """One coherent DUPLICATE_WORK_EVIDENCE bundle: issue state/timeline, cross
    references, open/merged PR references, keyword issue/PR search results,
    capture completeness notes, capture timestamp and repository identity —
    parse-search is folded into the same bundle instead of remaining a
    disconnected report."""
    from datetime import datetime, timezone
    issue = load_json(issue_file) if issue_file else {}
    timeline: list[dict] = []
    for tf in timeline_files:
        data = load_json(tf)
        if not isinstance(data, list):
            print("error: %s is not a JSON array (timeline responses are arrays)"
                  % tf, file=sys.stderr)
            raise SystemExit(4)
        timeline.extend(data)

    cross_refs, commits, linked = [], [], []
    for ev in timeline:
        et = ev.get("event")
        if et == "cross-referenced":
            src = ev.get("source", {}).get("issue", {})
            cross_refs.append({
                "number": src.get("number"), "title": src.get("title"),
                "state": src.get("state"),
                "merged": (src.get("pull_request") or {}).get("merged_at") is not None,
                "is_pr": "pull_request" in src,
                "repository": (src.get("repository") or {}).get("full_name"),
                "url": src.get("html_url"),
            })
        elif et == "referenced" and ev.get("commit_id"):
            commits.append({"sha": ev["commit_id"][:12], "url": ev.get("commit_id")})
        elif et == "connected":
            subj = ev.get("subject", {})
            linked.append({"number": subj.get("number"), "title": subj.get("title"),
                           "state": subj.get("state")})

    searches = []
    for sf in search_files:
        sdata = load_json(sf)
        if isinstance(sdata, dict):
            sdata = sdata.get("items", sdata.get("results", []))
        if not isinstance(sdata, list):
            print("error: %s is not a JSON array of search results" % sf,
                  file=sys.stderr)
            raise SystemExit(4)
        searches.append({
            "file": Path(sf).name,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "results": [{"number": r.get("number"), "title": r.get("title"),
                         "state": r.get("state"),
                         "url": r.get("html_url") or r.get("url")} for r in sdata],
        })

    pr_refs = [r for r in cross_refs if r["is_pr"]]
    bundle = {
        "type": "DUPLICATE_WORK_EVIDENCE",
        "schema_version": 2,
        "repository": repository_identity(repo),
        "repository_id": repository_identity(repo),
        "base_sha": base_sha,  # binds the bundle to the session's revision
        "generated_by": "duplicate_work_scan.py bundle",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "bundle",
        "issue": {
            "number": issue.get("number"), "title": issue.get("title"),
            "state": issue.get("state"), "state_reason": issue.get("state_reason"),
            "labels": [l.get("name") for l in issue.get("labels", [])],
            "assignees": [a.get("login") for a in issue.get("assignees", [])],
            "comments": issue.get("comments", 0),
            "created_at": issue.get("created_at"),
            "updated_at": issue.get("updated_at"),
            "url": issue.get("html_url"),
        },
        "timeline_events_parsed": len(timeline),
        "open_pr_references": [r for r in pr_refs if r["state"] == "open"],
        "merged_pr_references": [r for r in pr_refs if r["merged"]],
        "other_cross_references": [r for r in cross_refs if not r["is_pr"]],
        "linked_events": linked,
        "referencing_commits": commits,
        "keyword_issue_search": searches,
        "capture": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "completeness": "timeline capped at the captured pages; keyword search "
                            "capped by the capture — absence of signals does not "
                            "prove availability",
            "limitations": ["only GitHub via gh capture; other forges out of scope",
                            "classification (AVAILABLE/CLAIMED/PR_EXISTS/...) is the "
                            "caller's judgment"],
        },
        "dedupe_hints": [
            "open/merged PR references suggest PR_EXISTS or possibly ALREADY_FIXED",
            "'merged in own repo' for cross-repo references means merged in the "
            "PR's repository (often a fork), not this one",
            "assignees or comments announcing work suggest CLAIMED",
            "absence of signals does not prove availability — search issues and "
            "PRs by keyword too",
        ],
        "conclusion": "DATA_COLLECTED — classification is the caller's judgment; "
                      "data may be incomplete",
    }
    bundle["digest"] = digest_of(bundle)
    return bundle


def parse_issue(issue_file: Path, timeline_files: list[Path]) -> dict:
    issue = load_json(issue_file)
    if not isinstance(issue, dict):
        print("error: issue file is not a JSON object", file=sys.stderr)
        raise SystemExit(4)
    timeline: list[dict] = []
    for tf in timeline_files:
        data = load_json(tf)
        if not isinstance(data, list):
            print("error: %s is not a JSON array (timeline responses are arrays)" % tf,
                  file=sys.stderr)
            raise SystemExit(4)
        timeline.extend(data)

    cross_refs, commits, linked = [], [], []
    for ev in timeline:
        et = ev.get("event")
        if et == "cross-referenced":
            src = ev.get("source", {}).get("issue", {})
            cross_refs.append({
                "number": src.get("number"), "title": src.get("title"),
                "state": src.get("state"),
                # presence of merged_at means merged in the PR's OWN repository,
                # which for cross-repo references may be a fork — not this repo
                "merged": (src.get("pull_request") or {}).get("merged_at") is not None,
                "is_pr": "pull_request" in src,
                "repository": (src.get("repository") or {}).get("full_name"),
                "url": src.get("html_url"),
            })
        elif et == "referenced" and ev.get("commit_id"):
            commits.append({"sha": ev["commit_id"][:12], "url": ev.get("commit_id")})
        elif et == "connected":
            subj = ev.get("subject", {})
            linked.append({"number": subj.get("number"), "title": subj.get("title"),
                           "state": subj.get("state")})

    pr_refs = [r for r in cross_refs if r["is_pr"]]
    from datetime import datetime, timezone
    import hashlib
    body = {
        "type": "DUPLICATE_WORK_EVIDENCE",
        "schema_version": 1,
        "generated_by": "duplicate_work_scan.py",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "parse-issue",
        "issue": {
            "number": issue.get("number"), "title": issue.get("title"),
            "state": issue.get("state"), "state_reason": issue.get("state_reason"),
            "labels": [l.get("name") for l in issue.get("labels", [])],
            "assignees": [a.get("login") for a in issue.get("assignees", [])],
            "comments": issue.get("comments", 0),
            "created_at": issue.get("created_at"), "updated_at": issue.get("updated_at"),
            "url": issue.get("html_url"),
        },
        "timeline_events_parsed": len(timeline),
        "open_pr_references": [r for r in pr_refs if r["state"] == "open"],
        "merged_pr_references": [r for r in pr_refs if r["merged"]],
        "other_cross_references": [r for r in cross_refs if not r["is_pr"]],
        "linked_events": linked,
        "referencing_commits": commits,
        "dedupe_hints": [
            "open PR references or merged PR references suggest PR_EXISTS / possibly ALREADY_FIXED",
            "'merged in own repo' for cross-repo references means merged in the PR's repository (often a fork), not this one",
            "assignees or comments announcing work suggest CLAIMED",
            "absence of signals does not prove availability — search issues and PRs by keyword too",
        ],
        "conclusion": "DATA_COLLECTED — classification is the caller's judgment; data may be incomplete",
    }
    body["digest"] = hashlib.sha256(json.dumps(
        {k: v for k, v in body.items() if k != "digest"}, sort_keys=True).encode()).hexdigest()
    return body


def parse_search(results_file: Path) -> dict:
    data = load_json(results_file)
    if isinstance(data, dict):  # gh search --json wraps in an array; REST search uses items
        data = data.get("items", [])
    if not isinstance(data, list):
        print("error: search results are not a JSON array", file=sys.stderr)
        raise SystemExit(4)
    results = [{"number": r.get("number"), "title": r.get("title"),
                "state": r.get("state"), "url": r.get("html_url") or r.get("url")}
               for r in data]
    return {
        "mode": "parse-search",
        "results": results,
        "note": "search results capped by the capture; refine the query if needed",
    }


def render(report: dict) -> str:
    lines: list[str] = []
    if report["mode"] == "parse-issue":
        i = report["issue"]
        lines.append("#%s [%s] %s" % (i["number"], i["state"], i["title"]))
        lines.append("  assignees: %s  labels: %s  comments: %s" % (
            ", ".join(filter(None, i["assignees"])) or "—",
            ", ".join(filter(None, i["labels"])) or "—", i["comments"]))
        for key, label in (("open_pr_references", "OPEN PR references"),
                           ("merged_pr_references", "MERGED (in own repo) PR references"),
                           ("other_cross_references", "other cross-references")):
            rows = report[key]
            lines.append("  %s (%d):" % (label, len(rows)))
            for r in rows:
                extra = " (merged in own repo)" if r.get("merged") else ""
                where = " @%s" % r["repository"] if r.get("repository") else ""
                lines.append("    %s #%s [%s%s]%s %s" % (
                    "PR" if r["is_pr"] else "issue", r["number"], r["state"], extra, where, r["title"]))
        if report["referencing_commits"]:
            lines.append("  referencing commits: " +
                         ", ".join(c["sha"] for c in report["referencing_commits"]))
        for hint in report["dedupe_hints"]:
            lines.append("  hint: " + hint)
    else:
        lines.append("search results (%d):" % len(report["results"]))
        for r in report["results"]:
            lines.append("  #%s [%s] %s" % (r["number"], r["state"], r["title"]))
    lines.append("Apply the DEDUPLICATE gate before working on this issue.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Parse captured issue/PR data for duplicate-work analysis.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_cmd = sub.add_parser("commands", help="print capture commands to run with gh")
    p_cmd.add_argument("--slug", required=True, help="OWNER/REPO")
    p_cmd.add_argument("--issue", required=True, type=int, help="issue number")

    p_issue = sub.add_parser("parse-issue", help="aggregate captured issue + timeline JSON")
    p_issue.add_argument("--issue-file", required=True)
    p_issue.add_argument("--timeline-file", action="append", default=[])

    p_search = sub.add_parser("parse-search", help="parse captured search results into a structured fragment")
    p_search.add_argument("--results-file", required=True)
    p_search.add_argument("--kind", default="keyword_issue_search",
                          choices=["keyword_issue_search", "keyword_pr_search"],
                          help="which workflow signal this capture represents")

    p_bundle = sub.add_parser("bundle", help="merge issue + timeline + search captures into ONE coherent DUPLICATE_WORK_EVIDENCE bundle (repository identity + capture timestamp + digest)")
    p_bundle.add_argument("repo", nargs="?", default=".",
                          help="repository working copy (provides repository identity)")
    p_bundle.add_argument("--issue-file")
    p_bundle.add_argument("--timeline-file", action="append", default=[])
    p_bundle.add_argument("--search-file", action="append", default=[])
    p_bundle.add_argument("--base-sha",
                          help="session base SHA to bind the bundle to the "
                               "current revision (recommended: git rev-parse HEAD)")
    p_bundle.add_argument("--out", help="write the bundle JSON here")

    for p in (p_cmd, p_issue, p_search, p_bundle):
        p.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.cmd == "commands":
        if not SLUG_RE.match(args.slug):
            print("error: --slug must be OWNER/REPO", file=sys.stderr)
            return 2
        if args.issue <= 0:
            print("error: --issue must be a positive integer", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps({"capture_commands": capture_commands(args.slug, args.issue)}, indent=2))
        else:
            print("Run these with gh (or take the same requests from a platform tool):")
            for c in capture_commands(args.slug, args.issue):
                print("  " + c)
        return 0

    if args.cmd == "parse-issue":
        report = parse_issue(Path(args.issue_file), [Path(t) for t in args.timeline_file])
    elif args.cmd == "parse-search":
        report = parse_search(Path(args.results_file))
        report["type"] = "DUPLICATE_WORK_EVIDENCE_FRAGMENT"
        report["signal"] = args.kind
        report["captured_at"] = report.get("captured_at") or __import__(
            "datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        report["digest"] = hashlib.sha256(json.dumps(
            {k: v for k, v in report.items() if k != "digest"},
            sort_keys=True).encode()).hexdigest()
    elif args.cmd == "bundle":
        repo = Path(args.repo).resolve()
        issue_file = Path(args.issue_file) if args.issue_file else None
        if args.issue_file and not issue_file.exists():
            print("error: %s does not exist" % issue_file, file=sys.stderr)
            return 3
        bundle = build_bundle(repo, issue_file,
                              [Path(x) for x in args.timeline_file],
                              [Path(x) for x in args.search_file],
                              base_sha=args.base_sha)
        if args.out:
            Path(args.out).write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
            print("bundle written: %s (digest %s…, repository %s)"
                  % (args.out, bundle["digest"][:12], bundle["repository_id"]))
        else:
            print(json.dumps(bundle, indent=2))
        return 0

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
