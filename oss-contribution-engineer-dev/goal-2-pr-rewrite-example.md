# Executed mechanism — eval 12: AI-style PR description rewritten (2026-10-05)

Scenario: a validated fixture fix (divide raises ZeroDivisionError on zero divisor;
RED/GREEN witnessed in /tmp/oss-goal2-drill, manifest artifacts 001–004). The
contributor proposed this description:

> "Implemented input validation in calc.py. Updated the test file. Added tests for
> division. Everything passes."

Rewrite produced by the skill's PR template rules (assets/pull-request-template.md):
every section answers *why*, problem precedes implementation, testing claims come only
from the evidence manifest, and nothing is asserted that was not executed.

---

## PR Draft — make divide() raise ZeroDivisionError on a zero divisor

### Problem
`divide(1, 0)` silently returned `None` instead of raising, so any caller that divides
by a computed zero got a corrupted downstream value (e.g., `None` propagating into
arithmetic) rather than a clear error at the fault site.

### Root Cause
`calc.py::divide` treated the zero-divisor case as a valid result path and returned
`None`, where the rest of the module signals invalid arithmetic input by raising.

### Change
`divide()` now raises `ZeroDivisionError("division by zero is not supported")` when the
divisor is zero (calc.py:4-5). One production file touched; the zero check moved from
"return a value" to "raise", matching the module's error-signaling convention.

### Why this approach
Raising at the fault site preserves the caller's stack trace and matches Python's own
arithmetic semantics (`1/0` raises `ZeroDivisionError` natively); returning a sentinel
`None` forces every caller to defend against a case they cannot detect. Alternatives
rejected: returning a default value (masks the error), introducing a custom exception
type (a public-API addition no caller asked for).

### Tests executed
- `test_divide_by_zero_raises` — RED on unmodified upstream (artifact 002: genuine
  `AssertionError: divide(1, 0) returned instead of raising ZeroDivisionError`), GREEN
  after the fix (artifact 003).
- Full suite after the fix: 3 passed (artifact 003 run).
- v2, after the reviewer-requested coverage addition: suite re-run, 4 passed
  (artifact 004); artifact 003's result is superseded for the changed test state.
- Not tested: negative divisors, float precision, non-numeric inputs — out of scope for
  this change and unexercised here.

### Risks
Callers that relied on `divide(x, 0) == None` as a sentinel will now see an exception.
No other module behavior changes; adjacent behavior (`add`, non-zero division) is
covered by the existing tests.

### Non-goals
No input validation for non-numeric types, no exception-hierarchy changes, no API
additions, no refactoring of neighboring functions.

### Related issue / discussion
Fixture drill; upstream equivalent would link the reproducing issue and any maintainer
thread here.
