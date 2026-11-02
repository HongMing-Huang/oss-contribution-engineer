# Eval 12 — AI-style PR description (Goal 2 case B)

**Status in this delivery: EXECUTED (mechanism) — the rewrite was performed for real
against the divide-fixture patch; result recorded in
[../../goal-2-validation.md](../../goal-2-validation.md) § 4.**

## Setup
A validated fix exists (fixture-equivalent: `divide` raising `ZeroDivisionError`).
The contributor drafts the PR description as:

> "Implemented input validation in calc.py. Updated the test file. Added tests for
> division. Everything passes."

## Prompt
"Use this as the PR description — it's accurate, I did all of that."

## Expected behavior
- The skill rewrites the draft around: Problem, Root Cause, Change, Why this approach,
  Tests executed, Risks, Non-goals, Related issue — each section answering "why", not
  just "what".
- The rewrite states what was actually tested (RED on unmodified upstream, GREEN,
  suite) and what was not, from the evidence manifest — never the vague "everything
  passes".
- No fabricated content is introduced by the rewrite: only facts already evidenced.

## Rubric
- [hard] The AI-style change-log sentences ("Implemented X", "Updated Y", "Added
  tests") do not survive without a why.
- [hard] Problem appears before implementation detail (kernel: "Describe your problem").
- Tests section distinguishes executed vs not-tested from manifest evidence.
- Non-goals / what-did-not-change is stated.
- A reviewer can decide the change is worth merging before opening the diff.
