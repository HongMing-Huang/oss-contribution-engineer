#!/usr/bin/env python3
"""Generate the GitHub PR-state fixtures in this directory (goal 3, 2026-10-05).

Run from anywhere: writes 10 case dirs under /tmp/oss-goal3-pr-fixtures shaped like
`gh pr view --json` / `gh api .../reviews` / `gh api .../timeline` output. The copies
in this directory are the preserved artifacts of the run recorded in
../../../goal-3-validation.md. Timestamps are ISO-8601 so string comparison behaves
like production data. Expected classification per case is in the table in
../../../goal-3-validation.md § 3.
"""
import json
from pathlib import Path

OUT = Path("/tmp/oss-goal3-pr-fixtures")
AUTHOR = "contributor-dev"
REVIEWER = "maintainer-a"
T0 = "2026-09-28T10:00:00Z"
T1 = "2026-09-28T12:00:00Z"   # review submitted
T2 = "2026-09-29T09:00:00Z"   # fix pushed
T3 = "2026-09-29T09:30:00Z"   # author PTAL comment
T4 = "2026-10-02T18:00:00Z"   # closure


def commit(sha, date, msg):
    return {"oid": sha, "commit": {"committer": {"date": date}, "message": msg}}


def base_pr(**kw):
    pr = {
        "number": 42,
        "state": "OPEN",
        "merged": False,
        "mergedAt": None,
        "closedAt": None,
        "author": {"login": AUTHOR},
        "headRefOid": "f" * 40,
        "labels": [],
        "body": "Fix divide() to raise on zero divisor.",
        "commits": [commit("e" * 40, T0, "fix: raise on zero divisor")],
    }
    pr.update(kw)
    return pr


def review(state, at, cid=None):
    return {"state": state, "user": {"login": REVIEWER},
            "submitted_at": at, "commit_id": cid or "e" * 40}


def tl(event, at, **kw):
    d = {"event": event, "created_at": at, "actor": {"login": AUTHOR}}
    d.update(kw)
    return d


def case(name, pr, reviews=None, timeline=None):
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "pr.json").write_text(json.dumps(pr, indent=1))
    if reviews is not None:
        (d / "reviews.json").write_text(json.dumps(reviews, indent=1))
    if timeline is not None:
        (d / "timeline.json").write_text(json.dumps(timeline, indent=1))


FIX_SHA = "a" * 40  # the review-fix commit, pushed after the review

case("01-changes-requested",
     base_pr(headRefOid="e" * 40),
     [review("COMMENTED", T0), review("CHANGES_REQUESTED", T1)])

case("02-ready-for-rereview",
     base_pr(headRefOid=FIX_SHA, commits=[
         commit("e" * 40, T0, "fix: raise on zero divisor"),
         commit(FIX_SHA, T2, "review: name the divisor in the error")]),
     [review("CHANGES_REQUESTED", T1)],
     [tl("push", T2), tl("issue_comment", T3, body="Addressed — PTAL @maintainer-a")])

case("03-waiting-no-signal",
     base_pr(headRefOid=FIX_SHA, commits=[
         commit("e" * 40, T0, "fix: raise"),
         commit(FIX_SHA, T2, "review: name the divisor")]),
     [review("CHANGES_REQUESTED", T1)],
     [tl("push", T2)])

case("04-waiting-no-review", base_pr(), [])

case("05-merged",
     base_pr(state="CLOSED", merged=True, mergedAt=T4, closedAt=T4,
             headRefOid=FIX_SHA),
     [review("APPROVED", T3, cid=FIX_SHA)],
     [tl("push", T2), tl("issue_comment", T3, body="PTAL"),
      tl("closed", T4, actor={"login": REVIEWER})])

case("06-closed-not-merged",
     base_pr(state="CLOSED", merged=False, closedAt=T4),
     [review("CHANGES_REQUESTED", T1)],
     [tl("closed", T4, actor={"login": REVIEWER})])

case("07-withdrawn",
     base_pr(state="CLOSED", merged=False, closedAt=T4),
     [],
     [tl("issue_comment", T3, body="This approach is wrong; withdrawing."),
      tl("closed", T4, actor={"login": AUTHOR})])

case("08-dropped-stale",
     base_pr(state="CLOSED", merged=False, closedAt=T4,
             labels=["lifecycle/stale"]),
     [],
     [tl("closed", T4, actor={"login": "k8s-ci-robot"})])

case("09-superseded",
     base_pr(state="CLOSED", merged=False, closedAt=T4,
             body="Superseded by #57 which fixes this properly."),
     [review("CHANGES_REQUESTED", T1)],
     [tl("closed", T4, actor={"login": REVIEWER})])

case("10-ambiguous-closed",
     base_pr(state="CLOSED", merged=False, closedAt=T4))

print("fixtures written to", OUT)
