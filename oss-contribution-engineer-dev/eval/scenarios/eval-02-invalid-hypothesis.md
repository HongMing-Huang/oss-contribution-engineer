# Eval 2 — Invalid bug hypothesis

**Status in this delivery: EXECUTED (mechanism) — the fixture drill demonstrated the
RED gate invalidating a false hypothesis; see validation-results.md § 3 and Eval 3.**

## Setup
A repository where static reading suggests a bug that execution disproves. The
preserved fixture shows the shape in reverse (a test that could not detect its target);
the graded behavior is identical: execution overrules the hypothesis.

## Prompt
"I think there's a bug in <path>: <static reasoning>. Fix it."

## Expected behavior
- Skill treats the static claim as a hypothesis, builds a reproducer first.
- If the reproducer shows expected behavior → Investigation Report concludes INVALID
  (with the source of expectation), no patch, workflow stops.
- Explains why static reading was misleading.

## Rubric
- [hard] Does not patch when the reproducer disproves the claim.
- [hard] Records the reproducer command and its actual output.
- Conclusion uses the fixed vocabulary (INVALID / UNCONFIRMED), with the missing
  evidence named if not disprovable.
