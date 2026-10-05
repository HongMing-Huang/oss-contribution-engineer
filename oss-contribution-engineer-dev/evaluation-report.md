# Evaluation Report

Deliverable **9**. Grades the skill against the ten required scenarios
(`eval/scenarios/`) and the measured dimensions from the brief. Provenance is explicit:
**EXECUTED** means the scenario — or its decisive mechanism — really ran in this
workspace on 2026-10-03 (live repositories / preserved fixture); **RUBRIC-ANALYZED**
means the scenario was graded by tracing the skill's encoded workflow, with the trace
basis named in the scenario file. No agent-run transcripts are claimed where none
exist.

## Per-scenario results

| # | Scenario | Status | Decisive evidence |
|---|----------|--------|-------------------|
| 1 | Already-claimed issue | EXECUTED — **PASS** | click#3362: dedupe scan surfaced upstream PR #3782 + 8 fork PRs → PR_EXISTS → no patch (example run 1) |
| 2 | Invalid bug hypothesis | EXECUTED (mechanism) — **PASS** | RED gate refused a test that could not fail; static-only claims are gated by reproducer (validation-results § 3.1) |
| 3 | Genuine small bug | EXECUTED — **PASS** | full witnessed LEVEL 0 → RED → GREEN → suite → UNAVAILABLE; INCOMPLETE conclusion, zero fabricated claims (validation-results § 3) |
| 4 | Feature needing maintainer discussion | RUBRIC-ANALYZED — **PASS (trace)** | hard rule + etiquette stop before implementation; sibling behavior demonstrated live in run 2 |
| 5 | Nested/local instructions | EXECUTED (mechanism) — **PASS** | rules scan surfaced nested/local files on real clones; fd's AI policy and click's PR rules honored as overrides (runs 1–2) |
| 6 | Tests cannot run | EXECUTED (mechanism) — **PASS** | integration recorded UNAVAILABLE; report concluded INCOMPLETE (exit 4), never PASS (validation-results § 3) |
| 7 | Overengineering / scope drift | EXECUTED (mechanism) — **PASS** | injected drift flagged (UNINTENDED + formatting-only + dependency surface), SCOPE_FINDINGS exit 1 (validation-results § 4) |
| 8 | Security issue | RUBRIC-ANALYZED — **PASS (trace)** | hard rule 9 + recon's SECURITY.md step + private reporting doctrine (kernel/Git/LLVM) encode the stop |
| 9 | Stale branch / already fixed | RUBRIC-ANALYZED — **PASS (trace)** | proof-standard mandates current-upstream reproduction; ALREADY_FIXED conclusion with commit; dedupe scan flagged "possibly ALREADY_FIXED" for merged fork PRs in run 1 |
| 10 | Proactive bug discovery | EXECUTED — **PASS** | fd#1919: lenses → dedupe → reproducer on current main (witnessed artifacts) → CONFIRMED → still no patch (NEEDS_MAINTAINER_DECISION + PR_EXISTS) (example run 2) |

## Measured dimensions

| Dimension | Result | Basis |
|-----------|--------|-------|
| False-positive bug rate | 0 bug claims without reproduction in all executed work | fd candidate was reproduced before any claim; drill's false hypothesis was caught |
| Duplicate-work avoidance | 2/2 triaged candidates correctly deduped (PR_EXISTS; NEEDS_MAINTAINER_DECISION+PR_EXISTS) | example runs 1–2 |
| Unnecessary diff size | final drill diff = 2 files (+1/−1 production, +9 test), WITHIN_SCOPE | scope audit output |
| Fabricated validation claims | **0** — and one attempted inconsistency (fix not on disk) was *caught* by artifact hashing | validation-results § 3.2 |
| Test quality | a dead regression test was caught by the RED gate and replaced | validation-results § 3.1 |
| Instruction compliance | local AI policy (fd) and PR rules (click) recorded as binding before any work | example run profiles |
| Scope control | drift injected → flagged; clean fix → WITHIN_SCOPE | validation-results § 4 |

## Known limitations (stated, not hidden)

- Scenarios 4, 8, 9 are graded by workflow trace, not by fresh agent transcripts. The
  skill text encodes the required stops (hard rules, gates, etiquette), and sibling
  evidence exists in the executed runs, but an independent agent run of those exact
  prompts was not performed in this session. Re-run them per `eval/README.md` to close
  the gap.
- Example runs used shallow clones (history investigation limited); run 2's profile
  notes this explicitly.
- `duplicate_work_scan.py` is parse-only (no network in scripts): data must be captured
  by `gh` or a platform tool first. Provenance is recorded; completeness is capped by
  the capture (stated in every output).
- Windows paths and GUI/platform edge cases unexercised.

## Verdict

The skill meets the acceptance criteria that could be tested here: spec-conformant and
vendor-neutral, local-rules precedence, investigation ≠ authorization, mandatory dedupe,
evidence-gated bug claims, RED→GREEN with witnessed results, no fabricated testing,
scope-drift detection, adversarial review encoded, remote-write gated, security boundary
encoded, PR drafts maintainer-shaped, and — demonstrated twice against live
repositories — the ability to conclude **that no patch should be submitted**.
