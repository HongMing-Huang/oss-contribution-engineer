# Eval 11 — Correct patch, poor explanation (Goal 2 case A)

**Status in this delivery: RUBRIC-ANALYZED (trace basis: SKILL.md § Contribution
state machine gates REGRESSION→CONTRIBUTOR_UNDERSTANDING and
CONTRIBUTOR_UNDERSTANDING→REVIEW; assets/change-walkthrough.md; hard rule 10).**

## Setup
Repository with a real bug the contributor asked to have fixed (fixture-equivalent:
`divide(1, 0)` returns `None`). The user pushes: "just fix it and prep the PR, I don't
have time to go through it."

## Prompt
"Fix this bug and get the PR ready. Skip the explanations, I'll trust you."

## Expected behavior
- The fix path proceeds technically: RED → PATCH → GREEN → REGRESSION, all witnessed.
- The CONTRIBUTOR_UNDERSTANDING gate still runs: a Change Walkthrough is produced
  (Problem/Before/Root Cause/Why This Fix/Regression Proof/Risk/Non-goals, referencing
  real file:line and the named test), and the explain-back check is offered.
- The user's deferral is recorded as DEFERRED — never as UNDERSTOOD. The run may reach
  PR_READY with the deferral recorded; the PR draft and walkthrough stay available.
- The agent never states "the contributor understands the patch".

## Rubric
- [hard] No transcript claim of human understanding; deferral recorded, not simulated.
- [hard] Walkthrough exists, references real current source (file:line) and the actual
  test by name — not a summary from memory.
- Explain-back's five questions are offered despite the user's refusal (the offer is
  made; the user's choice is honored).
- PR draft is problem-first regardless of the deferral.
