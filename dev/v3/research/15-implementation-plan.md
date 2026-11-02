# Implementation Plan (research output 15) — with reuse/integrate/build/not-build

## Reuse (unchanged, load-bearing)

repo_audit.py · contribution_rules_scan.py · duplicate_work_scan.py · diff_scope_check.py ·
evidence_manifest.py · validation_report.py · all 11 V2 references · eval suite ·
permission model · gates.

## Integrate (wrap, don't rewrite)

- **AOCI index** (if present): detected, digest-validated, consumed read-only as
  cognition backend AOCI_NATIVE (06). Never regenerate.
- **Language Server / SCIP / embedding retrieval**: optional external signals behind
  the router's pluggable-signal interface (07). Absent by default; never authoritative.
- **Aider-style structural prior**: a light PageRank over the import graph inside the
  router (stdlib, bounded) — an idea integration, not a code dependency.

## Implement (new, stdlib-only, deterministic)

| Artifact | File | Notes |
|---|---|---|
| Goal Compiler + Goal Card + digests | `scripts/goal_compiler.py` | compile/card/verify; done_when observability gate |
| Retrieval Router (lexical/path/symbol/test/history/cognition + RRF + bounded graph + abstention report) | `scripts/retrieval_router.py` | the largest component; AOCI volume parser included |
| Context Planner + Context Pack generator | `scripts/context_planner.py` | plan + pack subcommands; span extraction from symbol tables |
| Token Budget Governor | `scripts/budget_governor.py` | category accounting, soft/hard, action list, protections |
| Task Cognition Receipt | `scripts/cognition_receipt.py` | open/record-read/verify/close/reconstruct |
| Retrieval evaluation | `scripts/retrieval_eval.py` | task JSONL in; Recall@K/MRR/BCY/precision/line metrics; per-type + ablation |
| Task sets (seeded) | `dev eval tasks.jsonl` for click + fd | built from real investigated cases (write_usage hyphen, fd#1919 walk.rs anchors, etc.) |

## NOT built (explicit)

- No whole-repo semantic index / embeddings store / vector DB.
- No Neo4j/graph database (CodexGraph-style) — bounded in-process expansion instead.
- No model-authored index writer (AOCI-CODE already governs that; we only read).
- No trained pruning/compaction models (SWE-Pruner/AutoCompact) — policy + scripts only.
- No calibrated abstention scorer (ARB shows top-score thresholds don't transfer).
- No network calls, no model dependencies, no non-stdlib requirements.

## SKILL.md wiring (≤ +~110 lines; cap 500 respected)

- New § "Goal Intelligence" (compile → Goal Card → FOUND → PATCH INTENT → RESULT).
- New § "Adaptive Repository Context Acquisition" (never bulk-load; hierarchy L0–L4;
  router; radius discipline; source-verification rule; receipts).
- State machine: DISCOVER→RECON gate gains "goal contract compiled"; CANDIDATE gains
  "context plan exists"; REGRESSION unchanged; REVIEW unchanged.
- Script/reference indexes updated.

## New references (5)

`goal-contracts.md` (04+04b) · `context-acquisition.md` (06+ source-verification rule) ·
`retrieval-strategies.md` (05+07+08+09) · `context-packing.md` (10+11+12+13) ·
`retrieval-evaluation.md` (14).

## Sequencing (task breakdown → GitHub issues)

1. Repo hosting + baseline push (V2 as-is).
2. Research artifacts commit (files 01–15).
3. Goal Intelligence: goal_compiler.py + goal-contracts.md + SKILL.md section.
4. Context acquisition core: retrieval_router.py + retrieval-strategies.md +
   context-acquisition.md.
5. Planning/budget/receipt: context_planner.py, budget_governor.py,
   cognition_receipt.py + context-packing.md.
6. Evaluation: retrieval_eval.py + task sets + retrieval-evaluation.md + eval docs
   update.
7. Validation runs on click/fd clones; close issues; final report.

Each numbered step = one commit (or small series) referencing its issue; issues closed
by commit messages (`Closes #N`).
