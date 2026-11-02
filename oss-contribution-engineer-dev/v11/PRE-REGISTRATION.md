# V11 Priority Pre-Registration

**Written BEFORE reading any run data. Do not edit after analysis begins.**
This file pre-registers the ranking criteria and the hypotheses each candidate
must satisfy, so the backlog order is testable rather than narrated.

## Objective function ordering (fixed)

- **G1 贡献决策正确性** — wrong localization / wrong patch-no-patch decision
- **G2 Agent 可操作性** — friction requiring workarounds
- **G3 成本** — latency/tokens with correct results

A candidate scores only for the highest goal it can break (G1 failures dominate
G2 dominate G3).

## Ranking metric

`rank ∝ IG ÷ E`

- **IG (information gain)**: reduction in uncertainty about *which G1 failures
  the system actually causes*, measured from raw run data as: number of tasks
  where the candidate is *attributably* responsible for a wrong
  candidate_root_cause / wrong file ranking / wrong terminal classification —
  NOT merely present.
- **E (effort)**: S (≤1 file, local) / M (few files + re-validation) /
  L (external dependency or new harness).

## Pre-registered hypotheses (falsifiable, to be tested against raw JSONL)

- **H1 stage-2 same-name confusion**: v9-r1 D-arm rows exist where
  `functions[]` point ONLY at test files while `gold_prod_files` differ
  (production-vs-test confusion). Falsified if no such row.
- **H2 django 46s latency**: profile attributes ≥90% of route wall time to
  PageRank proper (not overhead); AND zero G1 failures in raw data are
  attributable to latency. Falsified if latency caused any wrong outcome.
- **H3 official AOCI unproven**: zero failures in raw data are attributable to
  AOCI-runtime absence (no task repo has AOCI volumes). Falsified if any row
  shows an AOCI-dependent failure.
- **H4 no-LSP non-Python**: non-Python tasks' D-arm span recall comes only from
  lexical fallback (B-arm ≈ 0), so G1 localization quality is untested on
  those languages. Falsified if non-Python D-arm localization is gold-accurate
  without LSP.

## Confusion-matrix definition (for the raw-data pass)

For each (task × arm) row in v9-r1.jsonl and v9-r2-pack.jsonl:
- predicted-positive files = files/functions the arm surfaced
- gold = gold_prod_files (+ gold spans)
- record per row: TP-file, FP-file (surfaced but not gold), FN-file (gold
  missed), and whether stage-2 function hits are `test-only` / `prod-hit` /
  `mixed` — the class H1 needs.

## Improvement criterion template (Phase 2, written before fix)

For the #1 item: "improved" = on the 2 frozen held-out tasks, [quantified
metric] improves vs baseline by ≥ the pre-written threshold, with direction
consistent on BOTH tasks (n=2 → sign test, no CI theater; report raw numbers).
