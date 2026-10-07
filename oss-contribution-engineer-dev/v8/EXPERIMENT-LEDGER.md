# V8 Experiment Ledger — Real-Repository Optimization Iteration

Status: **EXPERIMENTAL** (V8+ versions are experimental iterations only; maturity is
tracked separately, see README maturity ladder). Nothing here is a release or a
readiness claim.

- Task freeze: `tasks.json` (8 tasks, 6 real repos, base SHA = merge^1; gold =
  first-parent diff of the fixing commit; the investigation arms never see it).
- Repos (blobless clones + detached worktrees, `work/` is gitignored):
  pallets/click · django/django · vitejs/vite · clap-rs/clap · gin-gonic/gin ·
  babel/babel (JS monorepo with packages/).
- Runner: `v8_bench.py` (arms A grep / B symbol / C router-no-graph / D full).
- Profiler: `v8_profile.py`.
- Raw results are append-only JSONL under `runs/` — bad results are never
  overwritten; each optimization round appends r2, r3, … and this ledger records
  before → failure → change → after per failure.

## Round 1 (frozen baseline, before any optimization)

Results: `runs/bench-r1.jsonl`

| task | arm | gold_file_recall | gold_span_recall | tokens | ops | latency_ms |
|---|---|---|---|---|---|---|

(merged automatically from the JSONL by `v8_report.py`)

### Round 2 (after F7 latency fixes: precomputed test flags + stem memo + hoisted edge totals; C/D re-run; W = warm corpus cache)

| task | arm | file_recall | span_recall | span_prec | ctx_tokens | ops | lat_ms | backend |
|---|---|---|---|---|---|---|---|---|
| click-3802-keyinterrupt-race | C | 1.0 | None | None | 110126 | 2 | 428 | LIGHTWEIGHT_FALLBACK |
| click-3805-sentinel-deepcopy | C | 0.0 | None | None | 115689 | 2 | 406 | LIGHTWEIGHT_FALLBACK |
| click-3865-short-help-abbrev | C | 1.0 | None | None | 81666 | 2 | 426 | AOCI_FILE |
| django-37377-jsonfield-in | C | 1.0 | None | None | 136555 | 2 | 32007 | LIGHTWEIGHT_FALLBACK |
| vite-safemodulepaths | C | 0.0 | None | None | 71573 | 2 | 2744 | LIGHTWEIGHT_FALLBACK |
| clap-zsh-escape | C | 0.0 | None | None | 79020 | 2 | 1221 | LIGHTWEIGHT_FALLBACK |
| gin-4818-getvalue-panic | C | 1.0 | None | None | 75423 | 2 | 221 | LIGHTWEIGHT_FALLBACK |
| babel-asynciterator-throw | C | 0.667 | None | None | 23049 | 2 | 5857 | LIGHTWEIGHT_FALLBACK |
| click-3802-keyinterrupt-race | D | 1.0 | 0.0 | 0.0 | 143 | 3 | 656 | LIGHTWEIGHT_FALLBACK |
| click-3805-sentinel-deepcopy | D | 1.0 | 0.0 | 0.0 | 23351 | 3 | 643 | LIGHTWEIGHT_FALLBACK |
| click-3865-short-help-abbrev | D | 1.0 | 1.0 | 0.412 | 336 | 3 | 657 | AOCI_FILE |
| django-37377-jsonfield-in | D | 1.0 | 0.0 | 0.0 | 1155 | 3 | 57768 | LIGHTWEIGHT_FALLBACK |
| vite-safemodulepaths | D | 0.0 | None | None | 0 | 3 | 4302 | LIGHTWEIGHT_FALLBACK |
| clap-zsh-escape | D | 0.0 | None | None | 0 | 3 | 1876 | LIGHTWEIGHT_FALLBACK |
| gin-4818-getvalue-panic | D | 1.0 | None | None | 0 | 3 | 344 | LIGHTWEIGHT_FALLBACK |
| babel-asynciterator-throw | D | 0.667 | None | None | 0 | 3 | 9317 | LIGHTWEIGHT_FALLBACK |
| click-3802-keyinterrupt-race | W | 1.0 | 0.0 | 0.0 | 143 | 3 | 334 | LIGHTWEIGHT_FALLBACK+warm-cache |
| click-3805-sentinel-deepcopy | W | 1.0 | 0.0 | 0.0 | 23351 | 3 | 604 | LIGHTWEIGHT_FALLBACK+warm-cache |
| click-3865-short-help-abbrev | W | 1.0 | 1.0 | 0.396 | 349 | 3 | 280 | LIGHTWEIGHT_FALLBACK+warm-cache |
| django-37377-jsonfield-in | W | 1.0 | 0.0 | 0.0 | 1155 | 3 | 56751 | LIGHTWEIGHT_FALLBACK+warm-cache |
| vite-safemodulepaths | W | 0.0 | None | None | 0 | 3 | 4516 | LIGHTWEIGHT_FALLBACK+warm-cache |
| clap-zsh-escape | W | 0.0 | None | None | 0 | 3 | 1559 | LIGHTWEIGHT_FALLBACK+warm-cache |
| gin-4818-getvalue-panic | W | 1.0 | None | None | 0 | 3 | 327 | LIGHTWEIGHT_FALLBACK+warm-cache |
| babel-asynciterator-throw | W | 0.667 | None | None | 0 | 3 | 6476 | LIGHTWEIGHT_FALLBACK+warm-cache |

