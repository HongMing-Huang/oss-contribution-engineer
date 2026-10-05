# Fusion & Ranking Proposal (research output 9)

Scores are ordering evidence, **not calibrated probabilities** (V2 rule: no fake
precision; ARB: abstention thresholds are not yet reliable). Every rank carries its
reason.

## Primary fusion: Reciprocal Rank Fusion

For each signal family s producing ranking r_s over candidates:

```
RRF(c) = Σ_s  weight(task_type, s) / (k + rank_s(c))        k = 60 (standard)
```

- `weight(task_type, s)`: task priors from 05 (default 1.0; e.g. code2test:
  test=1.5, symbol=1.2, lexical=1.0, path=0.5; trace2code: lexical=1.5,
  history=1.2, symbol=1.0; edit2ripple: graph=1.5, test=1.2; explore:
  cognition=1.5, path=1.2, graph=1.0).
- Anchor boosting (Aider's lesson, generalized): files mentioned in the goal
  contract / given as context get a rank-position bump into the candidate set but are
  labeled `given` — for comment2context they are excluded from "new context" results.

## Secondary adjustments (after RRF, before output)

| Adjustment | Rule |
|---|---|
| graph-distance penalty | applied inside expansion scores (08), surfaced as a reason |
| centrality prior | tiny bonus for files already prominent in backend cognition importance tags (AOCI C≥7) — cap at one rank position; never dominates query evidence |
| query-mention bonus | identifiers from the query appearing in symbol tables (LocAgent's finding that named symbols should dominate) |
| test/source identity | a file counted as gold for `tests` edges is not double-counted as lexical-new |
| recency decay | history signal: weight = 1/log(2 + days_since); recorded, capped |

## Ties, transparency, honesty

- Deterministic tie-break: (rrf, then lexical rank, then path lexicographic).
- Output always includes per-signal ranks for the top-K and one-line reasons.
- Ranking is presented as "signals we observed", not confidence: no probabilities, no
  "match %".

## Abstention (NO_RELEVANT_LOCAL_CONTEXT)

Allowed, structurally supported, honestly framed per ARB's negative result:

- The router emits an abstention *report* whenever: (a) every family's top score is
  below that family's noise floor, AND (b) fused top-1 sits below a configured floor,
  AND (c) no cognition object maps to the query domain.
- Default `--abstain-floor` is 0 (feature visible, conservative off) because ARB shows
  top-score thresholds calibrated even across corpora fail to transfer (lexical
  selective success 0.499 → 0.294 on natural no-gold after de-biasing controls).
  The agent decides abstention *with* the report, not from a pseudo-probability.
- Report fields: per-family top score + noise floor, query-domain coverage, whether
  the issue may live outside the repo (like ARB's externally-resolved no-gold class).
