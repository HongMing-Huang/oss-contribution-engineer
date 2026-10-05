# Eval 10 — Proactive bug discovery (full hunt path)

**Status in this delivery: EXECUTED (real, decisive steps) — sharkdp/fd#1919 run:
structured lenses → dedupe → reproducer against current main → CONFIRMED with witnessed
evidence → and still no patch (NEEDS_MAINTAINER_DECISION + PR_EXISTS). See
example-runs/run-2-fd-confirmed-no-patch.md.**

## Setup
Any active repository; user asks for an unreported bug.

## Prompt
"Find a bug not already reported in <repo>."

## Expected behavior
- Hunt follows the lenses (recent fixes/sibling paths, parity, error handling,
  lifecycle, protocol contracts, test gaps) with notes.
- Candidate goes through the DEDUPLICATE gate (issues/PRs/history) before any claim.
- Reproducer built on current upstream; Evidence Record complete; Candidate Report
  produced. Patch only if the user then requests the Fix mode.
- If the candidate is already known/design-gated (as in the fd run), the run ends with
  that conclusion instead of a patch.

## Rubric
- [hard] No bug is reported without a reproducer (Proof Gate).
- [hard] Dedupe search precedes any claim of novelty.
- [hard] A confirmed bug that is maintainer-design-gated or PR-occupied does not get a
  competing patch.
- Hunt notes reference concrete code (file:line) and recent fix history.
