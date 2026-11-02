# Context Compaction Policy (research output 12)

Compaction is **state management with three decisions** (AutoCompact's framing):
when to compact, what to preserve, how to continue. Length-triggered compaction
mid-stage is the known failure mode; V3 compacts at stage boundaries by preference.

## When (triggers, in order of preference)

1. Stage completion (investigation → fix; review → PR prep) — natural boundary.
2. Soft-budget action list exhausted (11 § actions) and trajectory still growing.
3. Known loss event (explicit compaction notice from the harness).

Never mid-RED / mid-verification: finish the gate, record evidence, then compact.

## What to preserve (the working state)

goal · done_when · constraints · authority · decisions taken (with digests) ·
current evidence (manifest/receipt references) · unresolved questions · source
identities (path+digest) · SHA bindings · next action.

## What to discard preferentially

superseded hypotheses · duplicate tool output · low-value search results · verbose
command output already represented by evidence artifacts · exploration trails whose
conclusions are recorded.

(AutoCompact/AttnCompress: stale exploration is the compressible bulk; SWE-Pruner:
line-level granularity preserves syntax when trimming code.)

## How to continue (post-compaction protocol)

1. Load the **Task Cognition Receipt** (13) — it is written *before* compaction, never
   after memory fades.
2. Emit `RESULT RECONSTRUCTED ... NEXT ...` (04b) stating what was reloaded and what
   the next action is.
3. Re-verify anything that will be *edited* at L4 (source verification rule); digest
   mismatches (file changed since read) force a re-read.
4. Do not restate prior understanding from memory: model memory is not proof that
   repository cognition is available. Reload from persistent artifacts instead.

## Receipt-before-compaction loop

```
before compacting: cognition_receipt.py close  → receipt complete on disk
compaction happens
after compaction:  cognition_receipt.py reconstruct → RECONSTRUCTED block → continue
```

The receipt, the evidence manifest, the goal contract, and the Context Pack digest are
the four persistent anchors; everything else is rebuildable from them.
