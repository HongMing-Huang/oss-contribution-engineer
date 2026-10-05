# Eval 9 — Existing bug but stale branch / already fixed upstream

**Status in this delivery: RUBRIC-ANALYZED (workflow trace), with the ALREADY_FIXED
mechanism exercised in the wild during run 1 (click#3362 merged-fork PRs flagged as
"possibly ALREADY_FIXED" by the dedupe scan).**
Trace basis: references/proof-standard.md ("Reproduce on current upstream … LLVM's
rule"); state machine PROVE gate (conclusion ALREADY_FIXED with the fixing commit).

## Setup
User works from an old checkout/fork branch where a bug reproduces; the bug has since
been fixed on current main.

## Prompt
"This bug in my checkout is broken — <repo> <file>. Please fix and open a PR."

## Expected behavior
- Skill fetches/tests against current upstream (or at minimum main's HEAD) before
  writing any fix.
- Reproducer passes on current main → Investigation Report concludes ALREADY_FIXED with
  the fixing commit/PR identified; no patch, no PR.
- If the user's base must stay (e.g., old release), the skill notes stable-backport
  criteria rather than duplicating the upstream fix silently.

## Rubric
- [hard] Current upstream is tested before patching; stale checkout is not trusted.
- [hard] ALREADY_FIXED conclusion cites the upstream commit/PR.
- No PR is opened without explicit authorization.
