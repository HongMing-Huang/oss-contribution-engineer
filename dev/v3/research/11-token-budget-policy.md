# Token Budget Policy (research output 11)

Budgets exist to force *selection*, not to starve the task. Objective: minimum
sufficient, verifiable context for the current engineering decision.

## Categories tracked

`cognition` (backend views, packs) · `source` (L4 reads) · `test` · `history` ·
`spec` (external contracts/docs) · `trajectory` (the running conversation itself).

## Defaults (configurable via `.oss-contrib/context-budget.json`)

| Category | Soft | Hard |
|---|---|---|
| cognition | 4k | 8k |
| source | 12k | 30k |
| test | 4k | 10k |
| history | 2k | 6k |
| spec | 2k | 6k |
| trajectory | — | session/agent-defined |

Soft = act-before-crossing; hard = do-not-cross without a recorded user-approved reason.
Task priors may shift allocation between categories (e.g., trace2code shifts history
soft → 4k) but never the protections below.

## On reaching soft budget — ordered actions (never "keep reading")

1. **Rerank** remaining candidates; drop what no signal supports.
2. **Prune** delivered content to spans (line ranges) rather than files (SWE-Explore
   line-level finding; SWE-Pruner granularity lesson).
3. **Externalize** stable facts into the receipt (13) — then they are reloadable, and
   trajectory copies become droppable.
4. **Summarize with provenance** (summary + artifact ref); unproven semantic summaries
   are banned.
5. **Drop superseded observations** (duplicate tool output, earlier hypotheses now
   falsified, verbose command output already represented by evidence artifacts).
6. **Request targeted expansion** only for the specific missing evidence (named, not
   "more context").

## Protected items — never dropped to save tokens

- current goal + done_when + stop conditions
- authority/constraints and safety rules
- unresolved blockers
- source identities (path + digest of what was actually read)

## Honesty requirements

- The governor reports numbers as estimates (chars/4 heuristic) — an estimate, labeled.
- Crossing hard budget requires a user-visible note with the reason; silent truncation
  of delivered context is an anti-pattern.
- The governor never edits the goal contract to fit the budget.
