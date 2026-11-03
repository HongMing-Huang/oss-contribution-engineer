# oss-contribution-engineer

A vendor-neutral [Agent Skill](https://agentskills.io) that turns a coding agent into a
disciplined open-source contributor: it investigates before editing, demands evidence
before claims, reproduces before fixing, prefers a regression test that fails first,
keeps patches minimal, and treats maintainer time as the scarcest resource.

**This skill is not intended to maximize PR count.** It is intended to maximize:

- correctness — claims backed by execution, not by plausibility
- learning — the contributor understands the subsystem they touched
- maintainer trust — small, verified, honest changes that are easy to review
- reproducibility — evidence records and validation reports that stand alone
- contribution quality — no farming, no slop, no duplicate work
- long-term credibility — knowing when *not* to submit is part of the job

> AI may accelerate investigation, testing, implementation, and review, but it must
> never replace evidence, engineering judgment, or human responsibility.

The doctrine behind the rules comes from the Linux kernel's AI-assistant and patch
policies, Git's SubmittingPatches, LLVM's contributing/review docs, and Google's
engineering-practices guides — paraphrased with sources in
`references/contribution-doctrine.md`.

## Install

```bash
npx skills add https://github.com/HongMing-Huang/oss-contribution-engineer
```

Or manually — copy this folder to any skills-compatible agent's skill directory:

| Scope | Path |
|-------|------|
| project (any agent) | `<repo>/.agents/skills/oss-contribution-engineer/` |
| user (any agent) | `~/.agents/skills/oss-contribution-engineer/` |
| Claude Code | `~/.claude/skills/oss-contribution-engineer/` |

### First run

```bash
python3 <SKILL_DIR>/scripts/envcheck.py
```

Checks Python ≥3.10, git, gh CLI (critical) and optional LSP backends
(Serena, gopls, typescript-language-server). The skill works without the
optional ones — they add symbol-level localization for non-Python repos.

Requires `python3` and `git` on PATH. Optional: authenticated `gh` CLI for
`--from-issue` and dedupe captures. See `references/ecosystem-guides.md`.

## Workflows

**"Find me a contribution"** — recon the repository, triage candidates against the
quality model, dedupe, and recommend one with a Candidate Report. Refuses contribution
farming (typo PRs, formatting sweeps, speculative refactors).

**"Investigate issue #123"** — READ_ONLY. Reproduce or disprove the reported behavior,
search for duplicates and linked PRs, and end with one conclusion:
CONFIRMED / UNCONFIRMED / INVALID / ALREADY_FIXED / DUPLICATE / DESIGN_QUESTION.
"Investigate" never authorizes edits.

**"Find a bug not already reported"** — proactive hunt: recent fix history, sibling
paths, cross-implementation parity, error-handling and lifecycle lenses, protocol
contracts. A candidate only counts after a reproducer and a dedupe search.

**"Fix this confirmed bug"** — the state machine runs: RED (regression test fails on
unmodified upstream, for the intended reason) → minimal PATCH → GREEN → neighbor +
package + static + build validation → Change Walkthrough + explain-back with the human
→ adversarial review (with a maintainer-perspective simulation) → PR_READY. Every
command's result is witnessed in an evidence manifest; nothing counts as passing unless
it ran.

**"Review my patch"** — adversarial review that tries to falsify the change: root cause,
concurrency, compatibility, test quality, scope creep, security, performance.

**"Prepare the PR but do not submit it"** — diff-scope audit against the patch plan,
validation report, maintainer-quality PR draft. Publishing anything (comment, issue,
branch, PR) requires explicit authorization, every time.

**"The maintainer asked for changes"** — review-response mode: classify each concern,
re-check the evidence, explain it to the contributor (concern → code context →
assessment → evidence → action), then either fix (head-bound evidence goes STALE and is
re-run, RED→GREEN again where the fix or test changed) or answer with a respectful
evidence-backed defense — never automatic agreement. Fixes go up as new commits;
readiness for re-review is signaled explicitly (re-request / PTAL). Each revision
carries a summary so reviewers never reconstruct the discussion by hand.

**"What happened to my PR?"** — the lifecycle is classified from captured PR state, not
self-report: `upstream_state.py` turns captured PR/reviews/timeline JSON into one of
eight outcomes — MERGED (the only success), CLOSED_NOT_MERGED, SUPERSEDED, WITHDRAWN,
DROPPED_OR_STALE, and in-flight WAITING_FOR_REVIEW / CHANGES_REQUESTED /
READY_FOR_REREVIEW. "PR opened" is not success, and `closed=true` is never reported as
a merge.

**Large repositories**: context is acquired, never bulk-loaded — workflow-aware
retrieval routing (lexical / symbol / test-relations / history / lightweight
structural PageRank over the import/test file graph / bounded graph expansion,
fused per workflow) feeds a no-regret packer that lets structural candidates fill
only the slots direct evidence leaves open. Two external intelligence backends plug
into the same router with per-candidate provenance: an `AOCI_RUNTIME` client that
consumes a real AOCI MCP runtime receipt (whole-index lifecycle, attestation,
identity-drift gating, explicit fallback otherwise) and a symbol backend
(`python-ast` first; Serena/LSP adapter when configured). Every packed span carries
provenance and a digest; no backend is source truth — current source remains
authoritative; routing regret is measured, and an extra signal is rejected when it
makes the pack worse.

## The state machine

```
DISCOVER → RECON → CANDIDATE → DEDUPLICATE → PROVE → RED → PATCH → GREEN
        → REGRESSION → CONTRIBUTOR_UNDERSTANDING → REVIEW → PR_READY
        → IN_REVIEW ⇄ PATCH …
        → terminal: MERGED | CLOSED_NOT_MERGED | SUPERSEDED | WITHDRAWN | DROPPED_OR_STALE
        in-flight: WAITING_FOR_REVIEW | CHANGES_REQUESTED | READY_FOR_REREVIEW
```

Each transition has entry/exit gates (see `SKILL.md`). A gate failure is a successful
outcome of the skill: INVALID, ALREADY_FIXED, DUPLICATE, UNCONFIRMED, DESIGN_QUESTION,
TOO_LARGE — each is a conclusion with evidence, not a failure to produce a patch.

## Development history

Experiment ledgers (V3–V12), benchmark runs, blind validations, and design-review
records live in the private companion repo:
[HongMing-Huang/oss-contribution-engineer-dev](https://github.com/HongMing-Huang/oss-contribution-engineer-dev)

## Project maturity (read this before any version number)

Version numbers (V6, V7, V8, …) are **experimental iteration labels**, not maturity.
Maturity is tracked on this ladder and the project currently sits at **EXPERIMENTAL**:

    RESEARCH → EXPERIMENTAL → VALIDATED_ON_SAMPLE → REPEATEDLY_VALIDATED
             → REAL-WORLD_TRIAL → USABLE

V8 ran the pipeline against real repositories and frozen tasks with competent
baselines and ablations; the results (including negative ones) live in
`the companion dev repo (link above)`. Nothing in this README is
a claim of usability, production-readiness, or feature-completeness.

## Runtime and capability status

The state machine is no longer prose: `scripts/contribution_session.py` is the
executable spine. It composes the existing scripts, persists one session record
(`.oss-contrib-evidence/session.json`), and **refuses illegal transitions with a
non-zero exit** — gates read only machine artifacts (goal contract, evidence
manifest, captured PR JSON), never markdown reports. Stale head-bound evidence
mechanically blocks advancement; `budget_governor.py govern` runs a bounded
pack→audit→prune→repack→ACCEPT/BLOCKED loop.

Every capability claim is classified in [`CAPABILITIES.json`](CAPABILITIES.json)
as ENFORCED, IMPLEMENTED, ADVISORY, EXPERIMENTAL, or UNIMPLEMENTED — this README
derives its claims from that ledger, and **every ENFORCED entry cites automated
tests** (`tests/<file>.py#<test-id>`); a validation test fails the suite if an
ENFORCED claim loses its test evidence. Notably: the state machine, permissions,
evidence witnessing (typed), stale-blocking, RED↔GREEN regression identity,
structured-artifact gates, and budget governing are ENFORCED; duplicate-work
checking and the security stop are ADVISORY (they guide, they
cannot mechanically prove); AOCI integration is FILE_COMPATIBILITY only
(runtime/MCP integration is UNIMPLEMENTED); call/reference/inheritance graphs are
UNIMPLEMENTED (imports + source↔test relations + PageRank is what exists);
embeddings are deliberately UNAVAILABLE.

## Layout

- `SKILL.md` — philosophy, hard rules, permission model, modes, gates, workflows
- `references/` — methodology per mode (recon, triage, hunting, proof, testing,
  patch design, review, review response, etiquette, AI policy, doctrine, portability)
- `scripts/` — deterministic collectors: `repo_audit.py`, `contribution_rules_scan.py`,
  `duplicate_work_scan.py` (parse-only: prints capture commands, aggregates captured
  JSON), `diff_scope_check.py`, `evidence_manifest.py` (witnessed execution;
  `--head-bound` ties PASS to the HEAD it ran on), `validation_report.py` (marks
  head-bound evidence STALE after HEAD moves), `upstream_state.py` (parse-only: prints
  PR capture commands, classifies the captured state into the 8 lifecycle outcomes)
- `assets/` — report templates (recon profile, candidate, investigation, issue draft,
  patch plan, validation, change walkthrough, review, PR draft, review response)

Scripts are stdlib-only Python 3, never touch the network, and report what is on disk
or in provided capture files — they collect; the agent and the human judge.
