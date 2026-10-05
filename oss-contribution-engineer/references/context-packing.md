# Context Packing, Budgets, Compaction & Receipts

Research basis: v3/research/10/11/12/13. Objective: **minimum sufficient, verifiable
context for the current engineering decision** — not maximum context.

## Context Planner & Context Pack

```bash
python3 <skill-dir>/scripts/context_planner.py <repo> plan --goal <goal.json> --retrieval <router.json> --top-r1 5
python3 <skill-dir>/scripts/context_planner.py <repo> pack --goal <goal.json> --plan <plan.json>
```

The plan (pre-load) names the primary subsystem, radius tiers with reasons, token
allocation, and visible exclusions. The pack delivers **source ranges** (symbol spans,
not whole files), each with: path, symbol, line span, digest at read time, and why.
Packing rule learned from measurement: a file that cannot fit even alone is skipped by
the packer, and span delivery is charged by span size — whole-file charging starved the
gold file behind a 10k-token neighbor. The pack is bounded, digest-stamped, and stored
beside the receipt.

## Token Budget Governor

```bash
python3 <skill-dir>/scripts/budget_governor.py <pack.json> [--config .oss-contrib/context-budget.json]
```

Categories: cognition / source / test / history / spec / trajectory; defaults soft
4k/12k/4k/2k/2k, hard 8k/30k/10k/6k/6k (configurable). At soft budget, do NOT keep
reading — ordered actions: rerank → prune to spans → externalize stable facts into the
receipt → summarize with provenance → drop superseded observations → request targeted
expansion for the *named* missing evidence. **Never** drop: goal/done_when/stop
conditions, authority+safety constraints, unresolved blockers, source identities.
Crossing a hard budget requires a user-visible reason; silent truncation is banned.
Token counts are estimates (chars/4) and labeled as estimates.

## Context compaction = state management (three decisions: when / what / how)

- **When**: at stage boundaries (investigation→fix; review→PR prep), never mid-RED.
- **What**: before compacting, close the receipt — then preserve (goal, done_when,
  constraints, authority, decisions, evidence refs, unresolved, source identities, SHA
  bindings, next action) and preferentially discard (superseded hypotheses, duplicate
  tool output, low-value search results, verbose output already represented by
  evidence artifacts).
- **How**: reload from persistent artifacts, never from memory:

```bash
python3 <skill-dir>/scripts/cognition_receipt.py <repo> reconstruct --task-id <id>
```

and open the reply with `RESULT RECONSTRUCTED ... NEXT ...`.

## Task Cognition Receipt

```bash
python3 <skill-dir>/scripts/cognition_receipt.py <repo> open --task-id <id> --goal-digest <digest> [--backend AOCI_NATIVE]
python3 <skill-id>/scripts/cognition_receipt.py <repo> record-read --task-id <id> --ranges "325-350" --why "..." src/walk.rs
python3 <skill-dir>/scripts/cognition_receipt.py <repo> verify   --task-id <id>   # re-hash: CURRENT/CHANGED/DELETED
python3 <skill-dir>/scripts/cognition_receipt.py <repo> close    --task-id <id> --unresolved ... --next-action ...
```

The receipt binds: repository identity, base SHA, goal digest, backend + alignment,
subsystems understood, sources/tests read (digests, ranges, whys), history evidence,
external contracts, decisions, unresolved questions, pack digest, next action. `verify`
fires drift detection: a CHANGED file invalidates cached claims about it — re-read
before any edit or claim (this is how "mixing obsolete source with current source" is
mechanically prevented).

Receipts are model-memory insurance: after compaction, the receipt + evidence manifest
+ goal contract + pack digest are the four anchors from which everything else rebuilds.
