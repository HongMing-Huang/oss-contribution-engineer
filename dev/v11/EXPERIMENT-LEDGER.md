# V11 Experiment Ledger — Evidence-Driven Prioritization Round

Status: **EXPERIMENTAL**. Protocol per PRE-REGISTRATION.md (criteria written
before data) → raw-data pass → BACKLOG.md → single improvement → held-out
validation per CRITERION.md.

## Phase 1 — raw-data findings (no ledger summaries consulted)

Aggregate file-level confusion matrix from raw v9 JSONL rows (10 tasks,
16 gold files; dedup r1+r2):

| arm | TP | FP | FN | precision | recall |
|-----|----|----|----|-----------|--------|
| A2 grep | 7 | 33 | 9 | 0.175 | 0.438 |
| B symbol | 3 | 6 | 13 | 0.333 | 0.188 |
| C router | 8 | 72 | 8 | 0.100 | 0.500 |
| D full | 9 | 71 | 7 | 0.113 | 0.562 |

Hypothesis tests (all against raw rows/files):
- **H4 partially refuted on file recall, confirmed on symbol recall**: the two
  V9 non-Python total misses (vite, clap) did NOT generalize — both V11
  held-out non-Python tasks hit gold at rank 1 with lexical only. What IS
  uniform: `root_cause_hits=0` (python-ast symbol family empty for TS/Go).
- **H1 confirmed, bounded**: raw investigation state shows test-file pollution
  co-occurring WITH the correct rank-1 production hit.
- **H2 confirmed G3-only**: 0 budget-stops, 0 latency-attributable failures in
  60 rows.
- **H3 zero evidence**: 0 AOCI-attributable failures.

Backlog (BACKLOG.md): #1 wire Serena/LSP into `locate` (the
advertise-but-don't-call gap); #2 test-hit deprioritization; NOT doing
H2/H3/precision work (evidence-cited).

## Phase 2 — held-out validation (chi#1156 Go, trpc#7769 TS; never run before)

| task | tag | file_recall | gold_rank | root_cause_hits |
|---|---|---|---|---|
| chi-1156 | baseline | 1.0 | 1 | 0 |
| chi-1156 | after (Serena wired) | 1.0 | 1 | **1** ✅ |
| trpc-7769 | baseline | 1.0 | 1 | 0 |
| trpc-7769 | after (Serena wired) | 1.0 | 1 | **0** ❌ |

Raw rows: `runs/heldout-results.jsonl`.

**Pre-registered criterion NOT met** (required direction on BOTH tasks).

### Negative result (kept verbatim, per protocol)

- chi improved because the blind title's word "compress" names the Compressor
  symbols in the gold file — LSP find_symbol resolved them with digests.
- trpc did not: Serena WORKED (symbols found for "responses"/"header") but in
  the wrong files — blind PR-title words ("allow header on 405 responses")
  name no symbol inside the gold `resolveResponse.ts`. This is the exact
  contingency CRITERION.md's honesty clause anticipated: title-word → symbol
  matching is task-dependent; LSP cannot conjure a symbol the text never names.
- **The improvement claim is withdrawn.** The wiring stays as dormant,
  env-gated code (unset `SERENA_MCP_COMMAND` ⇒ behavior byte-identical to
  before; 85 tests green without it) — operationally equivalent to rolled
  back in default runs; no maturity upgraded; backlog #2 NOT started
  (single-improvement rule).
- Lesson recorded: symbol-name presence in the task text is the precondition
  for LSP localization value; a follow-up would need identifier extraction
  from the CODE (e.g., lexical hits → read → extract real symbol names →
  LSP confirm), which is a different, larger mechanism — out of scope here.

## Incident notes

- pip install of serena-agent failed silently behind a SOCKS proxy
  (`Missing dependencies for SOCKS support`) — `env -u all_proxy … pip`
  fixed it; check `ls .venv/bin | grep serena` after quiet installs.
- `$PWD` inside SERENA_MCP_COMMAND expanded against the wrong shell cwd —
  absolute paths required; and the static command needed `--project <repo>`
  injected per call (now done in `_serena_symbols`).
