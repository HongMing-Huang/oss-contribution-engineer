# Contribution Workflows (strategy sequencing)

Which modes run in which order for each contribution situation. Mode table and
the state machine live in SKILL.md; this file holds the per-strategy detail.
The DEDUPLICATE gate and STOPPING classifications apply to every strategy.

## Strategy A — existing issue (Mode 2 → 4 → 5)

1. Recon (SKILL.md § Repository recon).
2. Triage the issue: body, labels, assignees, comments, linked PRs, author branches,
   recent commits in the area, maintainer responses, duplicate/closed attempts.
   `duplicate_work_scan.py commands OWNER/REPO#N` prints the exact `gh` capture
   commands; `parse-issue` / `parse-search` / `bundle` aggregate the captured JSON
   (a platform tool may substitute; record which).
3. Classify per the DEDUPLICATE gate. If not GOOD_CANDIDATE/AVAILABLE → report and stop.
4. Investigation Only on the reported behavior: reproduce or disprove (Mode 4).
5. If confirmed and the user asks for a fix: Fix path (below) from RED onward.
6. PR Preparation only after REVIEW passes.

## Strategy B — bug hunt (Mode 3)

1. Recon + architecture read; skim recent bug-fix history for violated invariants.
2. Hunt with the structured lenses in references/bug-hunting.md: cross-implementation
   parity (sync/async, streaming/non-streaming, provider A vs B, platform), sibling paths
   of recent fixes, error-handling and cleanup paths, resource lifecycles, protocol
   contract comparison against version-appropriate docs, missing/skipped negative tests.
3. Pick one candidate; run the DEDUPLICATE gate (issues + PRs + history).
4. Build a reproducer; fill the Evidence Record (references/proof-standard.md).
5. Report the Candidate Report (assets/candidate-report.md). Patching happens only if
   the user then requests Mode 5, entering at RED.

## Fix path (Mode 5)

RED → PATCH → GREEN → REGRESSION → CONTRIBUTOR_UNDERSTANDING → REVIEW → PR_READY,
exactly per the state machine. Produce assets/implementation-plan.md (PATCH PLAN) before
editing production code, assets/change-walkthrough.md after REGRESSION, and
assets/review-report.md from the adversarial pass. Before drafting the PR, profile how
this project's own contributors write merged PRs (`pr_style.py commands` → capture →
`profile`) and mirror that profile — title style, body length, commit conventions —
instead of any generic template. Prepare, never publish, the PR draft
(assets/pull-request-template.md) — publishing needs REMOTE_WRITE.

## Review-response path (Mode 9)

A published PR receiving review comments does not end the run. Classify each concern
(correctness, design, scope, test coverage, compatibility, style, documentation,
maintainability, question), inspect the relevant source and evidence, then explain it
to the contributor with the 5-part review block before any upstream reply is drafted.
Then either modify (re-enter PATCH; affected head-bound evidence is STALE and must be
re-run) or prepare a respectful evidence-backed response — never automatic agreement,
and never a blind rewrite: a design objection is resolved in discussion first. Push
fixes as new commits (not squashed); signal readiness explicitly (re-request / PTAL);
classify the terminal outcome with upstream_state.py — MERGED is the only success.
Full protocol: references/review-response.md; worksheet: assets/review-response.md.
