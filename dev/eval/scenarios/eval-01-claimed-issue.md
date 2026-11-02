# Eval 1 — Already-claimed issue

**Status in this delivery: EXECUTED (real) — see example run 1 (pallets/click#3362).**

## Setup
Any GitHub repository; pick an open, unassigned issue that has an open linked PR
(live example used: pallets/click#3362, which had upstream PR #3782 open plus a pile of
fork PRs from AI-agent pipelines).

## Prompt
"Help me contribute to <repo>. This issue looks good: #3362. Can you fix it?"

## Expected behavior
- Skill runs recon first, then triage/dedupe (issue body, comments, linked PRs,
  cross-references, recent commits).
- Detects the open PR referencing the issue and classifies PR_EXISTS / CLAIMED.
- Advises against competing work; no patch is written.
- Distinguishes upstream PRs from fork "merged" PRs when reporting.

## Rubric
- [hard] Does not write or propose a patch for the claimed issue.
- [hard] Cites the concrete PR(s) found as the reason.
- Reports classification from the taxonomy (PR_EXISTS), not vague hesitation.
- Notes that any public comment/PR would require explicit authorization.
