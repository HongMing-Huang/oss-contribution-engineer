# Goal 3 Validation — Real Upstream Contribution Loop

All executions below were really run in this workspace on 2026-10-05. Provenance rule:
nothing is claimed without a recorded execution or artifact. Companions:
[goal-2-gap-analysis.md](goal-2-gap-analysis.md), [goal-2-validation.md](goal-2-validation.md);
v1 records in [validation-results.md](validation-results.md) unchanged.

## 1. What changed (implementation, compact)

- `scripts/evidence_manifest.py` — new `--head-bound` flag on `record`: marks evidence
  that certifies the HEAD it ran on (GREEN, suites, lint, build). RED proofs and
  pre-fix baselines stay unbound by design.
- `scripts/validation_report.py` — HEAD-aware staleness: a head-bound PASS whose
  recorded git HEAD ≠ current HEAD becomes **STALE** (exit 5, blocks the conclusion,
  lists files changed since — evidence-dir/pycache noise filtered). Once a *later*
  head-bound record covers the current HEAD, the old entry displays **SUPERSEDED
  (rerun as #N)** — visible history, never active PASS. `--head` lets the caller pin
  the reference (e.g. a captured PR head SHA).
- `scripts/upstream_state.py` (new, parse-only like duplicate_work_scan) — prints
  exact `gh` capture commands, then classifies captured pr/reviews/timeline JSON into
  exactly one of MERGED · CLOSED_NOT_MERGED · SUPERSEDED · WITHDRAWN ·
  DROPPED_OR_STALE · WAITING_FOR_REVIEW · CHANGES_REQUESTED · READY_FOR_REREVIEW, with
  the facts behind the call. Ambiguity policy: missing data resolves to the
  more-honest branch — never MERGED, never READY_FOR_REREVIEW without a signal.
  `--local-repo` cross-checks PR head SHA against a local checkout;
  `--checks-file` aggregates captured CI check-runs into the facts ("CI passed" is a
  classification, not a self-report).
- SKILL.md — outcome taxonomy replaces UPSTREAM_RESOLVED (0 occurrences remain);
  IN_REVIEW gates are evidence-bound (capture → classify; READY_FOR_REREVIEW requires
  fixes + re-recorded evidence + signaled re-review); DURING REVIEW block extended to
  the 5-part form (concern / code context / assessment / evidence / action);
  § Upstream lifecycle section; script index updated.
- references/review-response.md — loop now requires contributor walkthrough of the
  5-part assessment BEFORE any upstream reply; design objections settled before
  rewriting; fixes pushed as new commits (k8s); explicit re-review signal (PTAL /
  re-request); new § Upstream outcome classification with the taxonomy table and
  closed≠success rule. Worksheet gains Assessment/Code-context columns, rereview-signal
  and outcome sections. testing-strategy.md § Stale validation now points at the
  enforced `--head-bound` mechanism. README state machine + script list updated.
- Research basis (fetched 2026-10-05): Kubernetes PR guide (PTAL, new commits not
  squashed, /hold, Tide, 90-day stale closure, OWNERS, AI-PR closure rule) on top of
  goal-2's kernel/Git fetches (respond to every comment; defend design first; 4-week
  inactive-topic discard).

## 2. The core test — review-driven change without lying about old evidence

Drill repo `/tmp/oss-goal3-loop` (fixture defect: `divide(1,0)` returns `None`),
commits `d0ae1a9` (baseline) → `d93dc5b` (fix = "published" PR head) → `e4af988`
(review-driven change). All via `evidence_manifest.py record`:

| # | Purpose | Flags | Result |
|---|---------|-------|--------|
| 1 | LEVEL 0 baseline (pre-fix) | (unbound) | PASS — artifact 001 |
| 2 | RED on unmodified upstream | `--expect-fail` (unbound) | PASS (expected failure) — artifact 002 |
| 3 | GREEN after fix | `--head-bound` @ `d0ae1a9`* | PASS — artifact 003 |
| 4 | GREEN v2 after review change | `--head-bound` @ `e4af988` | PASS — artifact 004 |

*recorded pre-commit, so its captured HEAD is the baseline — exactly the
"evidence predates the code it must describe" situation.

Sequence witnessed:

1. Review concern (design): "error message must name the divisor" → applied as a
   production change to `calc.py`; fix commit `d93dc5b` is the PR head.
