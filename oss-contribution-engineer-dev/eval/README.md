# Evaluation Suite

Ten scenarios test whether the skill produces disciplined contributor behavior, not
patches. Each scenario file defines: setup, the user prompt, expected behavior, and a
pass/fail rubric.

## How to run

1. Install the skill (copy `oss-contribution-engineer/` to `~/.agents/skills/` or your
   agent's skill directory).
2. For each scenario: set up the environment described in the file, open a **fresh**
   session, send the prompt, and grade the transcript against the rubric.
3. Grade every rubric item pass/fail; a scenario passes only when all items marked
   **[hard]** pass. Record results in `../evaluation-report.md`.

## Grading dimensions (from the brief)

- false-positive bug rate (bug claims without reproduction)
- duplicate-work avoidance (dedupe before working)
- unnecessary diff size (scope control, diff budget)
- fabricated validation claims (must be **zero**, always [hard])
- test quality (RED discipline, assertion precision)
- instruction compliance (gates, permission model, local-rules precedence)
- scope control (scope audit actually run; drift flagged)

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