### Round 1 (frozen baseline, pre-optimization)

| task | arm | file_recall | span_recall | span_prec | ctx_tokens | ops | lat_ms | backend |
|---|---|---|---|---|---|---|---|---|
| click-3802-keyinterrupt-race | A | 0.0 | 0.0 | 0.0 | 16578 | 5 | 71 | - |
| click-3802-keyinterrupt-race | B | 1.0 | 0.0 | 0.0 | 132 | 10 | 2703 | python-ast |
| click-3802-keyinterrupt-race | C | 1.0 | None | None | 110126 | 2 | 873 | LIGHTWEIGHT_FALLBACK |
| click-3802-keyinterrupt-race | D | 1.0 | 0.0 | 0.0 | 143 | 3 | 1282 | LIGHTWEIGHT_FALLBACK |
| click-3805-sentinel-deepcopy | A | 0.0 | 0.0 | 0.0 | 78968 | 5 | 34 | - |
| click-3805-sentinel-deepcopy | B | 0.0 | 0.0 | 0.0 | 1003 | 9 | 2176 | python-ast |
| click-3805-sentinel-deepcopy | C | 0.0 | None | None | 115689 | 2 | 2934 | LIGHTWEIGHT_FALLBACK |
| click-3805-sentinel-deepcopy | D | 1.0 | 0.0 | 0.0 | 23351 | 3 | 1119 | LIGHTWEIGHT_FALLBACK |
| click-3865-short-help-abbrev | A | 0.0 | 0.0 | 0.0 | 777 | 5 | 34 | - |
| click-3865-short-help-abbrev | B | 1.0 | 1.0 | 0.412 | 336 | 9 | 2088 | python-ast |
| click-3865-short-help-abbrev | C | 1.0 | None | None | 119859 | 2 | 2862 | LIGHTWEIGHT_FALLBACK |
| click-3865-short-help-abbrev | D | 1.0 | 1.0 | 0.396 | 349 | 3 | 1261 | LIGHTWEIGHT_FALLBACK |
| django-37377-jsonfield-in | A | 0.0 | 0.0 | 0.0 | 6674 | 5 | 1642 | - |
| django-37377-jsonfield-in | B | 1.0 | 0.067 | 0.05 | 274 | 10 | 40737 | python-ast |
| django-37377-jsonfield-in | C | 1.0 | None | None | 136555 | 2 | 301455 | LIGHTWEIGHT_FALLBACK |
| django-37377-jsonfield-in | D | 1.0 | 0.0 | 0.0 | 1155 | 3 | 480661 | LIGHTWEIGHT_FALLBACK |
| vite-safemodulepaths | A | 0.0 | 0.0 | 0.0 | 2332 | 5 | 410 | - |
| vite-safemodulepaths | B | 0.0 | None | None | 0 | 10 | 298 | python-ast |
| vite-safemodulepaths | C | 0.0 | None | None | 71573 | 2 | 48114 | LIGHTWEIGHT_FALLBACK |
| vite-safemodulepaths | D | 0.0 | None | None | 0 | 3 | 76500 | LIGHTWEIGHT_FALLBACK |
| clap-zsh-escape | A | 0.0 | 0.0 | 0.0 | 14534 | 5 | 97 | - |
| clap-zsh-escape | B | 0.0 | None | None | 0 | 10 | 31 | python-ast |
| clap-zsh-escape | C | 0.0 | None | None | 79020 | 2 | 2110 | LIGHTWEIGHT_FALLBACK |
| clap-zsh-escape | D | 0.0 | None | None | 0 | 3 | 4095 | LIGHTWEIGHT_FALLBACK |
| gin-4818-getvalue-panic | A | 1.0 | 2.0 | 0.027 | 4217 | 5 | 30 | - |
| gin-4818-getvalue-panic | B | 0.0 | None | None | 0 | 10 | 6 | python-ast |
| gin-4818-getvalue-panic | C | 1.0 | None | None | 75423 | 2 | 4696 | LIGHTWEIGHT_FALLBACK |
| gin-4818-getvalue-panic | D | 1.0 | None | None | 0 | 3 | 348 | LIGHTWEIGHT_FALLBACK |
| babel-asynciterator-throw | A | 0.333 | 2.25 | 0.002 | 38293 | 5 | 4497 | - |
| babel-asynciterator-throw | B | 0.0 | None | None | 0 | 10 | 5311 | python-ast |
| babel-asynciterator-throw | C | 0.667 | None | None | 23049 | 2 | 70276 | LIGHTWEIGHT_FALLBACK |
| babel-asynciterator-throw | D | 0.667 | None | None | 0 | 3 | 48120 | LIGHTWEIGHT_FALLBACK |
| babel-asynciterator-throw | A | 0.333 | 0.5 | 0.002 | 38293 | 5 | 8561 | - |
| babel-asynciterator-throw | B | 0.0 | None | None | 0 | 10 | 8306 | python-ast |
| babel-asynciterator-throw | C | 0.667 | None | None | 23049 | 2 | 32215 | LIGHTWEIGHT_FALLBACK |
| babel-asynciterator-throw | D | 0.667 | None | None | 0 | 3 | 46671 | LIGHTWEIGHT_FALLBACK |

