# V9 Experiment Ledger — Blind Real-Repository Iteration

Status: **EXPERIMENTAL** (unchanged; see README maturity ladder). This ledger is
append-only and extends `../v8/EXPERIMENT-LEDGER.md`. V9's purpose was fixing
the experimental-validity problems V8 exposed, not adding mechanisms.

## What changed for validity

1. **§1 Blind task sources.** All 10 task prompts are captured VERBATIM from
   pre-fix material (4 issue level incl. one Trac ticket via SSRF-bounded
   fetch; 6 PR-title level where no issue exists) with source_url, timestamp,
   raw text, sha256 capture digest, fix + base commits
   (`v9_freeze_tasks.py` → `v9_tasks.json`). A freeze leak-check proves every
   query token occurs in the captured source (10/10 leak-free). The manually
   authored V8 summaries are RETIRED — they contained diff knowledge (e.g. the
   old click-3865 summary named the mechanism 'vs.'/'e.g.' from the fixing
   diff). Consequence, honestly measured: blind text is weaker evidence and
   recalls dropped vs V8's leaky numbers (arm D file recall 0.704 leaky →
   0.767 blind is NOT comparable; task text changed entirely).
2. **§3 One snapshot per task.** The symbol graph, spans index, and warm corpus
   are built ONCE per task and reused by router AND localizer
   (localize(stage1_result=…) skips its internal re-route; localize no longer
   rebuilds the graph). Stage percentiles below. Repeated parsing between
   router and localizer is eliminated (two_stage stage p50 = 2 ms vs the whole
   second Corpus+route it used to do).
3. **§5 Stopping semantics.** `SUFFICIENT_EVIDENCE` is GONE. Exits are
   `STOPPED_EVIDENCE_FOUND / STOPPED_BUDGET / STOPPED_NO_EVIDENCE`, each with a
   structured `stop_evidence` record (question, direct evidence, relations
   covered, unresolved list, why-stop). Comparison on the same blind tasks:
   C (router only) vs D (router + iterative expansion): file recall 0.667 vs
   0.767, but span precision 0.007 vs 0.005 and span recall 0.190 vs 0.138 —
   **iterative expansion adds noise, not value, under equal units. Per the
   pre-committed rule ("simplify or remove"), the neighbor-hop expansion is
   REMOVED from the default path** (`expand=False`; D1 arm reproduced D
   task-for-task identically — the hop contributed zero exact matches, only
   visited nodes). The old behavior stays behind `expand=True` for
   reproducibility. Negative result preserved.