2. `validation_report.py` immediately after the change (before any rerun): GREEN
   entry → **STALE (recorded at d0ae1a9; current HEAD e4af988)**, conclusion
   "STALE — rerun affected validation before citing PASS", **exit 5**; markdown report
   names the files to re-cover: `calc.py, tests/test_calc.py`. The pre-rerun state was
   additionally reproduced on demand via `--head d93dc5b…` → exit 5 (a "everything
   still passes" claim at that point is structurally blocked).
3. Suite rerun recorded `--head-bound` at `e4af988` (artifact 004) → report now shows
   old entry **SUPERSEDED (rerun as #4 at current HEAD)**, 3 passed / 0 stale,
   conclusion **PASSED**, exit 0 — passing *only* via the new record.
4. Manifest integrity: artifact hashes verified (`verify`) matching.

This is eval 16, executed end-to-end. The old PASS was never attached to the changed
code: between the change and the rerun the only obtainable conclusion was STALE.

## 3. Outcome classification — 10/10 on preserved gh-shaped fixtures

Fixtures (kept in [eval/fixtures/pr-state/](eval/fixtures/pr-state/), generator
`generate.py`): realistic `gh pr view --json` / `gh api …/reviews` / `…/timeline`
shapes, ISO timestamps.

| Fixture | Expected | Classified | Decisive signal |
|---------|----------|------------|-----------------|
| 01-changes-requested | CHANGES_REQUESTED | ✓ | latest review CHANGES_REQUESTED; head unchanged since |
| 02-ready-for-rereview | READY_FOR_REREVIEW | ✓ | fixes pushed after review + author "PTAL" comment post-push |
| 03-waiting-no-signal | WAITING_FOR_REVIEW | ✓ | fixes pushed, no re-review signal — gap named |
| 04-waiting-no-review | WAITING_FOR_REVIEW | ✓ | open, no review submissions captured |
| 05-merged | MERGED | ✓ | closed + merged=true (the only success) |
| 06-closed-not-merged | CLOSED_NOT_MERGED | ✓ | closed by maintainer, not author, not merged |
| 07-withdrawn | WITHDRAWN | ✓ | closed by the author |
| 08-dropped-stale | DROPPED_OR_STALE | ✓ | lifecycle/stale label, bot closure |
| 09-superseded | SUPERSEDED | ✓ | body "Superseded by #57" |
| 10-ambiguous-closed | CLOSED_NOT_MERGED + ambiguity | ✓ | no timeline → "closer unknown — NOT treated as success" |

`--local-repo` cross-check: local HEAD `e4af9881` vs fixture head `aaaa…` →
**MISMATCH — local validation does not describe the PR head; rebase/rerun** (matches
the drill's actual state after the review change). READY_FOR_REREVIEW was produced
only in fixture 02 (eval 18's signal distinction). No closed-without-merge capture
resolved to success language (eval 17's hard rule).

CI/check-run evidence: `--checks-file` aggregates captured check-runs into the facts —
verified on the preserved fixture 02 with an injected failing run:
`ci: 2/3 checks passed, 0 pending, FAILED: e2e-matrix` (checks.json kept with the
fixture). "CI passed" is therefore also a classification of captured state, not
self-report; CI failure surfaces in facts without altering the lifecycle outcome.

## 4. Static conformance

- `py_compile` all scripts in `scripts/` (six originals + upstream_state + v3 set):
  OK on 2026-10-05.
- SKILL.md: description 1013 chars (≤1024); `UPSTREAM_RESOLVED` occurrences: **0**;
  outcome taxonomy present in state machine, gates, script index, README.

## 5. What was NOT validated (stated, not hidden)

- No live GitHub PR was created/closed (no REMOTE_WRITE side effects); the classifier
  ran on realistic captured-JSON shapes, so live-capture variance (exact GraphQL field
  spellings, bot actor names) is covered only as modeled. `commands` output shows the
  exact gh invocations for real capture.
- The JUSTIFY branch of review response (respectfully declining a change with
  evidence) remains trace-graded (eval 13 notes this); the drill's concern was
  accepted.
- Human-in-the-loop steps (explain-back during review, contributor confirming the
  5-part assessment) are encoded in SKILL.md/reference/worksheet; no live human
  session was run for this goal.
