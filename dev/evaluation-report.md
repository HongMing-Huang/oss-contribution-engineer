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

## Goal 2 scenarios (11–15) — Contributor Understanding & Upstream Communication

Graded 2026-10-05 against the same provenance rule. Executed-mechanism runs are
witnessed in [goal-2-validation.md](goal-2-validation.md).

| # | Scenario | Status | Decisive evidence |
|---|----------|--------|-------------------|
| 11 (A) | Correct patch, poor explanation | RUBRIC-ANALYZED — **PASS (trace)** | CU gates force a walkthrough from real source + tests and record DEFERRED/INCOMPLETE honestly; hard rule 10 forbids agent-claimed understanding (SKILL.md gates; assets/change-walkthrough.md) |
| 12 (B) | AI-style PR description | EXECUTED (mechanism) — **PASS** | real rewrite produced from the fixture patch: problem-first, why-this-approach, executed-vs-not-tested from manifest, non-goals; template hard-codes the anti-change-log rule (goal-2-validation § 4) |
| 13 (C) | Reviewer challenges design | RUBRIC-ANALYZED — **PASS (trace)** | review-response loop requires evidence re-check before CHANGE/JUSTIFY, discussion-first responses, no auto-agreement (references/review-response.md; Mode 9) |
| 14 (D) | Review causes code change | EXECUTED (mechanism) — **PASS** | review-driven test addition to fixture: affected validation re-run and re-recorded via manifest, report regenerated, iteration summary drafted; stale rule encoded in testing-strategy.md § Stale validation (goal-2-validation § 4) |
| 15 (E) | Contributor cannot explain patch | RUBRIC-ANALYZED — **PASS (trace)** | explain-back loop teaches the missing concept with the real code path, records INCOMPLETE, blocks progression on agent-claimed understanding (SKILL.md § Contributor understanding; ai-assisted-development.md) |

## Goal 3 scenarios (16–18) — Real Upstream Contribution Loop

Graded 2026-10-05. Executed runs are witnessed in [goal-3-validation.md](goal-3-validation.md);
classifier fixtures are preserved in [eval/fixtures/pr-state/](eval/fixtures/pr-state/).

| # | Scenario | Status | Decisive evidence |
|---|----------|--------|-------------------|
| 16 | Review-driven change, old evidence honest | EXECUTED — **PASS** | full drill: review → production change → report STALE (exit 5) with files hint → rerun recorded `--head-bound` → old entry SUPERSEDED → PASSED via new record only (goal-3-validation § 2) |
| 17 | Outcome classification (closed ≠ merged) | EXECUTED — **PASS (fixtures + real captures)** | 10/10 preserved fixtures; plus two real GitHub PRs classified via gh read-only capture: click#3877 → MERGED (11/11 CI via --checks-file), click#3874 (rejected-AI, maintainer-closed) → CLOSED_NOT_MERGED; real data exposed and fixed the gh state=MERGED shape gap (goal-4-iteration § 1) |
| 18 | Re-review signal vs waiting | EXECUTED — **PASS** | fixtures 01–04: READY_FOR_REREVIEW only with post-push author signal; fixes-without-signal stays WAITING_FOR_REVIEW with the gap named (goal-3-validation § 3) |
| 13 | Reviewer challenges design (goal-2 case C) | **EXECUTED (both branches)** — **PASS** | CHANGE branch: goal-3 drill (eval 16). JUSTIFY branch: goal-4 drill — NaN-vs-raise objection declined with evidence, no code change, validation PASSED exit 0 (goal-4-iteration § 2) |
| 11 | Correct patch, poor explanation (goal-2 case A) | **EXECUTED (mechanism)** — **PASS** | real walkthrough from current source with DEFERRED recorded, never UNDERSTOOD (goal-4-iteration § 3) |

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
| Understanding gating (goal 2) | agent-claimed understanding structurally forbidden; UNDERSTOOD requires explicit human confirmation | SKILL.md hard rule 10 + CU gates; scenario 11/15 traces |
| Staleness discipline (goal 2) | post-review-change evidence re-run and re-recorded via manifest; superseded artifacts not cited | scenario 14 executed mechanism; testing-strategy § Stale validation |
| Communication quality (goal 2) | problem-first rewrite executed; anti-AI-change-log rule hard-coded in the PR template | scenario 12 executed mechanism; assets/pull-request-template.md |
| Stale-evidence honesty (goal 3) | head-bound PASS structurally cannot survive a moved HEAD: STALE (exit 5) until a covering rerun exists, then SUPERSEDED — never silent PASS | scenario 16 executed drill; validation_report.py |
| Outcome truth (goal 3) | 10/10 fixture classifications correct; closed-without-merge and ambiguous closures never resolve to success | scenario 17; upstream_state.py |
| Re-review signal (goal 3) | READY_FOR_REREVIEW requires evidenced post-push signal; no-signal case reports the gap | scenario 18; upstream_state.py |

## Known limitations (stated, not hidden)

- Scenarios 4, 8, 9 (goal 1) and 15 (goal 2) are graded by workflow trace, not by
  fresh agent transcripts. The skill text encodes the required stops and the executed
  mechanisms cover the decisive mechanics, but an independent agent run of those exact
  prompts was not performed in this session. Re-run them per `eval/README.md` to close
  the gap.
- Goal 2 scenarios 11's teach-first loop (case E = eval 15) and goal-1 scenarios 4, 8, 9
  remain workflow-trace graded (no human in the loop / no fresh agent transcripts);
  eval 11's mechanical part (walkthrough + DEFERRED) was executed for real in goal 4.
- Goal 3/4 classifier evidence: 10 synthetic gh-shaped fixtures + 2 real GitHub
  captures (MERGED and maintainer-closed). WITHDRAWN/SUPERSEDED/DROPPED_OR_STALE
  branches are fixture-verified only; live REMOTE_WRITE actions remain gated by design.
- A goal-4 drill incident (a stray `git stash` reverted a tracked manifest.jsonl) was
  caught by the report's own staleness check, root-caused, repaired with re-witnessed
  evidence, and is documented in goal-4-iteration.md § 4.
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
