# V11 Phase-2 improvement criterion (finalized BEFORE implementing the fix)

Baseline measured on the 2 held-out tasks (runs/heldout-results.jsonl, tag=baseline):

| task | file_recall | gold_rank | root_cause_hits | backends |
|---|---|---|---|---|
| heldout-chi-1156 | 1.0 | 1 | **0** | LEXICAL only |
| heldout-trpc-7769 | 1.0 | 1 | **0** | LEXICAL only |

**Baseline finding that changed the picture:** the pre-registered H4 framing
("non-Python tasks totally miss files") does NOT generalize — on these two
held-out tasks lexical routing finds the gold file at rank 1. What IS
uniformly broken on non-Python: symbol-level localization
(`root_cause_hits=0` on both; the python-ast symbol family is empty for
TS/Go). The V9 vite/clap total misses are task-dependent lexical failures,
not a universal non-Python file-recall failure.

**Fix target (unchanged candidate #1):** consume Serena/LSP in
`repository_intelligence.locate` when configured (it is currently advertised
but never called).

## Final metric (fixed now, before implementation)

- **Primary (the dimension the fix targets):** `root_cause_hits` on each
  held-out task: baseline 0 → ≥1 (a symbol span inside a gold file, carrying
  digest + provenance). Direction must hold on BOTH tasks.
- **Non-regression guard:** file_recall stays ≥ baseline (1.0) and gold_rank
  stays 1 on both.
- **Honesty clause:** if Serena's find_symbol returns nothing usable because
  blind PR-title words do not name symbols, that is a REAL negative result —
  record it, roll back nothing that helps, and report exactly why.

n=2 → sign-test logic only; raw numbers reported; no CI theater.
