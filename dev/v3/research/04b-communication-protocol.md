# Agent Communication Protocol (research output 4b, binds output 4)

Compact, machine-checkable status blocks replace prose status. Motivated by the
SWE-agent finding that interface design moves outcomes: the protocol is an interface.

## Task start — Goal Card

```
GOAL  <one line: intent>
DONE  <done_when items, short>
SCOPE <likely_domains/scope guesses, marked as guesses>
UNKNOWN <top unknowns>
NEXT  <first action>
```

No long paraphrase of the user's request. Unknowns are required, not optional.

## During investigation — FOUND block (replaces generic status prose)

```
FOUND   <one finding>
EVIDENCE <command/obs/artifact reference (manifest id where recorded)>
IMPACT  <what this changes in the plan, or 'none'>
NEXT    <action>
```

Multiple findings → multiple blocks. Nothing else is required between tool calls.

## Before production edits — PATCH INTENT

Mirrors the V2 PATCH PLAN as a communication block (the Implementation Plan asset
remains the full artifact):

```
PATCH INTENT
  invariant violated: <...>
  expected changed files: <...>
  expected behavior change: <...>
  regression evidence: RED <manifest id/artifact>
  non-goals: <...>
```

BLOCKED if RED evidence is absent (gate unchanged from V2).

## Closure — RESULT block

```
RESULT        <CONFIRMED | UNCONFIRMED | INVALID | ALREADY_FIXED | DUPLICATE |
               DESIGN_QUESTION | PATCHED (PR_READY) | NO_PATCH (reason)>
EVIDENCE      <manifest artifacts / receipt id>
CHANGED       <files, or 'none'>
NOT VERIFIED  <levels SKIPPED/UNAVAILABLE + what could not be checked>
REMAINING RISK <...>
```

## Rules

- Blocks are emitted at real transitions, not on a timer.
- Every EVIDENCE line references something observable (command, artifact path,
  manifest id, receipt id) — the V2 "never fabricate execution" rule applies verbatim.
- After context compaction, the FIRST message must be a reconstruction block reusing
  the Task Cognition Receipt (see 13): `RESULT RECONSTRUCTED ... NEXT ...` — the agent
  reloads from persistent artifacts instead of reciting remembered state.
