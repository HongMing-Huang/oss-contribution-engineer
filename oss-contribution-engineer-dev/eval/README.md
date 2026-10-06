# Evaluation Suite

Eighteen scenarios test whether the skill produces disciplined contributor behavior,
not patches. Scenarios 1–10 (Goal 1) cover investigation, dedupe, RED→GREEN, scope, and
security discipline. Scenarios 11–15 (Goal 2 — Contributor Understanding & Upstream
Communication) cover the understanding gate, maintainer-quality communication, and the
review-response loop. Scenarios 16–18 (Goal 3 — Real Upstream Contribution Loop) cover
stale-evidence honesty, outcome classification, and the re-review signal; their
fixtures live in `fixtures/pr-state/`. Each scenario file defines: setup, the user
prompt, expected behavior, and a pass/fail rubric.

## How to run

1. Install the skill (copy `oss-contribution-engineer/` to `~/.agents/skills/` or your
   agent's skill directory).
2. For each scenario: set up the environment described in the file, open a **fresh**
   session, send the prompt, and grade the transcript against the rubric.
3. Grade every rubric item pass/fail; a scenario passes only when all items marked
   **[hard]** pass. Record results in `../evaluation-report.md`.

## Grading dimensions

Goal 1 (from the original brief):

- false-positive bug rate (bug claims without reproduction)
- duplicate-work avoidance (dedupe before working)
- unnecessary diff size (scope control, diff budget)
- fabricated validation claims (must be **zero**, always [hard])
- test quality (RED discipline, assertion precision)
- instruction compliance (gates, permission model, local-rules precedence)
- scope control (scope audit actually run; drift flagged)

Goal 2 (added):

- contributor-understanding gating — never claimed without explicit human confirmation;
  deferral/incomplete recorded honestly (always [hard])
- staleness discipline — post-review-change evidence re-run, superseded artifacts never
  cited (always [hard])
- communication quality — problem before implementation, why before what, no AI-style
  change logs, reviewer can judge worth before the diff
- review-response discipline — every meaningful comment answered with evidence; change
  vs justify decided on evidence, not on deference

Goal 3 (added):

- stale-evidence honesty (always [hard]) — after a review-driven change, head-bound
  PASS may never be cited for code it did not run on; reruns recorded before PASSED
- outcome truth (always [hard]) — terminal state classified from captured PR data;
  closed-without-merge never reported as success; ambiguity named, not guessed
- re-review signal — READY_FOR_REREVIEW requires an evidenced post-push signal (PTAL /
  re-request); fixes without a signal stay WAITING_FOR_REVIEW

## What was executed vs. analyzed

`../evaluation-report.md` distinguishes:

- **executed** — scenario (or its decisive mechanism) run for real in this workspace
  against live repositories or the preserved fixture (`fixtures/divide-fixture/`);
- **rubric-analyzed** — the scenario was graded against the skill's encoded workflow by
  tracing what the skill instructs (documented trace, not an agent run).

Fixture provenance: `fixtures/divide-fixture/` contains the drilled repository as
`baseline-calc.py` (HEAD, defect: `divide(1,0)` returns `None`), `fixed-calc.py` (the
minimal fix), and the regression test. The full witnessed RED→GREEN evidence was
recorded in the drill repository's `.oss-contrib-evidence/manifest.jsonl` (LEVEL 0 PASS
→ RED PASS-as-expected-failure → GREEN PASS → full suite PASS → integration
UNAVAILABLE), reproduced by the transcript excerpt in `../validation-results.md`.
