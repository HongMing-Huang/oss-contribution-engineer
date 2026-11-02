# Goal Contract Specification (research output 4)

The Goal Compiler normalizes every non-trivial contribution task into a **Goal
Contract**: a structured, digest-stable artifact that separates *what the user wants*
from *what the agent currently guesses will satisfy it*. The contract is the anchor for
retrieval routing, budgets, receipts, and compaction.

## Principle

An implementation hypothesis is **not** the goal. The agent may hold many hypotheses;
exactly one contract exists per task, and it changes only when the user's intent
changes (with the change recorded). `done_when` items are observable acceptance
evidence wherever possible.

## Schema (v1)

```jsonc
{
  "contract_version": 1,
  "task_id": "<slug or receipt id>",
  "created": "<UTC ISO-8601>",
  "intent":    "<what the user wants, in their terms>",
  "outcome":   "<observable end state>",
  "why":       "<user's stated motivation or 'unstated'>",
  "done_when": [ // each: observable acceptance evidence
    {"criterion": "...", "observable": true, "how_observed": "run: <cmd> | test <name> | artifact <path> | maintainer reply | none"},
  ],
  "repository": "<url or slug>",
  "likely_domains": ["<L1 subsystem guesses>"],
  "scope":  "<files/areas believed in play — a guess, labeled as such>",
  "explicit_non_goals": ["..."],
  "constraints": ["..."],
  "repository_rules": ["<from recon; local rules override skill defaults>"],
  "authority": {"read": true, "worktree_edit": false, "remote_write": false},
  "unknowns": ["<facts not yet established>"],
  "stop_conditions": ["..."],  // incl. terminal successes: INVALID/ALREADY_FIXED/DUPLICATE/UNCONFIRMED/DESIGN_QUESTION
  "digest": "<sha256 of canonical JSON excluding digest field>"
}
```

Rules:
- `done_when`: ≥1 item; each item marked `observable: true|false` with `how_observed`
  set (`run:`/`test`/`artifact`/`maintainer reply`) or explicitly UNVERIFIABLE. An all-
  unobservable contract is flagged and the user is asked to sharpen it.
- `scope` entries are tagged `guess` — never treated as truth (anti-pattern: turning a
  guessed file list into the goal).
- `authority` mirrors V2's permission model; remote_write always starts false.
- The digest is over canonical (sorted-key, no-digest) JSON — receipts and packs cite
  the digest, not the prose.

## Goal Compiler contract with the agent

1. `scripts/goal_compiler.py compile ...` produces the contract + **Goal Card**.
2. The user's words fill `intent/outcome/why`; the agent fills `scope/likely_domains/
   unknowns` and MUST mark them as guesses.
3. Contracts persist under `.oss-contrib-evidence/goals/` and are immutable once
   compiled; revisions create a new digest and record what changed and why.
4. Hypotheses live in the task trajectory and Investigation Reports — never in the
   contract.

## Minimal contract gate

A task may proceed past DISCOVER only with a compiled contract; "investigate issue X"
with no other framing compiles to intent=investigate, authority={read}, done_when=one
observable Investigation Report conclusion. This is what makes "investigate ≠ edit"
mechanical rather than behavioral.
