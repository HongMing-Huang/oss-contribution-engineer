# Goal 2 Validation — Contributor Understanding & Upstream Communication

All executions below were really run in this workspace on 2026-10-05. Provenance rule:
nothing is claimed without a recorded execution or artifact. Companion to
[goal-2-gap-analysis.md](goal-2-gap-analysis.md); v1 records in
[validation-results.md](validation-results.md) are unchanged and re-confirmed here.

## 1. Static conformance (re-run after goal-2 edits)

| Check | Result | Evidence |
|-------|--------|----------|
| `python3 -m py_compile` all 6 original scripts | OK (6/6) | shell run, 2026-10-05 (goal-2 changes touch no scripts) |
| SKILL.md frontmatter description ≤ 1024 chars after goal-2 extension | OK — 1005 chars | inline Python check, 2026-10-05 |
| SKILL.md size | 334 lines (design target ≤ 350) | line count |
| New files present | assets: change-walkthrough.md, issue-draft.md, review-response.md; references: review-response.md | directory listing |

Note: a parallel workstream (v3 Goal-Contract/cognition/retrieval architecture) added
`scripts/goal_compiler.py`, `references/goal-contracts.md`, and related v3 scripts
during this session. Goal-2 treats these as the existing Goal Model to reuse, not to
rebuild: SKILL.md § Progress communication now cross-references
references/goal-contracts.md, and no v3 file was modified.

## 2. RED→GREEN drill re-run (fixture; anti-fabrication core re-confirmed)

Repository `/tmp/oss-goal2-drill`, baseline commit `48c7350`, fix commit `57f8253`.
Commands recorded via `evidence_manifest.py record` (sha256-stamped artifacts, git HEAD
captured):

| # | Purpose | Result | Note |
|---|---------|--------|------|
| 1 | LEVEL 0 baseline (original suite, pre-regression-test) | PASS | artifact 001 |
| 2 | RED on unmodified upstream (`--expect-fail`) | PASS (expected failure — RED proof) | artifact 002; genuine `AssertionError: divide(1, 0) returned instead of raising ZeroDivisionError` — the intended defect, not an import error |
| 3 | GREEN after minimal fix | PASS | artifact 003 |
| 4 | diff scope audit `--intended calc.py,tests/test_calc.py` | WITHIN_SCOPE (exit 0) | 1 production (+1/−1), 1 test (+9/−0) |
| 5 | `evidence_manifest.py verify 003` | sha256 match | chain integrity |

Existing behavior did not regress: the exact v1 mechanism (witnessed LEVEL 0 → RED →
GREEN, true statuses, scope audit) reproduces cleanly on current code.

## 3. Stale-validation mechanism (goal-2 rule, executed)

Simulating eval 14 / the IN_REVIEW loop: with the fix committed (the "published PR"),
the reviewer request "also cover `divide(0, 0)`" was applied as a v2 test-only change.
Per testing-strategy.md § Stale validation:

- Artifact 004 recorded: full suite re-run post-change — PASS (4 passed), superseding
  artifact 003's result for the changed test state (purpose string states the
  supersession explicitly).
- `validation_report.py` regenerated: 4 executed / 4 passed / 0 failed, conclusion
  **PASSED** — with every entry traceable to a witnessed artifact.
- A production-code change would additionally re-trigger RED→GREEN; here the fix itself
  was untouched, so the recorded RED (artifact 002) still applies to unchanged
  production code — consistent with the rule as written.

## 4. Communication mechanisms (goal 2, executed)

- **Eval 12 (AI-style PR rewrite):** the contributor-style draft ("Implemented input
  validation… Updated the test file… Added tests… Everything passes.") was rewritten for
  real against the fixture patch under assets/pull-request-template.md rules —
  problem-first, why-this-approach, tests-executed from manifest artifacts (including
  explicit supersession and not-tested areas), risks, non-goals. Full artifact:
  [goal-2-pr-rewrite-example.md](goal-2-pr-rewrite-example.md). No fact appears in the
  rewrite that is not backed by a witnessed artifact or the diff.
- **Progress blocks:** the SKILL.md § Progress communication block set (INVESTIGATION /
  BEFORE PATCH / AFTER PATCH / DURING REVIEW) is defined and cross-referenced with the
  Goal Contract protocol (references/goal-contracts.md); the DURING REVIEW block is the
  goal-2 extension. Used verbatim in scenarios 13–15 rubrics.
- **UNCONFIRMED INVESTIGATION framing:** encoded in assets/issue-draft.md (honesty
  gate) and referenced from bug-hunting.md and SKILL.md hard rule 1.

## 5. Coverage statement (what was NOT validated)

- Scenarios 11, 13, 15 are rubric-analyzed traces, not fresh agent transcripts (same
  limitation class as v1 scenarios 4/8/9; stated in evaluation-report.md).
- The IN_REVIEW → UPSTREAM_RESOLVED transition involves live GitHub state (merge/close)
  and was not exercised; its mechanics (iteration summary, response drafts) are
  artifact-templates validated by inspection only.
- Parallel v3 scripts (goal_compiler.py etc.) were not compiled or run by this workstream
  — outside goal-2 scope and possibly mid-edit by their own session.