4. **§6 Equal units.** Every arm delivers line/span context through one
   inspection-span protocol (matching lines ±5 merged, cap 60 lines/file,
   shared 400-line budget, same chars/4 estimator). No whole-file vs span
   comparisons remain (arm C's cost column is now spans, not whole files).
5. **§7 Competent baseline.** A2 = exact identifier search → inspect nearby
   source → import/name-linked tests → one bounded follow-up. On blind text it
   beats the V8 grep arm massively (file recall 0.567 vs 0.185) and beats the
   symbol-only arm — it is no longer a strawman.

## V9 r1 results (10 tasks: 8 V8 set re-sourced blind + 2 new blind)

Data: `runs/v9-r1.jsonl` (50 rows incl. the D1 simplification arm). Summary
table with p50/p95/max auto-merged below by `v9_report.py`.

Key readings (means over blind tasks):
- file recall: **D 0.767 > C 0.667 > A2 0.567 > B 0.300** — the full pipeline
  still wins on blind evidence, and the strengthened grep baseline closed much
  of the gap the V8 numbers suggested.
- span precision is low for EVERY arm under equal units (0.005–0.009): the
  inspection-span protocol floods in context lines by design; this metric now
  measures delivery noise uniformly, not arm quality.
- B (symbol-only) collapses on blind text (0.300): blind issues rarely name
  exact symbols — the V8 symbol numbers were inflated by leaky text.

## §4 Real multi-language semantic backend (serena-agent, venv in workdir)

- **Go (gin @d8f2d588d7, gopls in ./lsp-bin):** startup 3.6 s; find_symbol
  `getValue` → tree.go Method, 87 ms; find_referencing_symbols → RESOLVED
  cross-file reference gin.go handleHTTPRequest L743 with context line, 3.2 s;
  get_symbols_overview 115 ms.
- **TypeScript (vite @ba8b7ab43b, typescript-language-server in ./lsp-npm):
  startup 4.8 s; find_symbol `importAnalysisPlugin` → definition, 4.0 s;
  find_referencing_symbols → resolved reference into plugins/index.ts, 9.5 s;
  overview 109 ms.
- Fallback behavior recorded when a language server is missing (gopls absent →
  tool errors named the missing server; install into the workdir fixed it —
  nothing machine-wide). Rows: `runs/serena-runs.jsonl`.
- Capability statement: cross-language REFERENCES/definitions now come from a
  real LSP on these two repos; lexical routing alone is not claimed to provide
  them.

## §2 End-to-end intelligence → contribution path

`runs/contribution-path-v9.jsonl`: click-3805, blind PR-title source →
snapshot → route → localize (STOPPED_EVIDENCE_FOUND) → context plan + pack →
source verification → investigation pool (5 pipeline-surfaced files) → target
anchored by repro evidence **inside the pool** (`src/click/_utils.py::Sentinel`,
surfaced by the pack's source_ranges — the driver never names a path) →
witnessed repro → digest-bound RED → PATCH → head-bound GREEN → upstream
subset → UNDERSTOOD (human) → scope audit → **PR_READY**. Localization notes:
stage-2 exact-matching hit same-named TEST functions (`copy`) — a real blind-
text weakness recorded as negative evidence; the pack (not the driver) is what
surfaced the production file.

## Negative results preserved

- Iterative graph expansion removed from the default localization path (§5
  above): zero exact-match benefit on all 10 blind tasks, noise cost only.
- Two-stage function matching on blind text hits same-named test helpers
  (click-3805 `copy`); identifier-exact matching over weak text is unreliable.
- PR_TITLE-level sources (6/10 tasks) carry fix-author framing — weaker blind
  material than issues; per-task `source_level` is recorded so future rounds
  can weight accordingly.
- django Trac plain-text endpoint returned HTTP 500; the django task degraded
  to PR_TITLE with the fallback reason recorded in the freeze artifact.

## Maturity

EXPERIMENTAL, unchanged. V9 made the experiment more trustworthy; it did not
make the project useful.

## V9 round summary (blind tasks, equal span units, snapshot reuse)

| arm | n | file_recall | span_recall | span_prec | tok p50 | lat p50 | lat p95 | lat max |
|---|---|---|---|---|---|---|---|---|
| A2 | 10 | 0.567 | 0.138 | 0.007 | 1259 | 44 | 6480 | 6480 |
| B | 10 | 0.3 | 0.25 | 0.009 | 0 | 1529 | 81913 | 81913 |
| C | 10 | 0.667 | 0.19 | 0.007 | 2415 | 1730 | 114526 | 114526 |
| D | 10 | 0.767 | 0.138 | 0.005 | 1342 | 1877 | 142202 | 142202 |
| D1 | 10 | 0.767 | 0.138 | 0.005 | 1342 | 1093 | 113771 | 113771 |

### D stage latencies (ms, p50/p95/max)

| stage | p50 | p95 | max |
|---|---|---|---|
| graph_build | 56 | 17020 | 17020 |
| route | 527 | 52898 | 52898 |
| scan_tokenize | 135 | 2177 | 2177 |
| symbol_index | 302 | 11257 | 11257 |
| total | 606 | 55874 | 55874 |
| two_stage | 2 | 2976 | 2976 |

## V9 round 2 (D re-run with context_plan/context_pack timed — §3 seven-stage profile complete)

All seven §3 stages now have independent timings: `v9_bench.py` arm D times the
context_planner plan+pack calls, and the E2E contribution row carries
`context_plan_ms`/`context_pack_ms` (38/40 ms on click-3805). Reading:
**context packing is negligible** — the dominant stages remain route (p95 46 s,
django PageRank) and the one-time snapshot builds (tokenize 9.1 s, graph 8.5 s
at p95) which the task-scoped snapshot already amortizes. No persistence beyond
the V9 snapshot is justified by this profile.

| arm | n | file_recall | span_recall | span_prec | tok p50 | lat p50 | lat p95 | lat max |
|---|---|---|---|---|---|---|---|---|
| D | 10 | 0.767 | 0.138 | 0.005 | 1342 | 8776 | 106653 | 106653 |

### D stage latencies (ms, p50/p95/max)

| stage | p50 | p95 | max |
|---|---|---|---|
| context_pack | 52 | 116 | 116 |
| context_plan | 44 | 130 | 130 |
| graph_build | 129 | 8520 | 8520 |
| route | 3780 | 46115 | 46115 |
| scan_tokenize | 324 | 9067 | 9067 |
| symbol_index | 107 | 5607 | 5607 |
| total | 3893 | 46227 | 46227 |
| two_stage | 1 | 2233 | 2233 |
