# Change Walkthrough — <change / PR title>

> Product of CONTRIBUTOR_UNDERSTANDING. Audience: the human contributor — the person who
> will sign off, answer review, and carry the change. It explains the engineering
> reasoning, not every changed line. Every claim must reference real current source
> (file:line) and the actual tests by name; a summary never replaces re-reading the
> source. Refresh this document whenever the patch changes (review fixes, rebases) —
> a stale walkthrough is worse than none.

## Problem
<!-- what was broken, user-visible: one or two sentences, no marketing -->

## Before
<!-- how the affected code behaved before the fix; cite file:line as it was, and the
     observable wrong behavior (or link the reproducer output) -->

## Root cause
<!-- the code-level cause; the commit that introduced it if known (Fixes: tag material) -->

## Relevant data / state
<!-- the data or state that flows through the bug: inputs, invariants, error paths —
     enough to understand why this location is the problem's home -->

## Changed code
<!-- the diff, briefly, with file:line; what each hunk does for the fix (one line each) -->

## Why this fix
<!-- why this location and this approach are correct; the alternative(s) considered and
     why they were rejected; why the change is minimal -->

## After
<!-- the new observable behavior, traced through the same data flow as "Before" -->

## Regression proof
<!-- the named test; its RED run on unmodified upstream (manifest artifact ref) and its
     GREEN run after the fix; why the test would fail again if the bug returned -->

## Risk
<!-- what may still regress: adjacent behavior, environments not covered, assumptions
     the fix depends on; carried into the PR description -->

## Non-goals
<!-- what was deliberately not changed, and why leaving it alone is correct -->

## Understanding status (recorded, never claimed by the agent)
<!-- UNDERSTOOD (explicit human confirmation) / DEFERRED / INCOMPLETE — with the gaps
     named and the code path shown for them; date + how confirmed -->
