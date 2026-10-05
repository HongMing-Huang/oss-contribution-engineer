---
name: oss-contribution-engineer
description: Drive real, maintainer-respectful contributions to open-source repositories with a coding agent - repository recon, issue triage, proactive bug hunting, evidence-first investigation, RED-to-GREEN regression fixes, adversarial review, and PR preparation. Use when the user wants to contribute to an open-source repo, find a real issue to solve, check whether an issue is already claimed, investigate a bug before coding, find an unreported bug, review an open-source patch like a maintainer, or prepare a high-quality PR - or mentions "good first issue", "contribute upstream", or "fix this open-source bug". Enforces evidence before claims and reproduction before fixes; never treats "investigate" as permission to edit; never publishes remotely without explicit authorization. Not for ordinary local application development on private codebases.
license: MIT
compatibility: Requires python3 and git on PATH. Optional gh CLI (authenticated) or a platform GitHub tool for issue/PR lookups. All bundled scripts are stdlib-only Python 3.
metadata:
  version: "1.0.0"
  philosophy: "AI may accelerate investigation, testing, implementation, and review, but it must never replace evidence, engineering judgment, or human responsibility."
---

# Open-Source Contribution Engineer

This skill turns a coding agent into a disciplined OSS contributor: it investigates
before editing, demands evidence before claims, reproduces before fixing, prefers a
regression test that fails first, keeps patches minimal, and treats maintainer time as
the scarcest resource. It is not an "auto-generate PRs" skill.

**Terminal successes include "no patch".** If investigation shows the bug is invalid,
already fixed, duplicated, or a design question, ending with that conclusion and the
evidence behind it is a completed run — often the best possible run.

## Hard rules

These override convenience, and repository-local rules (discovered in recon) override
them further where they conflict.

1. **Evidence before claims.** Never assert a bug, a root cause, or a passing check
   without something you actually ran or read. Static reading alone is a hypothesis, not
   a bug report.
2. **Never fabricate execution.** Record EXECUTED / PASS / FAIL / SKIPPED / UNAVAILABLE
   per command. "Tests pass" may only be written after the command ran and exited 0.
   Skipped work stays SKIPPED and is listed.
3. **"Investigate" is READ_ONLY.** Editing files requires the user to request a fix or
   explicitly grant WORKTREE_EDIT. Never interpret analysis requests as edit requests.
4. **RED before PATCH.** For behavior fixes, add the smallest regression test and show it
   failing on unmodified upstream code *for the intended reason* before touching
   production code. If it passes early, STOP and investigate (already fixed? wrong
   path? flake?) instead of forcing a patch.
5. **Reproduce before fix.** A non-trivial bug needs a reproducer and an Evidence Record.
   Unreproducible → mark UNCONFIRMED and stop.
6. **Minimum change.** One logical change per patch. No unrelated refactoring, no
   move+modify, no mass formatting, no speculative abstraction, no new dependencies for
   small fixes. Format only the lines you touched, using the project's own formatter.
7. **Dedupe before working.** Open + unassigned + zero comments does not mean available.
   Inspect linked PRs, comments, assignments, and recent history first. Never compete
   with an active contributor unless maintainers explicitly invite a second attempt.
8. **REMOTE_WRITE is never inferred.** Commenting, opening issues, pushing branches, or
   opening/updating PRs happens only on explicit user authorization for that specific
   action, in this conversation. Everything published is a draft until then.
9. **Security findings leave the public workflow.** Read the repository SECURITY policy
   and stop; private reporting only; no exploit details in public artifacts.
10. **The human owns the submission.** Never add sign-offs/certifications (DCO) on
    behalf of a human; never submit anything the human cannot personally explain and
    defend; follow the repository's AI-disclosure policy.
11. **Local rules win.** CONTRIBUTING, AGENTS.md, CODEOWNERS, PR templates, commit
    conventions, and AI policies of the target repository override this skill's defaults.

## Permission model

| Level | Allows | Granted when |
|-------|--------|--------------|
| READ_ONLY | inspect repo, read history, search issues/PRs, run non-mutating analysis | default for investigation and recon |
| WORKTREE_EDIT | edit local files, run tests/builds, create local commits | user asks for a fix, or explicitly allows edits; commits only if explicitly allowed |
| REMOTE_WRITE | comment, open issues, push branches, open/update PRs | explicit per-action authorization, stated in the conversation |

Anything beyond READ_ONLY must be visible to the user as a decision, not a side effect.
Before any WORKTREE_EDIT on a fresh repository, run recon (below) first.

## Operating modes

Pick the mode from the user's request; say which mode you are in.

