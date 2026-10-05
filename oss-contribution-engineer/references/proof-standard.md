# Proof Standard (the Proof Gate)

A bug claim without an Evidence Record is a guess. This file defines the record and the
gate that turns investigation into either a confirmed bug or an honest stop.

## Evidence Record (required for every non-trivial bug claim)

| Field | Content |
|-------|---------|
| repository / branch / commit | exact upstream state tested (`git rev-parse HEAD`) |
| environment | OS, runtime/compiler versions, relevant flags |
| affected file/function | precise location |
| expected behavior | what should happen |
| source of expectation | doc/spec/maintainer statement/sibling behavior/test — link or quote location |
| actual behavior | what happens |
| minimal reproducer | smallest script/command/test that shows it |
| reproduction command + raw output | verbatim, recorded via evidence manifest |
| duplicate-search evidence | issues/PRs searched, what was found (from dedupe scan) |
| suspected root cause | hypothesis with code reading to back it |
| confidence limitations | what could make this wrong |

Store command outputs with `scripts/evidence_manifest.py` so outputs and exit codes are
witnessed, and reference the artifact paths in the record.

## The gate

- Reproducer runs and clearly shows expected vs actual → **CONFIRMED**, proceed (only if
  the user asked for a fix does the RED path begin).
- Cannot reproduce after honest attempts (different environment? version? unclear report?)
  → **UNCONFIRMED**. Say what evidence is missing. Do NOT write a patch to complete the
  workflow. If the source was an external issue, offer a minimal info request instead.
- Behavior is correct per docs/spec/tests → **INVALID** (record the source).
- Fixed in a newer commit on the same code path → **ALREADY_FIXED** (name the commit).
- Existing issue/PR covers it → **DUPLICATE** (link it).
- Behavior defensible but questionable → **DESIGN_QUESTION** for maintainers.

## Investigation Report (assets/investigation-report.md)

For Investigation-Only mode and before any fix: hypothesis, source paths, architecture
trace, expected (with source) vs observed, reproducer, root cause, duplicate search,
conclusion (one of the six above), and the evidence artifact list.

## Reproducer discipline

- Prefer adding it as a test file eventually, but during PROVE a standalone script/command
  is fine; keep it minimal — reduce until only the defect remains.
- Reproduce on **current upstream** (fetch/pull or fresh clone), not a stale checkout.
  LLVM's rule: verify against current trunk before reporting.
- If the failure needs specific conditions (OS, provider, timing), say so and test at
  least one cheaper approximation; state exactly which conditions were and weren't
  covered.
- Flaky reproducer? Run it enough times to distinguish flake from determinism, and
  record how many runs. A nondeterministic repro must say so.
