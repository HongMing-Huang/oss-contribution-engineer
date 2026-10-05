# Retrieval Evaluation

Research basis: v3/research/14. Two layers, deliberately separated: retrieval/context
quality (this file) and patch discipline (the V2 eval suite). Do not optimize
exclusively for SWE-bench patch resolution.

## Running the retrieval eval

```bash
python3 <skill-dir>/scripts/retrieval_eval.py <repo> --tasks tasks.jsonl \
  --top-k 5,10,20 --budget-tokens 8000              # full hybrid
python3 <skill-dir>/scripts/retrieval_eval.py <repo> --tasks tasks.jsonl \
  --signals lexical,path                            # ablation arm
```

Task set format (JSONL): `id`, `task_type`, `query`, `anchor_files`, `given_files`,
`gold_files`, optional `gold_regions` (`{path, lines: "a-b"}`). Gold must be verified
against the repository at the tested commit (base-commit hygiene; no leakage) — the
bundled seed tasks cite their verification (grep line numbers, reproduced issues).

## Metrics

Recall@K · MRR · gold file coverage · **BCY@B** (budgeted context yield: gold exposed
after token-budgeted packing; oversized single files are skipped, learned from
measurement) · region coverage · useful/delivered line ratio · delivered-token cost ·
per-task-type breakdown. Ablation arms: lexical-only · symbol+test-only · hybrid
(embedding arm exists only when an external backend is configured).

## Recorded results (2026-10-05, real runs; click + fd clones)

Five-arm ablation (2026-10-05, real runs; arms = `--signals` subsets; embedding arm is
**UNAVAILABLE by design** — no model dependency — and is documented as such, not silently
dropped; per-task-type detail in `oss-contribution-engineer-dev/v3/eval/results/`):

| Repo | Arm | MRR | Recall@5 | BCY@8k |
|---|---|---|---|---|
| click | lexical only | **0.625** | **0.875** | **0.875** |
| click | RepoMap only | 0.252 | 0.750 | 0.250 |
| click | symbol+test only | 0.250 | 0.250 | 0.250 |
| click | hybrid | 0.411 | 0.625 | 0.625 |
| fd | lexical only | 0.390 | 0.625 | **0.250** |
| fd | RepoMap only | 0.400 | 0.625 | 0.000 |
| fd | symbol+test only | 0.333 | 0.625 | 0.000 |
| fd | hybrid | **0.438** | 0.625 | 0.000 |

RepoMap arm: PageRank (power iteration, stdlib) over the file graph (importer→imported,
production→tests) with query personalization as the analog of Aider's chat-file
multiplier. Findings:

1. **No arm wins everywhere** — lexical wins click outright; hybrid wins fd MRR; the
   RepoMap arm surfaces structurally central files (fd's `tests/testenv/mod.rs` import
   hub ranked #1) but hub centrality can crowd out query-specific gold — the reason the
   hybrid keeps it as a weighted prior, never an authority (ARB reproduced).
2. **RepoMap hub risk is measurable**: adding the repomap signal to the fd hybrid
   regressed BCY@8k to 0.000 — hub files (testenv/mod.rs) pack before gold in rank
   order under greedy first-fit packing. Recorded as a routing-policy lesson
   (trace2code-style tasks need a hub penalty), not tuned away post-hoc.
3. Per-task-type (hybrid, unchanged where noted): code2test Recall@5 = 1.0 on both
   repos; **comment2context (click) = 0.0** (docs dominate lexical for that query);
   fd issue2code = 0.0 (CHANGELOG.md dominates lexical) — recorded failures.
4. **More context made things worse**: rank_depth=20 whole-file delivery averages
   ~100k estimated tokens per task vs a 12k source soft-budget — span-level Context
   Packs deliver the same evidence at 80–640 tokens. Whole-file delivery is an
   anti-pattern the metrics expose.
5. Defects found and fixed *because* of the metrics/E2E: whole-file budget charging
   (span charging now), oversized-file starvation in BCY (skip rule), head-only span
   scan in the packer (full-file symbol scan + name-preference now), separator-order
   tokenization that made "usage-line" unmatchable against "write_usage".

## End-to-end link

Run the V2 contribution scenarios with and without V3 context acquisition and compare
root-cause accuracy, regression-test quality, patch scope, patch correctness,
validation success, review quality — recording cases where more context makes results
worse. Component metrics never claim patch causality (ARB's scope discipline).
