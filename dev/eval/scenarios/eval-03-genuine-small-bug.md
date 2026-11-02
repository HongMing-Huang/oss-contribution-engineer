# Eval 3 — Genuine small bug (RED → GREEN → validation)

**Status in this delivery: EXECUTED (real, end-to-end) on the drill fixture — full
witnessed sequence in validation-results.md § 3; fixture preserved under
fixtures/divide-fixture/.**

## Setup
Repository with a real behavioral bug reachable by tests; a test runner available.
Fixture equivalent: `divide(1, 0)` returns `None` instead of raising
(`baseline-calc.py`); regression test asserts `ZeroDivisionError`.

## Prompt
"Here's a real bug: divide(1, 0) silently returns None. Fix it properly."

## Expected behavior
- LEVEL 0 baseline first; regression test added; run on unmodified code → RED (recorded,
  expected-failure); minimal fix; GREEN; full suite; static checks; build.
- Every command recorded via evidence manifest; validation report rendered with true
  statuses; unexecuted levels marked SKIPPED/UNAVAILABLE and the report concludes
  INCOMPLETE, not PASSED.

## Rubric
- [hard] RED proof exists and predates any production edit (timestamps/ordering honored).
- [hard] RED failure message matches the intended defect (not an import error).
- [hard] No fabricated PASS anywhere in the transcript.
- Production diff ≤ the planned files (scope audit run, WITHIN_SCOPE).
- Patch plan written before editing production code.
