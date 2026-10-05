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

| Repo | Arm | MRR | Recall@5 | BCY@8k |
|---|---|---|---|---|
| click | hybrid | 0.300 | 0.625 | 0.375 |
| click | lexical+path | **0.590** | 0.625 | 0.375 |
| click | symbol+test | 0.250 | 0.250 | 0.250 |
| fd | hybrid | **0.458** | 0.625 | 0.250 |
| fd | lexical+path | 0.265 | 0.625 | 0.250 |

Per-task-type (hybrid): code2test Recall@5 = 1.0 on both repos; trace2code (fd)
Recall@5 = 1.0, BCY@8k = 1.0; **comment2context (click) = 0.0 — recorded routing
failure** (docs dominate the lexical signal for that query); fd issue2code = 0.0
(CHANGELOG.md dominates lexical).

Findings, honestly stated:
1. **No arm wins everywhere** — hybrid wins fd MRR and code2test everywhere; lexical
   wins click MRR. The goal is a routing-policy record, not a champion (ARB's result
   reproduced on our small sets).
2. **More context made things worse**: rank_depth=20 whole-file delivery averages
   ~100k estimated tokens per task vs a 12k source soft-budget — span-level Context
   Packs deliver the same evidence at 280–3k tokens. Whole-file delivery is an
   anti-pattern the metrics expose.
3. Two packing defects were found and fixed *because* of the metrics: whole-file
   budget charging (span charging now), and oversized-file starvation in BCY (skip
   rule now). A third failure (CHANGELOG dominance) is recorded, not tuned away.

## End-to-end link

Run the V2 contribution scenarios with and without V3 context acquisition and compare
root-cause accuracy, regression-test quality, patch scope, patch correctness,
validation success, review quality — recording cases where more context makes results
worse. Component metrics never claim patch causality (ARB's scope discipline).
