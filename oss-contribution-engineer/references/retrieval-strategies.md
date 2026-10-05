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

## V4: workflow-aware routing + no-regret packing (2026-10-05)

The router no longer merges everything unconditionally. `ROUTING_POLICIES` decides per
workflow: which families run, their RRF weights, and how structural-only candidates
are treated (`structural_max_share`, `structural_first`). Every candidate now carries
`evidence_class` (direct | structural) and structured per-arm `evidence`
(`{family, rank, match: exact|partial}` for symbols, `{relation, distance}` for graph,
`{centrality}` for repomap) with an explainable `reason` — "exact symbol match +
history hit", never a bare hybrid score.

**No-regret guard (constructive)**: unless the policy declares `structural_first`
(only `explore` does), direct-evidence candidates always outrank structural-only ones
and structural candidates fill only remaining slots up to a per-workflow share cap.
A RepoMap hub can therefore never displace a direct hit *by construction* — the fd
hub regression measured in V3 is now structurally impossible, not tuned away. The
PACK phase continues the guard: direct candidates pack first; structural-only
candidates pack within the quota; any direct candidate that still loses its slot
under budget pressure is reported in `pack.no_regret.displaced_direct`.

**Routing priors are hypotheses, validated by ROUTING REGRET** (retrieval_eval
`--arms router,...`): regret = best tested arm BCY − policy-routed BCY, per sample.
First measurements: on click seeds regret mean 0.25 — one sample (comment2context)
where lexical-only reached BCY 1.0 and the policy 0.0, pinpointing a bad prior; on
the ARB frozen slice all arms scored BCY 0 (see below), where regret degenerates to
0 and *absolute* scores must be reported alongside — regret is only informative when
some arm succeeds.

**Measured honestly (ARB v0_1 frozen 6-task slice, SHA-verified base-commit clones,
Python/Rust/Go/TS; edit2ripple absent from v0_1 — recorded, not simulated):** router
MRR 0.183 (best of the four arms), Recall@10 0.333, but **BCY = 0 at 4k/8k/16k for
every arm** and ~50 s/query latency. Gold files were verified present in the scanned
corpus — the failure is real: at monorepo scale with PR-shaped queries, whole-file
packing under any budget never reaches gold-ranked-deep files, and per-run corpus
scans are too slow. Conclusions recorded, not tuned away: (1) file-level retrieval +
whole-file BCY is the wrong packing unit at scale — span-level packs (Context Pack)
and persistent cognition (backend layer) are the intended mitigations; (2) click/fd
seed results do not transfer to monorepos — routing priors need scale-aware
validation; (3) latency demands a persistent index, not per-run scans. These are
recorded as open work items, with no hybrid-superiority claim: on the ARB slice the
router was merely *least bad* (MRR 0.183 vs 0.018–0.167), and every arm failed the
packing metric.