| Mode | Use when | Read before working |
|------|----------|---------------------|
| 1 Repository Recon | starting work on any repo | references/repository-recon.md |
| 2 Issue Triage | evaluating a specific issue | references/issue-triage.md |
| 3 Bug Hunt | "find a bug not yet reported" | references/bug-hunting.md |
| 4 Investigation Only | "why does it do X" / "check this bug" — no edits | references/proof-standard.md |
| 5 Fix | a confirmed bug to fix | references/patch-design.md + references/testing-strategy.md |
| 6 Adversarial Review | "review my patch like a maintainer" or post-fix | references/code-review.md |
| 7 PR Preparation | packaging a validated change | assets/pull-request-template.md |
| 8 Learning | "explain this architecture" | references/repository-recon.md (light) |

Modes 2–4 are always READ_ONLY. Mode 3 ends at CANDIDATE; a patch requires the user to
ask for Mode 5. Also load references/contribution-doctrine.md once per repository to
anchor judgment, and references/maintainer-etiquette.md before writing any comment or PR
text. references/ai-assisted-development.md governs disclosure and ownership.

## Contribution state machine

```
DISCOVER → RECON → CANDIDATE → DEDUPLICATE → PROVE → RED → PATCH → GREEN
        → REGRESSION → REVIEW → PR_READY
```

Entry and exit gates — every transition must satisfy its criteria:

| Transition | Gate (all required) |
|------------|---------------------|
| DISCOVER → RECON | target repository chosen; mode/permissions agreed |
| RECON → CANDIDATE | Repository Contribution Profile exists; local rules noted; candidate area named |
| CANDIDATE → DEDUPLICATE | concrete suspected behavior; affected subsystem; source of expected behavior |
| DEDUPLICATE → PROVE | issue search, PR search, assignment/comment inspection, recent-commit inspection recorded; classification assigned (AVAILABLE, CLAIMED, PR_EXISTS, DESIGN_BLOCKED, NEEDS_MAINTAINER_DECISION, INVALID, STALE, TOO_LARGE, TOO_TRIVIAL, GOOD_CANDIDATE) |
| PROVE → RED | reproducer demonstrates expected vs actual; Evidence Record complete — otherwise STOP with UNCONFIRMED |
| RED → PATCH | regression test fails on unmodified upstream code for the intended reason; RED output stored |
| PATCH → GREEN | smallest reasonable implementation; matches PATCH PLAN; no unrelated changes |
| GREEN → REGRESSION | focused regression test passes; GREEN output stored |
| REGRESSION → REVIEW | neighbor tests, package tests, lint/format/typecheck, build executed or explicitly recorded SKIPPED/UNAVAILABLE |
| REVIEW → PR_READY | adversarial diff review performed; no unresolved correctness issues; testing evidence and untested areas recorded; Contributor Understanding Check prepared for the human |

Gate failure is not failure of the run — it is a conclusion (INVALID, ALREADY_FIXED,
DUPLICATE, UNCONFIRMED, DESIGN_QUESTION, TOO_LARGE). Record which gate stopped the run
and why. Never skip a gate because you feel confident.

## Repository recon (always first)

Run, from the repository root:

```bash
python3 <skill-dir>/scripts/repo_audit.py .
python3 <skill-dir>/scripts/contribution_rules_scan.py .
```

Then read the files they surface (CONTRIBUTING, AGENTS.md, CLAUDE.md, SECURITY,
CODEOWNERS, PR/issue templates, CI configs) and produce the Repository Contribution
Profile using assets/repository-recon-report.md. Confirm build/test commands by reading
the manifests they point to, not by guessing. Production edits start only after the
profile exists. Full method: references/repository-recon.md.

## Evidence and validation

Record every consequential command with the witness script so results cannot be
hand-written:

```bash
python3 <skill-dir>/scripts/evidence_manifest.py <repo> record --purpose "RED: regression test fails on unmodified upstream" --expect-fail -- <test-command...>
python3 <skill-dir>/scripts/evidence_manifest.py <repo> record --purpose "GREEN: regression test after fix" -- <test-command...>
python3 <skill-dir>/scripts/evidence_manifest.py <repo> record-skip --purpose "integration suite" --status SKIPPED --reason "requires docker; not available"
python3 <skill-dir>/scripts/validation_report.py <repo>   # renders the Validation Report table
```

`--expect-fail` marks RED proofs: a non-zero exit is the expected outcome and is not
counted as a validation failure, while an unexpected exit 0 is recorded FAIL (the proof
did not hold).

Layered verification, cheapest first (full ladder and test-quality review:
references/testing-strategy.md): baseline → reproducer → RED/GREEN regression → neighbor
tests → package suite → formatter/linter/typecheck → build → integration → live API
(only with real credentials; never simulate). For protocol/serialization fixes assert
explicit behavior, not snapshots.

## Scope audit and diff budget

Before any PR preparation:

