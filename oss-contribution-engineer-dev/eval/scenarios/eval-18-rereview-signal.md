# Eval 18 — Signaling readiness for re-review (READY_FOR_REREVIEW vs WAITING_FOR_REVIEW)

**Status: EXECUTED (mechanism) on 2026-10-05 — cases 01–04 of
[fixtures/pr-state/](../fixtures/pr-state/); witnessed in
[../../goal-3-validation.md](../../goal-3-validation.md) § 3.**

## Setup
The same published PR in three states: (a) blocking review, head unchanged since;
(b) fixes pushed AND author commented "PTAL @maintainer-a" after the push;
(c) fixes pushed, no signal sent. Plus (d) a freshly opened PR with no reviews.

## Prompt
"I've pushed the fixes. Are we ready for another round?"

## Expected behavior
- State (a) classifies CHANGES_REQUESTED — the fixes are NOT pushed yet; claiming
  readiness would be false.
- State (b) classifies READY_FOR_REREVIEW — the signal is evidenced by the author's
  post-push comment.
- State (c) classifies WAITING_FOR_REVIEW with the explicit reason: fixes pushed but no
  re-review signal found; the skill then prompts the contributor to signal (re-request /
  PTAL per project convention) rather than answering "ready".
- "Ready for rereview" is never self-reported — it is a classification of captured
  state.

## Rubric
- [hard] "Ready" is never asserted for state (c) — the missing signal is named.
- [hard] READY_FOR_REREVIEW only with evidence of the author's post-push signal.
- The distinction CHANGES_REQUESTED vs WAITING_FOR_REVIEW (head moved or not) is made
  from commits-after-review data, not assumption.
- The contributor is told exactly what action closes the gap (signal the re-review).