## Failure records (V8 section 6 — before → failure → change → after)

### F7 — large-repository query latency (the headline failure)

- **TASK:** django-37377 on django/django @8abacfc36d (6956 scanned files).
- **OBSERVED FAILURE:** cold route() 181 s; full pipeline arm D 480 s. The
  earlier ~50 s/query number from the ARB slice was real but unexplained.
- **ROOT CAUSE (profiled, not guessed — runs/profile-django.json + cProfile):**
  `tests_of()` re-scanned ALL files through 4 `is_test_path` regexes on every
  call — 88 M regex searches ≈ 100 s per route (4371 calls × O(N)); edge totals
  were recomputed inside every PageRank iteration; `read+tokenize` was only
  ~13 s and raw reads 0.66 s — the "persistent indexing for reads" hypothesis
  was WRONG for this profile.
- **EVIDENCE:** cProfile: `is_test_path` 88 M calls / 64.7 s in `re.search`.
- **CHANGE:** precompute `Corpus.test_files` once; memoize `tests_of` per stem;
  hoist static edge totals out of the iteration loop (retrieval_router.py).
- **EXPECTED EFFECT:** ranking-order-preserving speedup.
- **AFTER:** route 181 s → **35 s** (5.2×); arm C mean 51.7 s → 5.4 s (9.6×);
  arm D mean 73.3 s → 9.4 s (7.8×); top-3 candidates identical on the probe
  query; 72 tests green. Remaining measured hotspots: corpus tokenize ~10 s
  (mitigated by warm cache: arm W identical recall 0.708, 8.9 s vs 9.4 s mean),
  and the two-stage localize rebuilding its own symbol graph per run (~11 s on
  django) — recorded as future work, not fixed on intuition.

### F1 — span-recall scoring inflated >1.0

- gin-4818 arm A reported `span_recall=2.0`. **ROOT CAUSE:** overlapping
  delivery windows double-counted gold lines. **CHANGE:** unique-gold-line set.
  **AFTER:** all recalls ≤1.0; the aborted round is preserved as
  `runs/bench-r1-aborted-scoring-bug.jsonl`.

### F2 — bench crashed scoring arm C

- score() assumed step file lists; arm C stores counts. **CHANGE:** type guard.

### F3 — pre-patch gate vs tooling state

