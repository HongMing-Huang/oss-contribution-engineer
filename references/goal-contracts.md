# Goal Contracts & Communication Protocol

Research basis: v3/research/04 (spec), 04b (protocol), 03 §9 (ARB), 03 §2 (SWE-agent
interface lesson). The Goal Compiler separates **what the user wants** from **what the
agent guesses will satisfy it**; an implementation hypothesis is never the goal.

## When

Compile a contract for every non-trivial task, right after the request is understood
and before any repository work beyond recon:

```bash
python3 <skill-dir>/scripts/goal_compiler.py . compile \
  --intent "fix fd --exclude ignoring non-first search paths" \
  --outcome "exclude patterns apply under every search path, per maintainer decision" \
  --done-when "run: python3 -m pytest tests/ -q" \
  --done-when "maintainer reply accepts the approach" \
  --repository sharkdp/fd --domains "walk,overrides" \
  --scope src/walk.rs --unknowns "which design option maintainers prefer" \
  --constraints "no design decisions without maintainer input" \
  --authority read
```

"Investigate issue X" with no other framing compiles to `intent=investigate`,
`authority={read}`, done_when = one observable Investigation Report conclusion —
this is what makes **investigate ≠ edit** mechanical.

## Contract rules

- `scope` / `likely_domains` / `unknowns` are recorded as **guesses** (`status: guess`);
  user intent fields are not.
- `done_when`: ≥1 item; observable items carry `how_observed` (`run:` / `test` /
  `artifact` / `maintainer reply`). A contract with zero observable items is rejected —
  sharpen it with the user instead of proceeding blind (`--allow-unobservable` exists
  for genuinely observational tasks, and the flag is visible in the contract).
- `authority.remote_write` is always false at compile time; it is granted per action
  later, never inferred (V2 permission model unchanged).
- Contracts are immutable: revision = new digest + a note of what changed and why.
  Hypotheses go to `goal_compiler.py . hypotheses --hypothesis "..." --status proposed`
  — free to propose, falsify, supersede without touching the contract.

## Communication protocol (compact blocks, no status prose)

**Task start — Goal Card** (emitted by the compiler):

```
GOAL  <intent>
DONE  <done_when with observability tags>
SCOPE <domains + guesses>
UNKNOWN <top unknowns>
NEXT  <first action>
AUTH  read=… worktree_edit=… remote_write=…
```

**During investigation — per finding:**

```
FOUND   <finding>
EVIDENCE <manifest id / artifact path / command>
IMPACT  <plan change, or 'none'>
NEXT    <action>
```

**Before production edits — PATCH INTENT** (block form of the V2 PATCH PLAN; the
Implementation Plan asset remains the full artifact):

```
PATCH INTENT
  invariant violated / expected changed files / expected behavior change /
  regression evidence (RED artifact) / non-goals
```

**Closure:**

```
RESULT        CONFIRMED|UNCONFIRMED|INVALID|ALREADY_FIXED|DUPLICATE|
              DESIGN_QUESTION|PATCHED (PR_READY)|NO_PATCH (reason)
EVIDENCE      <artifact refs / receipt id>
CHANGED       <files | none>
NOT VERIFIED  <SKIPPED/UNAVAILABLE levels + unchecked areas>
REMAINING RISK <...>
```

Every EVIDENCE line references something observable. After context compaction, the
first message is a RECONSTRUCTED block built from the Task Cognition Receipt — never a
recitation of remembered state (see context-packing.md).
