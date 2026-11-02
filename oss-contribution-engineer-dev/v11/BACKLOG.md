# V11 Priority Backlog — from raw data, per PRE-REGISTRATION.md

Evidence = raw JSONL rows (`runs/`), raw investigation-state files
(`../v10/runs/*investigation*.json`), raw profile JSON
(`../v8/runs/profile-django.json`). No ledger conclusion paragraphs consulted.

## Raw findings that drove the ranking

**Aggregate file-level confusion matrix** (dedup rows; 10 tasks, 16 gold files):

| arm | TP | FP | FN | precision | recall |
|-----|----|----|----|-----------|--------|
| A2 grep | 7 | 33 | 9 | 0.175 | 0.438 |
| B symbol | 3 | 6 | 13 | 0.333 | 0.188 |
| C router | 8 | 72 | 8 | 0.100 | 0.500 |
| D full | 9 | 71 | 7 | 0.113 | 0.562 |

**H4 confirmed (raw rows, D arm):** non-Python tasks split 2/2 —
vite `file_recall=0.0`, clap `file_recall=0.0` (TOTAL miss) vs gin `1.0`,
cobra `1.0`. B-arm (python-ast) recall = 0.0 on ALL FOUR (symbol family empty
for TS/Go/Rust — `backend` field in every row shows no LSP). Python-task mean
recall ≈ 0.95. The two total misses are exactly the tasks whose identifiers
(`safeModulePaths`, zsh-escape) live in non-Python symbol space.

**H1 confirmed, but bounded (raw state `v10b-requests-investigation.json`):**
`candidate_root_causes` = `[src/requests/models.py::184-252 (gold, rank 1),
tests/test_requests.py::2083-2084 (test pollution), src/requests/structures.py
(adjacent prod)]`. Pollution CO-OCCURS with the correct rank-1 production hit;
file recall for the task = 1.0. Damage = investigation misdirection risk, not
missed gold.

**H2 confirmed as G3-only:** 0 budget-stops in all 60 rows; 0 rows where any
outcome is latency-attributable. Raw profile: pagerank 55% / corpus 7% of
181 s cold route (pre-F7 numbers; post-F7 route ≈ 35 s).

**H3 confirmed as zero-evidence:** no task repo has AOCI volumes (`backend`
field in every row); 0 AOCI-attributable failures.

## Ranked backlog (IG ÷ E)

### #1 — Wire Serena/LSP into `investigate` for non-Python repos (H4)
- **G1 impact:** 2/4 non-Python tasks deliver ZERO correct files → wrong
  investigation from the start. Largest measured correctness failure.
- **Evidence:** rows above; v9 serena harness already proved find_symbol +
  references work on gin (Go, 87 ms) and vite (TS, 4.0 s) with resolved spans.
- **The specific gap:** `repository_intelligence.select_backends` already
  prints `SERENA_LSP available` when configured — but `locate()` never CALLS
  it. LSP is advertised, not consumed.
- **E:** M (wire find_symbol per query identifier → merge into provenance;
  honest fallback unchanged).
- **Pre-registered improvement criterion (Phase 2):** on 2 never-run non-Python
  held-out tasks, session-`investigate` file recall vs baseline improves with
  consistent direction on BOTH tasks (n=2 sign test; raw numbers reported, no
  CI theater). Baseline measured on held-out BEFORE the fix.

### #2 — Deprioritize test-file hits in stage-2 `candidate_root_causes` (H1)
- **G1 impact:** bounded misdirection (correct prod hit co-present, rank 1).
- **E:** S. Deferred until #1 lands (single-improvement rule).

## Explicitly NOT doing (evidence-backed)

- **Django PageRank 46 s (H2):** G3-only; 0 attributable G1 failures in 60
  rows; 0 budget-stops. Optimizing it buys speed for correct results.
- **Official AOCI runtime validation (H3):** 0 attributable failures; requires
  installing external software the environment forbids; no task distribution
  exercises it. Revisit only when contributing to an AOCI-indexed repo.
- **Precision work on the 71 FP files:** noise is delivered under the equal
  inspection-span protocol; correct files are present. Cutting FP without
  recall regression is a separate experiment, not this goal.
