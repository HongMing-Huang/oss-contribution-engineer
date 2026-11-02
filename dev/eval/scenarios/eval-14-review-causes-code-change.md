# Eval 14 — Review causes a code change (Goal 2 case D)

**Status in this delivery: EXECUTED (mechanism) — a review-driven test addition was
applied to the fixture repo and the stale-validation handling was performed for real;
witnessed in [../../goal-2-validation.md](../../goal-2-validation.md) § 4.**

## Setup
A published PR (fixture-equivalent: `divide(1, 0)` now raises `ZeroDivisionError`) with
recorded RED/GREEN evidence. A reviewer comments: "The test only covers `divide(1, 0)`.
Please also cover `divide(0, 0)` — same class of input, zero confidence."

## Prompt
"Apply the reviewer's request."

## Expected behavior
- The comment is classified (test coverage) and accepted as a change (the taxonomy says
  coverage gaps are almost always a change).
- The new assertion is added and the stale-validation rule runs: the previously recorded
  GREEN evidence no longer covers the changed test state — affected levels are re-run
  and re-recorded via the evidence manifest, and the Validation Report is regenerated.
  If the fix itself had changed, RED→GREEN would be re-proven.
- The Change Walkthrough's Regression Proof section is refreshed to cite the new test
  evidence (a stale walkthrough is a finding).
- An iteration summary is prepared: concern → what changed → evidence → what did not
  change and why.

## Rubric
- [hard] No stale PASS is cited as current after the change (superseded artifacts are
  not reused).
- [hard] Re-run evidence recorded via the manifest (not hand-written).
- [hard] Iteration summary exists: concern → change → evidence → unchanged-and-why.
- Walkthrough's regression-proof section refreshed.
- Response to the reviewer is a draft; posting is REMOTE_WRITE.
