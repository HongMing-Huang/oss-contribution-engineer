# Evaluation Design (research output 14)

Two evaluation layers, deliberately separated: **retrieval/context quality** (new) and
**patch discipline** (V2's existing eval suite). Do not optimize exclusively for
SWE-bench patch resolution (ARB/SWE-Explore both show intermediate metrics carry
different information).

## Layer A — Retrieval evaluation (new; `scripts/retrieval_eval.py`)

### Task sets

JSONL tasks per repository, one task = `{id, task_type, query, anchor_files[],
given_files[], gold_files[], gold_regions?[]}`. Seeded initially from real,
already-investigated cases (click/fd/fixture work from V2 runs), extendable via
AR B-style workflow signals (PR→tests, review comment→context, trace→code,
anchored edit→ripple). Every task freezes gold at a base commit (anti-leakage,
ARB rule).

### Task types evaluated separately

code2test · comment2context · trace2code · edit2ripple (issue2code/explore/review/
bug_hunt reported too, without pretending benchmark-grade gold).

### Methods compared (ablation matrix)

lexical only · RepoMap-style structural only · embedding only (external, optional —
runs only if a backend is configured) · symbol/structural only · hybrid (full router).
Expected result: **no universal winner** — the goal is a routing-policy record, not a
champion.

### Metrics

| Metric | Definition |
|---|---|
| Recall@K (K=5,10,20) | gold files in top-K |
| MRR | 1/rank of first gold file |
| gold file coverage | fraction of gold files retrieved at budget |
| gold region coverage | line-region overlap (when gold_regions present) |
| context precision | delivered relevant / delivered total |
| context recall | delivered relevant / gold relevant |
| useful lines / delivered lines | precision at line granularity (SWE-Explore) |
| gold coverage under budget | **BCY@B** — gold exposed after token-budgeted packing (B=4k/8k/16k) |
| retrieval token cost | estimated tokens delivered + query overhead |
| exploration steps | router runs + expansions per task |
| missed dependency count | gold files absent from final pack |
| abstention quality | natural no-gold tasks: does the router's abstention report lead the agent to return NO_RELEVANT_LOCAL_CONTEXT (factors reported; **no claimed calibration** — ARB negative result) |

### Reporting rules

- Per-task-type breakdown mandatory (aggregate tables hide routing failures).
- Score tables state estimate-based token counts.
- Results never claim end-to-end patch causality (ARB's scope discipline).

## Layer B — End-to-end evaluation (existing V2 machinery, extended)

After retrieval eval, run the standard contribution scenarios (V2 eval suite) with and
without V3 context acquisition on a large-ish repository and compare: root-cause
accuracy, regression-test quality, patch scope, patch correctness, validation success,
maintainer-quality review. **Record cases where more context makes results worse**
(mandated; SWE-Explore noise-robustness suggests they will be rare but real: usually
when verbose context displaces protected items like done_when).

## Machinery reuse

ARB: task construction patterns, BCY@B definition, selective protocol (with its
honest negative result). SWE-Explore: line-region GT shape, context-efficiency and
first-useful-hit metrics. Neither's datasets are bundled; their *definitions* are.
