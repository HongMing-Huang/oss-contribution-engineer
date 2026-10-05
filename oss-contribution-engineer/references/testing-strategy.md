# Testing Strategy

Verification is layered; each layer either runs (recorded PASS/FAIL) or is recorded
SKIPPED/UNAVAILABLE with a reason. Nothing collapses into "tests pass".

## Levels (cheapest first)

| Level | What | Notes |
|-------|------|-------|
| 0 Baseline | relevant existing tests pass before edits | when practical; a red baseline poisons every later claim |
| 1 Reproducer | prove the bug | Level 1 of the Proof Gate |
| 2 Regression | smallest test that fails (RED) then passes (GREEN) | see sequence below |
| 3 Neighbor | tests for adjacent behavior in the same files | catches unintended behavior change |
| 4 Package | the affected package/module suite | the project's own granularity |
| 5 Static | formatter check, linter, type checker, static analyzer | exactly the ones the project requires (from recon) |
| 6 Build | build the affected package/project | catches packaging-level breakage |
| 7 Integration | integration/e2e when the change crosses boundaries | often needs services; SKIPPED is acceptable if recorded |
| 8 Live external | real provider/API calls | only with credentials and safe test access; never simulate or fabricate |

Record every command through `scripts/evidence_manifest.py`; render with
`scripts/validation_report.py`. A level that could not run appears in the report as
SKIPPED or UNAVAILABLE — visible, not silent.

## RED → GREEN sequence (behavior fixes)

1. Clean baseline (Level 0).
2. Add the smallest regression test that encodes the *expected* behavior.
3. Run it on unmodified production code.
4. Confirm RED — record the full output as evidence.
5. Confirm the failure is the intended defect (message/assertion matches, not an import
   error or unrelated breakage).
6. Modify production code (PATCH).
7. Re-run; confirm GREEN; record output.

**If RED does not happen: STOP.** Possibilities, in order: the bug is already fixed
upstream; the test doesn't exercise the defect; the assumption about expected behavior is
wrong; the test path is wrong; the test is flaky. Investigate — do not adjust the test
until it fails, and never weaken an existing test to manufacture RED.

## Test quality review (the skill reviews tests, not just runs them)

Before accepting a regression test, answer:

- Would it fail if the bug returned? (the regression question)
- Does it assert public behavior or implementation trivia?
- Does it encode the same wrong assumption as the production code?
- Is the assertion precise (exact value/error) rather than `assert result is not None`?
- Is the fixture realistic (production-shaped input, not a toy)?
- Is it deterministic (no sleep, no ordering dependence, no network)?
- Does it cover the actual failure boundary (the branch that was wrong)?
- Are the important negative cases present (and not just the happy path)?
- Do snapshots hide the contract? For protocol/serialization fixes, prefer explicit
  behavioral assertions (exact bytes/fields/status codes).
- Does it need mocks that could mask the defect? Fewer, thinner mocks.

A failing-grade answer is a finding for the REVIEW gate, not a footnote.