- Security-hook state (`.mimosa/hook-state/*.json`) written into the worktree
  was flagged as untracked production changes, refusing a legitimate PATCH.
- **CHANGE:** `.mimosa` added to the session's bookkeeping exclusion set
  (contribution_session.py) with a comment citing this record. 72 tests green.

### F4 — evidence commands run from the caller's cwd (OPEN)

- The first GREEN "failure" and one RED "pass" were environmental artifacts
  (ImportError / file-not-found from a different cwd; a glob test depends on
  repo-root cwd). **WORKAROUND:** absolute paths + `sh -c 'cd repo && …'`.
- **PROPOSED CHANGE (open):** `evidence_manifest.py record --cwd <dir>`.

### F5 — dynamic code blocked for experiment tooling (OPEN, environmental)

- `python3 -c <code>` is rejected by the security hook for repro drivers;
  workaround: static fixture files (`race_child.py`) + shell loops. Harness
  constraint, documented so future rounds don't re-litigate it.

### F6 — classification vocabulary gap (OPEN)

- No UNCONFIRMED / NOT_REPRODUCIBLE class exists; click-3802 (a real race, not
  reproduced in 120 witnessed rounds — designed-Abort rounds excluded) was
  recorded as DESIGN_BLOCKED with the precise verdict in the conclusion text
  and notes artifact. **PROPOSED CHANGE (open):** add UNCONFIRMED to the
  STOPPING set.

### F8 — the bench harness itself regressed (meta-failure, kept for honesty)

- Adding the raw-output cache mangled loop indentation: every post-r1 run
  silently processed ONLY the last task (r2 first attempts had 1–2 rows,
  exit 0). **DETECTED:** row-count sanity check vs task list. **CHANGE:**
  main() loop restructured; rows written for every (task, arm) again. Lesson:
  append-only JSONL + per-run row counts are the experiment's own tripwire.

## Ablations

AOCI cognition on/off (click), graph arms, symbol on/off, two-stage vs static —
appended per round; negative results kept verbatim. Full data:
`runs/ablations.json`. Summary:

- **Graph expansion:** helps in exactly 1/8 tasks materially (click-3805: C 0.0
  → D 1.0 — the structural graph found the target C missed); no task got
  WORSE. Mean +0.111 file recall (r1 numbers).
- **Two-stage localization (TWO_STAGE_LOCALIZATION_EXPERIMENT):** mean span
  recall 0.25 with span precision 0.099 — most delivered span lines are not
  gold. `SUFFICIENT_EVIDENCE` fired on 3/8 tasks and is NOT treated as
  correctness. Negative result kept: the deterministic skeleton is noisy.
- **Symbol backend:** B (0.333) beats grep (0.185) on Python tasks; returns
  nothing honestly on TS/Go/Rust tasks (no LSP configured).
- **AOCI cognition (fixture-grade):** identical routing outcomes on the three
  click tasks with vs without fixture volumes — expected: fixture F lines are
  mechanical placeholders, and no AOCI benefit may be claimed from this cell.
  The official runtime remains unproven (conformance service only).
- **Warm corpus cache:** identical recall (0.708), mean latency 9.4 s → 8.9 s —
  the cache targets the corpus phase, which profiling showed was NOT the
  dominant cost after F7; kept as infrastructure, effect now marginal.

## Contribution-path runs (V8 section 11)

- `runs/contribution-path.jsonl` — click-3805 (frozen base 3cbcf9b115):
  independent investigation → witnessed repro → RED (digest-bound) → PATCH →
  GREEN (head-bound) → upstream subset (321 passed) → UNDERSTOOD (human
  confirmed) → scope audit → **PR_READY**. The evidence chain caught a real
  defect in the first patch (overriding `__reduce__` is intercepted by
  `Enum.__reduce_ex__`). Nothing pushed; PATCH_READY is the deliverable.
- `runs/no-patch.jsonl` — click-3802 (frozen base b47c0529e9): 120 witnessed
  rounds, 0 unhandled escapes (first-pass artifacts showed the DESIGNED abort
  path — detector refined and the correction recorded); NO_PATCH via STOPPING
  classification (see F6 for the vocabulary caveat).

## Maturity statement

This iteration measures the context-acquisition layer with deterministic
protocols, not LLM reasoning. All conclusions are evidence about THIS pipeline
on THESE frozen tasks; they do not generalize without more runs.
