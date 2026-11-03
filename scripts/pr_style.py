#!/usr/bin/env python3
"""pr_style.py — capture and profile how a project's contributors actually
write merged PRs, so a new PR mirrors the project's own conventions instead
of a generic (visibly AI-flavored) template.

Parse-only, like duplicate_work_scan.py: this script never touches the
network. `commands` prints the exact gh captures to run; `profile` turns the
captured JSON into a PR_STYLE_PROFILE artifact (with digest) the PR-draft
step must match.

Usage:
  pr_style.py commands OWNER/REPO [--count 10]
  pr_style.py profile <capture.json>

Exit codes: 0 ok, 2 usage error, 3 bad capture file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

CONVENTIONAL_RE = re.compile(r"^[a-z]+(\([^)\s]{1,30}\))?!?:\s", re.I)
IMPERATIVE_STARTS = {
    "add", "fix", "remove", "refactor", "update", "use", "make", "move",
    "rename", "replace", "support", "handle", "avoid", "enable", "disable",
    "drop", "bump", "clean", "split", "merge", "return", "throw", "skip",
    "allow", "prevent", "introduce", "implement", "improve", "correct",
    "change", "write", "read", "set", "get", "build", "test", "docs",
    "修复", "新增", "移除", "重构", "支持", "更新", "调整",
}
ISSUE_LINK_RE = re.compile(r"\b(fix|close|resolve)[sd]?\b[^#\n]*#\d+|#\d+", re.I)


def cmd_commands(args) -> int:
    repo = args.repo
    n = args.count
    print("# Run these with gh, save each block's JSON to a file:")
    print("gh pr list -R %s --state merged --limit %d \\" % (repo, n))
    print("  --json number,title,body,additions,deletions,changedFiles,"
          "commits,author,mergedAt,labels \\")
    print("  > prs-merged.json")
    print("# tip: to profile the subsystem you are touching, add "
          "--search '<area keyword>' before --json,")
    print("#       or raise --limit to 20 for a steadier sample.")
    print("# then: pr_style.py profile prs-merged.json")
    return 0


def _median(values: list) -> float:
    return round(statistics.median(values), 1) if values else 0


def _first_word(text: str) -> str:
    w = re.sub(r"^[^\w]+", "", (text or "").strip()).split()
    return w[0].lower() if w else ""


def _classify_title(title: str) -> dict:
    return {
        "conventional": bool(CONVENTIONAL_RE.match(title or "")),
        "imperative_start": _first_word(title) in IMPERATIVE_STARTS,
        "chars": len(title or ""),
    }


def _classify_body(body: str) -> dict:
    b = body or ""
    return {
        "has_headings": "\n## " in b or b.startswith("## "),
        "has_checklist": bool(re.search(r"^- \[[ xX]\]", b, re.M)),
        "links_issue": bool(ISSUE_LINK_RE.search(b)),
        "chars": len(b),
    }


def _classify_commits(commits: list) -> dict:
    heads = [c.get("messageHeadline", "") for c in commits or []]
    return {
        "count": len(heads),
        "conventional": sum(1 for h in heads if CONVENTIONAL_RE.match(h)),
        "imperative_start": sum(1 for h in heads
                                if _first_word(h) in IMPERATIVE_STARTS),
        "median_chars": _median([len(h) for h in heads]) if heads else 0,
    }


def cmd_profile(args) -> int:
    src = Path(args.capture)
    if not src.is_file():
        print("error: %s is not a file — run the `commands` step first" % src,
              file=sys.stderr)
        return 3
    try:
        prs = json.loads(src.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print("error: cannot parse %s: %s" % (src, e), file=sys.stderr)
        return 3
    if not isinstance(prs, list) or not prs:
        print("error: capture must be a non-empty JSON array of merged PRs",
              file=sys.stderr)
        return 3

    titles = [_classify_title(p.get("title", "")) for p in prs]
    bodies = [_classify_body(p.get("body") or "") for p in prs]
    commit_stats = [_classify_commits(p.get("commits") or []) for p in prs]
    adds = [p.get("additions", 0) for p in prs]
    dels = [p.get("deletions", 0) for p in prs]
    files = [p.get("changedFiles", 0) for p in prs]
    n = len(prs)

    pct = lambda x: round(100.0 * x / n)  # noqa: E731
    conv_titles = sum(1 for t in titles if t["conventional"])
    imper_titles = sum(1 for t in titles if t["imperative_start"])
    conv_commits = sum(c["conventional"] for c in commit_stats)
    imper_commits = sum(c["imperative_start"] for c in commit_stats)
    total_commits = sum(c["count"] for c in commit_stats)

    artifact = {
        "type": "PR_STYLE_PROFILE",
        "schema_version": 1,
        "source_capture": str(src),
        "capture_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
        "sample_size": n,
        "generated_by": "pr_style.py profile",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "titles": {
            "conventional_commit_pct": pct(conv_titles),
            "imperative_start_pct": pct(imper_titles),
            "median_chars": _median([t["chars"] for t in titles]),
            "examples": [p.get("title", "") for p in prs[:3]],
        },
        "bodies": {
            "with_headings_pct": pct(sum(1 for b in bodies if b["has_headings"])),
            "with_checklist_pct": pct(sum(1 for b in bodies if b["has_checklist"])),
            "linking_issue_pct": pct(sum(1 for b in bodies if b["links_issue"])),
            "median_chars": _median([b["chars"] for b in bodies]),
        },
        "commits": {
            "total": total_commits,
            "conventional_pct": pct(conv_commits) if total_commits else 0,
            "imperative_pct": pct(imper_commits) if total_commits else 0,
            "median_headline_chars": _median(
                [c["median_chars"] for c in commit_stats if c["count"]]),
        },
        "size": {
            "median_additions": _median(adds),
            "median_deletions": _median(dels),
            "median_changed_files": _median([float(f) for f in files]),
        },
        "guidance": [],
    }
    g = artifact["guidance"]
    if conv_titles * 2 >= n:
        g.append("titles: conventional-commit style dominates — use it "
                 "(match the dominant scope prefix)")
    elif conv_titles == 0:
        g.append("titles: NO conventional-commit prefixes in the sample — "
                 "do not introduce them; write a plain sentence")
    g.append("titles: start with an imperative verb (%d%% of the sample do); "
             "median %d chars — do not exceed it by much"
             % (pct(imper_titles), artifact["titles"]["median_chars"]))
    g.append("body: %d%% carry headings, %d%% a checklist, %d%% link an "
             "issue — copy the project's own structure, not a template"
             % (artifact["bodies"]["with_headings_pct"],
                artifact["bodies"]["with_checklist_pct"],
                artifact["bodies"]["linking_issue_pct"]))
    g.append("body: median %d chars — matching the project means being as "
             "brief as its contributors are" % artifact["bodies"]["median_chars"])
    g.append("size: median merged PR here is +%.0f/−%.0f across %.0f files — "
             "a draft far above that needs a reason"
             % (artifact["size"]["median_additions"],
                artifact["size"]["median_deletions"],
                artifact["size"]["median_changed_files"]))
    artifact["digest"] = hashlib.sha256(json.dumps(
        {k: v for k, v in artifact.items() if k != "digest"},
        sort_keys=True).encode()).hexdigest()

    out = Path(args.out) if args.out else src.with_name("pr-style-profile.json")
    out.write_text(json.dumps(artifact, indent=2))
    print("PR_STYLE_PROFILE written: %s (sample %d merged PRs, digest %s…)"
          % (out, n, artifact["digest"][:12]))
    for line in g:
        print("  - %s" % line)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("commands", help="print the gh capture commands")
    p.add_argument("repo", help="OWNER/REPO of the UPSTREAM project")
    p.add_argument("--count", type=int, default=10)
    p.set_defaults(func=cmd_commands)
    p = sub.add_parser("profile", help="profile a captured merged-PR JSON")
    p.add_argument("capture")
    p.add_argument("--out")
    p.set_defaults(func=cmd_profile)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
