# Retrieval Strategies (Router, Fusion, Abstention)

Research basis: v3/research/05/07/08/09. The router combines independent signal
families, routes by task type, and may return nothing. Deterministic, stdlib-only,
offline; Language Server / SCIP / embeddings are optional pluggable signals, never
authoritative.

## Usage

```bash
python3 <skill-dir>/scripts/retrieval_router.py <repo> "<query>" \
  --task-type trace2code --top-k 8 --json
python3 <skill-dir>/scripts/retrieval_eval.py <repo> --tasks tasks.jsonl   # ablation + metrics
```

## Signal families & task priors

| Task type | Boosted families |
|---|---|
| code2test | test-relations, symbol, lexical |
| comment2context | symbol, path, lexical (given files excluded from "new context") |
| trace2code | lexical (frames), history, symbol |
| edit2ripple | graph expansion, test-relations, symbol |
| issue2code | lexical, symbol, cognition |
| review | graph, history, symbol |
| bug_hunt | history, lexical, test |
| explore | cognition, path, graph |

Fusion is RRF (k=60) with these priors as weights; graph expansion adds
`score × 0.5^depth` through a priority queue with depth ≤2, node budget ≤50, score
floor — never BFS (LocAgent distance-decay and OrcaLoca prune-before-LLM lessons).

## Honest ranking

- Output carries per-signal ranks and one-line reasons — "signals observed", not
  confidence. No probabilities, no match percentages.
- Anchor/given files are labeled `given` and excluded where the task type says so
  (comment2context: the reviewed file is not gold).

## Abstention — NO_RELEVANT_LOCAL_CONTEXT

A retrieval system must be allowed to return no files. The router emits an abstention
*report* (per-family top scores, identifier matches, cognition-domain coverage) whenever
all families come back weak. The agent decides with the factors — **not** from a
threshold: Agent Retrieval Bench's selective-retrieval result shows top-score thresholds
calibrated even across corpora do not transfer to natural no-gold cases (lexical
selective success 0.499 → 0.294 once counterfactual controls are removed). Calibration
remains an open problem; treating scores as probabilities would be dishonest.

## Measured behavior (2026-10-05, real runs — see v3/validation-results.md)

- click: hybrid code2test Recall@5 = 1.0 vs lexical-only 0.625; lexical-only MRR 0.59
  vs hybrid 0.30 → **no universal winner; routing per task type is the point** (ARB).
- fd: hybrid MRR 0.458 vs lexical-only 0.265; trace2code BCY@8k 1.0 after the
  oversized-file packing fix; fd issue2code still fails (CHANGELOG.md dominates
  lexical) — a recorded routing defect, not hidden.
- BCY@8k initially starved gold files behind a >8k-token CHANGELOG; the packing rule
  "skip a file that cannot fit even alone" was added after measurement, not before.
