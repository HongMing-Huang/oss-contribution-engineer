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

Copy the folder to any skills-compatible agent's skill directory:

| Scope | Path |
|-------|------|
| project (any agent) | `<repo>/.agents/skills/oss-contribution-engineer/` |
| user (any agent) | `~/.agents/skills/oss-contribution-engineer/` |
| Claude Code | `~/.claude/skills/oss-contribution-engineer/` |

Requires `python3` and `git` on PATH. Optional: an authenticated `gh` CLI or a platform
GitHub tool for issue/PR lookups. See `references/ecosystem-guides.md` for per-agent notes.

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
re-check the evidence, explain it to the contributor, then either fix (stale validation
re-run, RED→GREEN again) or answer with a respectful evidence-backed defense — never
automatic agreement. Each revision carries a summary so reviewers never reconstruct the
discussion by hand.

## The state machine

```
DISCOVER → RECON → CANDIDATE → DEDUPLICATE → PROVE → RED → PATCH → GREEN
        → REGRESSION → CONTRIBUTOR_UNDERSTANDING → REVIEW → PR_READY
        → IN_REVIEW → UPSTREAM_RESOLVED      (after publication, REMOTE_WRITE)
                    ↘ IN_REVIEW → PATCH …    (review change re-enters at PATCH)
```

Each transition has entry/exit gates (see `SKILL.md`). A gate failure is a successful
outcome of the skill: INVALID, ALREADY_FIXED, DUPLICATE, UNCONFIRMED, DESIGN_QUESTION,
TOO_LARGE — each is a conclusion with evidence, not a failure to produce a patch.

## Layout

- `SKILL.md` — philosophy, hard rules, permission model, modes, gates, workflows
- `references/` — methodology per mode (recon, triage, hunting, proof, testing,
  patch design, review, review response, etiquette, AI policy, doctrine, portability)
- `scripts/` — deterministic collectors: `repo_audit.py`, `contribution_rules_scan.py`,
  `duplicate_work_scan.py` (parse-only: prints capture commands, aggregates captured
  JSON), `diff_scope_check.py`, `evidence_manifest.py` (witnessed execution),
  `validation_report.py`
- `assets/` — report templates (recon profile, candidate, investigation, issue draft,
  patch plan, validation, change walkthrough, review, PR draft, review response)

Scripts are stdlib-only Python 3, never touch the network, and report what is on disk
or in provided capture files — they collect; the agent and the human judge.
