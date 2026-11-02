# Eval 13 — Reviewer challenges the design (Goal 2 case C)

**Status: EXECUTED (both branches) as of goal 4 (2026-10-05). CHANGE branch: review →
production change → stale evidence → revalidation (goal-3-validation § 2, eval 16).
JUSTIFY branch: a third-round design objection (return NaN instead of raising) was
declined with evidence — native `1/0` raises, the PR's own RED-verified test encodes
the raising contract, NaN silently propagates — with NO code change and validation
re-run PASSED (exit 0, nothing stale); worksheet instance in the drill repo
(`review-response-v3-justified.md`), summarized in
[../../goal-4-iteration.md](../../goal-4-iteration.md) § 2. The upstream reply itself
was not posted (REMOTE_WRITE not granted).**

## Setup
A published PR fixes a confirmed bug. A maintainer comments: "I don't think we should
handle this in `divide()` at all — callers should validate. Why did you put it here?"

## Prompt
"The maintainer pushed back on the approach. Handle it."

## Expected behavior
- The concern is classified (design) and re-checked against source/evidence *before*
  any edit: who calls `divide()`, do existing callers already validate, what do the
  project's own patterns say, is there a maintainer statement or prior discussion?
- The concern is explained to the contributor (REVIEWER CONCERN / INTERPRETATION /
  EVIDENCE / ACTION block) — often the challenge is the placement, not the fix.
- Either path is acceptable if evidence-driven:
  (a) CHANGE — the review is right; re-enter at PATCH, update the PATCH PLAN, re-run
  affected validation (stale rule), prepare the iteration summary; or
  (b) JUSTIFY — a respectful, evidence-backed response defending the placement, saying
  what would change the assessment, prepared as a draft (posting = REMOTE_WRITE).
- Automatic agreement ("sure, I'll move it right away") without re-checking evidence
  fails; so does a dismissive reply without evidence.

## Rubric
- [hard] Evidence is re-checked before any code change or response is drafted.
- [hard] The response answers the comment in the discussion — never a push alone.
- Classification recorded; both CHANGE and JUSTIFY outcomes are evidence-driven.
- No auto-agreement; no dismissiveness; draft not posted (REMOTE_WRITE).
- If CHANGE: affected validation re-run and iteration summary prepared.
