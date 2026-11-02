#!/usr/bin/env python3
"""upstream_state.py — classify the real state of an upstream PR from captured data.

The Skill must never treat "PR opened" as success, never interpret closed=true as a
successful contribution, and never self-report "review handled" / "CI passed" /
"ready for rereview". This script turns captured platform JSON into one of eight
evidence-backed lifecycle statuses plus the facts behind them.

Parse-only, like duplicate_work_scan.py: no network. Capture the data with your own
tooling (the `commands` subcommand prints exact `gh` invocations), then classify.

Outcomes
--------
  MERGED               closed with merged=true — the only success terminal
  CLOSED_NOT_MERGED    closed without merge by a maintainer/other actor (rejection etc.)
  WITHDRAWN            closed without merge by the PR author
  DROPPED_OR_STALE     closed without merge by inactivity (bot/stale label, long idle)
  SUPERSEDED           closed without merge, superseded by another PR/commit
  WAITING_FOR_REVIEW   open; latest review demands changes but fixes were pushed after
                       it (or no review yet) — and the contributor has NOT signaled
  CHANGES_REQUESTED    open; latest review demands changes and HEAD has not moved since
  READY_FOR_REREVIEW   open; fixes pushed after the last review AND the contributor
                       signaled readiness (re-requested review / PTAL comment after push)

Ambiguity policy: when signals are missing (no timeline file, no closer identity),
the classifier says so explicitly and picks the more-honest branch (never MERGED, never
READY_FOR_REREVIEW without a signal).

Usage
-----
  upstream_state.py commands --slug OWNER/REPO --pr 123
  upstream_state.py classify --pr-file pr.json [--reviews-file reviews.json]
                             [--timeline-file timeline.json] [--local-repo PATH]

`--local-repo` (optional) cross-checks the PR head SHA against a local checkout and
reports whether local validation evidence could still describe the PR head.

Exit codes: 0 = classified, 2 = usage, 3 = missing input file, 4 = malformed JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

OUTCOMES = ["MERGED", "CLOSED_NOT_MERGED", "SUPERSEDED", "WITHDRAWN",
            "DROPPED_OR_STALE", "WAITING_FOR_REVIEW", "CHANGES_REQUESTED",
            "READY_FOR_REREVIEW"]

REREVIEW_SIGNALS = ("ptal", "please take another look", "re-review",
                    "ready for another review", "rereview", "please review again")


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


def pr_field(pr: dict, *names, default=None):
    """Fetch the first present field among GitHub REST / GraphQL naming variants."""
    for name in names:
        if name in pr and pr[name] is not None:
            return pr[name]
    return default


def author_login(pr: dict) -> str:
    author = pr_field(pr, "author", "user", default={}) or {}
    return author.get("login") or ""


def closed_by(pr: dict, timeline: list | None):
    closer = pr_field(pr, "closedBy", default=None)
    if closer:
        return closer.get("login") or closer.get("name") or str(closer)
    if timeline:
        for ev in reversed(timeline):
            if ev.get("event") == "closed" and ev.get("actor"):
                return ev["actor"].get("login", "?")
    return None


def latest_review(reviews):
    if not reviews:
        return None
    ordered = sorted(reviews, key=lambda r: r.get("submitted_at", ""))
    return ordered[-1] if ordered else None


def commits_after(pr: dict, reviews, review) -> list[dict]:
    """Commits pushed after the given review submission (by submitted_at vs commit date,
    plus the review's own commit_id anchor when present)."""
    if review is None:
        return []
    anchor = review.get("submitted_at", "")
    anchor_cid = review.get("commit_id") or ""
    commits = pr_field(pr, "commits", default=None) or []
    after = []
    for c in commits:
        info = c.get("commit") or c.get("parents") and c or {}
        date = (c.get("commit") or {}).get("committer", {}).get("date") or c.get("date", "")
        sha = c.get("sha") or c.get("oid", "")
        if anchor and date and date > anchor:
            after.append(c)
        elif anchor_cid and sha and sha != anchor_cid and not date:
            after.append(c)
    return after


def detect_supersession(pr: dict, timeline: list | None) -> str | None:
    body = (pr_field(pr, "body", default="") or "").lower()
    if "superseded by #" in body:
        return "PR body says superseded"
    if timeline:
        for ev in timeline:
            if ev.get("event") == "cross-referenced":
                src = (ev.get("source") or {}).get("issue") or {}
                title = (src.get("title") or "").lower()
                if "supersede" in title:
                    return "cross-referenced '%s'" % src.get("title")
    return None


def detect_stale_closure(pr: dict, timeline: list | None) -> str | None:
    labels = [str(l).lower() for l in (pr_field(pr, "labels", default=[]) or [])]
    if any("stale" in l or "lifecycle/stale" in l for l in labels):
        return "stale label present"
    if timeline:
        for ev in timeline:
            actor = (ev.get("actor") or {}).get("login", "")
            if ev.get("event") in ("closed", "issue_comment") and actor.endswith(("-bot", "-robot")) \
                    and ev.get("event") == "closed":
                return "closed by automation (%s)" % actor
    return None


def detect_rereview_signal(pr: dict, timeline: list | None, author: str) -> str | None:
    """Evidence the contributor asked for another look AFTER pushing fixes."""
    if not timeline:
        return None
    pushed_at = None
    for ev in timeline:
        if ev.get("event") == "push":
            pushed_at = ev.get("created_at") or pushed_at
    for ev in timeline:
        if ev.get("event") == "issue_comment":
            who = (ev.get("actor") or {}).get("login", "")
            body = (ev.get("body") or "").lower()
            when = ev.get("created_at", "")
            if who == author and any(s in body for s in REREVIEW_SIGNALS):
                if pushed_at is None or when >= pushed_at:
                    return "author comment at %s: '%s...'" % (when, body[:40])
        if ev.get("event") == "review_requested" and (ev.get("actor") or {}).get("login") == author:
            when = ev.get("created_at", "")
            if pushed_at is None or when >= pushed_at:
                return "review re-requested at %s" % when
    return None


def summarize_checks(checks) -> dict | None:
    """Aggregate captured check-runs (gh api .../commits/SHA/check-runs shape)."""
    if not checks:
        return None
    runs = checks if isinstance(checks, list) else checks.get("check_runs") or []
    if not runs:
        return None
    summary = {"total": len(runs), "completed": 0, "passed": 0, "failed": 0,
               "pending": 0, "failed_names": []}
    for r in runs:
        status = (r.get("status") or "").lower()
        conclusion = (r.get("conclusion") or "").lower()
        if status != "completed":
            summary["pending"] += 1
            continue
        summary["completed"] += 1
        if conclusion in ("success", "neutral", "skipped"):
            summary["passed"] += 1
        else:
            summary["failed"] += 1
            summary["failed_names"].append(r.get("name") or "?")
    return summary


def classify(pr: dict, reviews, timeline):
    facts = {
        "number": pr_field(pr, "number"),
        "author": author_login(pr),
        "state": pr_field(pr, "state", "pr_state"),
        "merged": bool(pr_field(pr, "merged", "mergeCommit", default=False)),
        "head_sha": (pr_field(pr, "headRefOid", default=None)
                     or (pr_field(pr, "head", default={}) or {}).get("sha")),
        "merged_at": pr_field(pr, "mergedAt", "merged_at"),
        "closed_at": pr_field(pr, "closedAt", "closed_at"),
        "labels": [l.get("name") if isinstance(l, dict) else str(l)
                   for l in (pr_field(pr, "labels", default=[]) or [])],
    }
    review = latest_review(reviews)
    if review:
        facts["latest_review"] = {"state": review.get("state"),
                                  "by": (review.get("user") or {}).get("login", "?"),
                                  "at": review.get("submitted_at"),
                                  "commit_id": (review.get("commit_id") or "")[:12]}
    state = (facts["state"] or "").upper()

    # closed shapes: REST gives merged/merged_at booleans; `gh pr view` instead sets
    # state=MERGED (and has no `merged` field at all). Accept both.
    if state in ("CLOSED", "MERGED") or facts["merged"] or facts["merged_at"]:
        if facts["merged"] or facts["merged_at"] or state == "MERGED":
            return "MERGED", facts, "merged (state=%s%s)" % (
                state or "?", ", merged=true" if facts["merged"] else "")
        reason_super = detect_supersession(pr, timeline)
        if reason_super:
            return "SUPERSEDED", facts, reason_super
        reason_stale = detect_stale_closure(pr, timeline)
        if reason_stale:
            return "DROPPED_OR_STALE", facts, reason_stale
        closer = closed_by(pr, timeline)
        if closer is None:
            return ("CLOSED_NOT_MERGED", facts,
                    "closed without merge; closer unknown (no timeline) — NOT treated as success")
        if closer == facts["author"]:
            return "WITHDRAWN", facts, "closed by author %s" % closer
        return "CLOSED_NOT_MERGED", facts, "closed by %s (not author, not merged)" % closer

    # open PR
    if review and review.get("state") == "CHANGES_REQUESTED":
        after = commits_after(pr, reviews, review)
        facts["commits_after_latest_review"] = len(after)
        if not after:
            return "CHANGES_REQUESTED", facts, "latest review requests changes; head unchanged since"
        signal = detect_rereview_signal(pr, timeline, facts["author"])
        if signal:
            return "READY_FOR_REREVIEW", facts, "fixes pushed after review; %s" % signal
        return ("WAITING_FOR_REVIEW", facts,
                "fixes pushed after CHANGES_REQUESTED review but no re-review signal found "
                "(PTAL / re-request needed for READY_FOR_REREVIEW)")
    # open, no blocking review
    signal = detect_rereview_signal(pr, timeline, facts["author"])
    if review and commits_after(pr, reviews, review) and signal:
        return "READY_FOR_REREVIEW", facts, "new commits after last review; %s" % signal
    return ("WAITING_FOR_REVIEW", facts,
            "open; no unresolved CHANGES_REQUESTED review%s"
            % ("" if reviews else " (no review submissions captured)"))


def cmd_commands(slug: str, pr: int) -> int:
    print("# capture with gh (or your platform tool); then classify the captured JSON:")
    print("gh pr view %d --repo %s --json number,state,closedAt,author,"
          "headRefOid,labels,body,commits > pr.json" % (pr, slug))
    print("gh api repos/%s/pulls/%d > pr.json        # REST alternative (merged/merged_at fields)" % (slug, pr))
    print("gh api repos/%s/pulls/%d/reviews > reviews.json" % (slug, pr))
    print("gh api repos/%s/issues/%d/timeline --paginate > timeline.json" % (slug, pr))
    print("HEAD=$(python3 -c \"import json;d=json.load(open('pr.json'));print(d.get('headRefOid') or d.get('head',{}).get('sha',''))\")")
    print("gh api repos/%s/commits/$HEAD/check-runs > checks.json" % slug)
    print("# then:")
    print("upstream_state.py classify --pr-file pr.json --reviews-file reviews.json "
          "--timeline-file timeline.json --checks-file checks.json")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Classify upstream PR state from captured JSON.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_cmd = sub.add_parser("commands", help="print exact capture commands")
    p_cmd.add_argument("--slug", required=True, help="OWNER/REPO")
    p_cmd.add_argument("--pr", required=True, type=int)

    p_cl = sub.add_parser("classify", help="classify from captured JSON files")
    p_cl.add_argument("--pr-file", required=True)
    p_cl.add_argument("--reviews-file")
    p_cl.add_argument("--timeline-file")
    p_cl.add_argument("--checks-file", help="captured check-runs JSON for the PR head "
                                            "(gh api .../commits/SHA/check-runs)")
    p_cl.add_argument("--local-repo", help="optional local checkout to cross-check head SHA")

    args = ap.parse_args()

    if args.cmd == "commands":
        return cmd_commands(args.slug, args.pr)

    pr = load_json(Path(args.pr_file))
    reviews = load_json(Path(args.reviews_file)) if args.reviews_file else None
    timeline = load_json(Path(args.timeline_file)) if args.timeline_file else None
    checks = load_json(Path(args.checks_file)) if args.checks_file else None
    if reviews and isinstance(reviews, dict):
        reviews = reviews.get("reviews") or reviews.get("data") or []
    if timeline and isinstance(timeline, dict):
        timeline = timeline.get("data") or []

    outcome, facts, reason = classify(pr, reviews, timeline)
    ci = summarize_checks(checks)
    if ci:
        facts["ci"] = ("%d/%d checks passed, %d pending%s"
                       % (ci["passed"], ci["completed"], ci["pending"],
                          (", FAILED: " + ", ".join(ci["failed_names"])) if ci["failed"] else ""))

    if args.local_repo:
        local_head = None
        try:
            head_file = Path(args.local_repo) / ".git" / "HEAD"
            ref = head_file.read_text().strip()
            if ref.startswith("ref: "):
                ref_path = Path(args.local_repo) / ".git" / ref[5:]
                local_head = ref_path.read_text().strip()
            else:
                local_head = ref
        except OSError:
            local_head = None
        if local_head:
            match = (local_head == facts.get("head_sha"))
            facts["local_head_matches_pr"] = match
            print("local HEAD %s PR head %s: %s" % (
                local_head[:12], (facts.get("head_sha") or "?")[:12],
                "MATCH — local evidence can describe the PR head" if match
                else "MISMATCH — local validation does not describe the PR head; rebase/rerun"))
        else:
            print("note: could not read local HEAD from %s" % args.local_repo)

    print("OUTCOME: %s" % outcome)
    print("reason: %s" % reason)
    print("facts:")
    for k, v in facts.items():
        print("  %s: %s" % (k, v))
    if outcome not in OUTCOMES:
        print("error: internal — unknown outcome", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
