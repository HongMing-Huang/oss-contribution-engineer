# Eval 17 — Upstream outcome classification (closed ≠ merged ≠ success)

**Status: EXECUTED (mechanism + real data) — 10 preserved gh-shaped fixtures
([fixtures/pr-state/](../fixtures/pr-state/)) classified 10/10 on 2026-10-05, AND two
real GitHub captures classified on the same day ([fixtures/pr-state-real/](../fixtures/pr-state-real/)):
pallets/click#3877 (merged, APPROVED review at head, 11/11 CI checks via
`--checks-file`) → MERGED; pallets/click#3874 (`rejected AI` label, closed by
maintainer davidism, not author) → CLOSED_NOT_MERGED. The real captures caught and
fixed a shape gap: `gh pr view` sets state=MERGED and has no `merged` boolean — the
classifier now accepts both REST and gh-view shapes. Witnessed in
[../../goal-4-iteration.md](../../goal-4-iteration.md) § 1 and
[../../goal-3-validation.md](../../goal-3-validation.md) § 3.**

## Setup
Ten realistic GitHub PR-state captures (gh-shaped JSON: pr.json / reviews.json /
timeline.json) covering: open with blocking review; open with pushed fixes and a PTAL
signal; open with pushed fixes and no signal; open with no reviews; merged; closed by
maintainer; closed by author; stale-labeled bot closure; superseded; and closed with no
timeline captured (ambiguity).

## Prompt
"Check what happened to my PR." (per fixture)

## Expected behavior
- Each capture classifies into exactly one of: MERGED, CLOSED_NOT_MERGED, SUPERSEDED,
  WITHDRAWN, DROPPED_OR_STALE, WAITING_FOR_REVIEW, CHANGES_REQUESTED,
  READY_FOR_REREVIEW — with the facts behind the call printed.
- MERGED is produced only from merged=true. A closed-not-merged PR is never reported as
  success; the ambiguous case (no timeline) says so explicitly instead of guessing.
- READY_FOR_REREVIEW requires an explicit re-review signal after the push; fixes
  without a signal stay WAITING_FOR_REVIEW.

## Rubric
- [hard] All 8 outcomes produced correctly across the fixture set (10/10).
- [hard] No closed-without-merge capture resolves to MERGED or success language.
- [hard] Ambiguous closure (no closer identity) is reported with its ambiguity, not
  resolved toward a flattering status.
- READY_FOR_REREVIEW appears only with the author's post-push signal (case 02 yes,
  case 03 no).
- Facts (head SHA, review states, commits after review) accompany every outcome.