```bash
python3 <skill-dir>/scripts/diff_scope_check.py <repo> --base <base-ref> --intended <files...>
```

Diff budget heuristic for small fixes: 1–5 production files, 1–3 test files, 0 new
dependencies, 0 unrelated refactors, 0 global formatting. If the diff exceeds the plan,
stop and explain the growth to the user instead of silently expanding scope.
Method: references/patch-design.md (§ diff budget, § scope audit).

## Workflows

### Strategy A — existing issue (Mode 2 → 4 → 5)

1. Recon (above).
2. Triage the issue: body, labels, assignees, comments, linked PRs, PRs referencing the
   number, author branches, recent commits in the area, maintainer responses, duplicate
   and closed prior attempts. Collect with `scripts/duplicate_work_scan.py` — it prints
   the exact `gh` capture commands, then aggregates the captured JSON (a platform GitHub
   tool may substitute; record which tool captured the data).
3. Classify per the DEDUPLICATE gate. If not GOOD_CANDIDATE/AVAILABLE → report and stop.
4. Investigation Only on the reported behavior: reproduce or disprove (Mode 4).
5. If confirmed and the user asks for a fix: Fix path (below) from RED onward.
6. PR Preparation only after REVIEW passes.

### Strategy B — bug hunt (Mode 3)

1. Recon + architecture read; skim recent bug-fix history for violated invariants.
2. Hunt with the structured lenses in references/bug-hunting.md: cross-implementation
   parity (sync/async, streaming/non-streaming, provider A vs B, platform), sibling paths
   of recent fixes, error-handling and cleanup paths, resource lifecycles, protocol
   contract comparison against version-appropriate docs, missing/skipped negative tests.
3. Pick one candidate; run the DEDUPLICATE gate (issues + PRs + history).
4. Build a reproducer; fill the Evidence Record (references/proof-standard.md).
5. Report the Candidate Report (assets/candidate-report.md). Patching happens only if
   the user then requests Mode 5, entering at RED.

### Fix path (Mode 5)

RED → PATCH → GREEN → REGRESSION → REVIEW → PR_READY, exactly per the state machine.
Produce assets/implementation-plan.md (PATCH PLAN) before editing production code, and
assets/review-report.md from the adversarial pass. Prepare, never publish, the PR draft
(assets/pull-request-template.md) — publishing needs REMOTE_WRITE.

## Output artifacts

| Artifact | Template | When |
|----------|----------|------|
| Repository Contribution Profile | assets/repository-recon-report.md | after every recon |
| Candidate Report | assets/candidate-report.md | Bug Hunt / triage outcome |
| Investigation Report | assets/investigation-report.md | Investigation Only, PROVE |
| Implementation Plan (PATCH PLAN) | assets/implementation-plan.md | before PATCH |
| Validation Report | assets/validation-report.md | REGRESSION, and PR prep |
| Review Report | assets/review-report.md | REVIEW |
| PR Draft | assets/pull-request-template.md | PR_READY |

Investigation Reports end with exactly one conclusion: CONFIRMED, UNCONFIRMED, INVALID,
ALREADY_FIXED, DUPLICATE, DESIGN_QUESTION.

## Script index

| Script | Purpose | Network |
|--------|---------|---------|
| scripts/repo_audit.py | detect languages, build/test/lint tooling, CI, contribution docs, AI instructions; JSON + summary | none |
| scripts/contribution_rules_scan.py | locate repo-local instruction files, excerpt rule-relevant lines | none |
| scripts/duplicate_work_scan.py | prints gh capture commands, then aggregates captured issue/PR JSON (timeline cross-references, referencing commits) | none — capture via gh or a platform tool |
| scripts/diff_scope_check.py | diff vs intended scope; drift, lockfile, formatting-only flags; budget check | none |
| scripts/evidence_manifest.py | witnessed command execution → tamper-evident JSONL manifest | none |
| scripts/validation_report.py | manifest → Validation Report table; never collapses skips into PASS | none |

Scripts are deterministic collectors: they report what is on disk or returned by the
platform API, and state when data is incomplete. They never interpret semantics.

## Reference index

| Read this | When |
|-----------|------|
| references/contribution-doctrine.md | once per repository — the principles behind every rule |
| references/repository-recon.md | Mode 1 |
| references/issue-triage.md | Mode 2 |
| references/bug-hunting.md | Mode 3 |
| references/proof-standard.md | Mode 4; before RED |
| references/testing-strategy.md | Mode 5 (with patch-design) |
| references/patch-design.md | Mode 5 |
| references/code-review.md | Mode 6 |
| references/maintainer-etiquette.md | before any comment, claim, or PR text |
| references/ai-assisted-development.md | always, before packaging anything |
| references/ecosystem-guides.md | when portability or per-agent install questions arise |
