# Design — `oss-contribution-engineer` (deliverables B–F)

Companion to [`research-notes.md`](research-notes.md).

## B. Architecture proposal

**Format**: vendor-neutral Agent Skills standard (agentskills.io). Frontmatter uses only
spec fields — `name`, `description`, `license`, `compatibility`, `metadata` — so the folder
runs unchanged in Claude Code, Codex, Cursor, Gemini CLI, Copilot, and any other
compatible agent. Vendor-specific advice (install paths, `allowed-tools`, invocation
syntax, AGENTS.md interplay) lives in `references/ecosystem-guides.md`, never in the core.

**Why this architecture fits the workflow:**

1. **Triggering** is description-driven, so the description front-loads the leading words
   ("contribute", "open-source", "issue", "bug hunt", "PR", "review my patch") and states
   the anti-trigger ("not for ordinary local app development") to prevent false triggers.
2. **Predictability** comes from a fixed 11-state machine with explicit entry/exit gates,
   not from model improvisation. The same process runs every time; only content varies.
3. **Progressive disclosure**: SKILL.md (target ≤350 lines) holds philosophy, hard rules,
   permission model, modes, gates, and workflow skeletons. Per-branch methodology
   (triage taxonomy, bug-hunting patterns, testing levels, review protocol…) sits in
   `references/*.md`, loaded only when a mode calls for it.
4. **Deterministic scripts** do collection and verification that must not depend on model
   diligence: repo audits, instruction-file scans, duplicate-work evidence (parse-only:
   prints `gh` capture commands, aggregates captured JSON — no network in scripts),
   diff-scope checks, witnessed command execution, and validation-report rendering.
   Scripts are stdlib-only Python 3 (portable), read-only except the evidence directory,
   and are explicitly *collectors* — they never claim semantic understanding.
5. **Anti-fabrication is structural**: validation results can only be produced by
   `evidence_manifest.py record` (which executes the command) or recorded explicitly as
   SKIPPED/UNAVAILABLE with a reason. The agent cannot "write in" a PASS.
6. **Local-rules precedence** is architectural: recon precedes any edit, and the
   Repository Contribution Profile (built from repo-local docs) overrides the generic
   workflow wherever they conflict.
7. **Authorization is a mode property**: Investigation modes are READ_ONLY by default;
   edits require WORKTREE_EDIT; anything remote requires REMOTE_WRITE granted explicitly
   in the current conversation. "Investigate" never upgrades permission.

**What was deliberately NOT built**: no auto-submit tooling, no "good first issue"
scraping wrapper, no numeric certainty scores, no network access in any script —
`duplicate_work_scan.py` is parse-only (prints capture commands, aggregates captured
JSON), so data provenance is explicit and works identically with `gh` or platform tools.

## C. Workflow & state machine

### Modes

| # | Mode | Purpose | Default permission | Loads |
|---|------|---------|--------------------|-------|
| 1 | Repository Recon | Build the Repository Contribution Profile | READ_ONLY | references/repository-recon.md |
| 2 | Issue Triage | Classify an issue as work / not-work | READ_ONLY | references/issue-triage.md |
| 3 | Bug Hunt | Proactively find a real, unreported bug | READ_ONLY | references/bug-hunting.md |
| 4 | Investigation Only | Explain a behavior; no changes, ever | READ_ONLY | references/proof-standard.md |
| 5 | Fix | RED→GREEN minimal patch | WORKTREE_EDIT | references/patch-design.md, testing-strategy.md |
| 6 | Adversarial Review | Falsify the patch | READ_ONLY | references/code-review.md |
| 7 | PR Preparation | Draft PR + validation evidence | WORKTREE_EDIT (local only) | assets/pull-request-template.md |
| 8 | Learning / Explain Architecture | Teach the subsystem | READ_ONLY | — |

### State machine (Fix path; gates apply to every transition)

```
DISCOVER → RECON → CANDIDATE → DEDUPLICATE → PROVE → RED → PATCH → GREEN
        → REGRESSION → REVIEW → PR_READY
```

| Transition | Exit criteria (gate) |
|------------|----------------------|
| DISCOVER → RECON | a target repository is chosen and known to the user |
| RECON → CANDIDATE | Repository Contribution Profile exists; local rules precedence acknowledged; area identified |
| CANDIDATE → DEDUPLICATE | concrete suspected behavior; affected subsystem; a source for expected behavior |
| DEDUPLICATE → PROVE | issue search, PR search, comments/assignment inspection, recent-commit inspection all recorded; status class assigned |
| PROVE → RED | reproducer runs and shows expected vs actual; Evidence Record complete; else → UNCONFIRMED stop |
| RED → PATCH | regression test fails on unmodified upstream code *for the intended reason*; RED output stored |
| PATCH → GREEN | smallest reasonable implementation; no unrelated refactor; production change matches PATCH PLAN |
| GREEN → REGRESSION | focused regression test passes; GREEN output stored |
| REGRESSION → REVIEW | neighbor + package tests, lint/format/typecheck, build run; results recorded incl. SKIPPED/UNAVAILABLE |
| REVIEW → PR_READY | adversarial review done; no unresolved correctness issues; testing evidence recorded; untested areas recorded; Contributor Understanding Check prepared |

**Rules**: a gate failure is a *successful* outcome of the skill (ALREADY_FIXED,
INVALID, DUPLICATE, UNCONFIRMED, DESIGN_QUESTION are terminal successes). The agent must
not skip gates because it is confident. Strategy A (existing issue) enters at CANDIDATE
after triage; Strategy B (bug hunt) enters at RECON and runs the hunt before CANDIDATE.

## D. File layout

```
oss-contribution-engineer/
├── SKILL.md                     # ≤350 lines: philosophy, hard rules, permissions,
│                                #   modes, gates, workflows, indexes
├── README.md                    # philosophy + install + 6 documented workflows
├── references/
│   ├── contribution-doctrine.md # kernel/git/LLVM/Google principles + links
│   ├── repository-recon.md      # recon checklist + Contribution Profile format
│   ├── issue-triage.md          # inspection checklist + classification + quality model
│   ├── bug-hunting.md           # parity/sibling/error/lifecycle/protocol/tests/fixes
│   ├── proof-standard.md        # Evidence Record + Proof Gate + UNCONFIRMED
│   ├── testing-strategy.md      # levels 0–8 + RED→GREEN + test-quality review
│   ├── patch-design.md          # PATCH PLAN + diff budget + anti-overengineering
│   ├── code-review.md           # adversarial review protocol + report
│   ├── maintainer-etiquette.md  # claiming, pinging, comment discipline
│   ├── ai-assisted-development.md # ownership, disclosure, DCO, authorization
│   └── ecosystem-guides.md      # per-agent discovery + portability limits
├── scripts/
│   ├── repo_audit.py            # deterministic environment/culture detection
│   ├── contribution_rules_scan.py # locate + excerpt repo-local instructions
│   ├── duplicate_work_scan.py   # gh-based issue/PR cross-reference collection
│   ├── diff_scope_check.py      # diff vs intended scope, drift + budget flags
│   ├── evidence_manifest.py     # witnessed command execution → JSONL manifest
│   └── validation_report.py     # manifest → markdown Validation Report
└── assets/
    ├── repository-recon-report.md
    ├── candidate-report.md
    ├── investigation-report.md
    ├── implementation-plan.md
    ├── validation-report.md
    ├── review-report.md
    └── pull-request-template.md
```

Supporting deliverables (outside the skill folder, in `oss-contribution-engineer-dev/`):
research notes, this design, validation results, `eval/scenarios/` (10 scenarios), the
evaluation report, and example runs against real repositories.

## E. Implementation plan

1. Write SKILL.md (hard rules → permissions → modes → gates → workflows → indexes).
2. Write the 11 references; each ≤ ~150 lines, paraphrased principles with source links.
3. Write 6 scripts: shared conventions (argparse, `--json`, exit codes, no network except
   documented `gh` subprocess), then per-script logic per D.
4. Write 7 assets (spec lists 6 templates; PR draft template included as 7th — the
   directory listing in the original brief showed 6 asset files; the PR template is
   deliverable-critical so it joins the assets).
5. Validate: `py_compile` all scripts; run each script for real (recon on two real clones,
   duplicate scan via `gh` on a live issue, scope check on a scratch repo with injected
   drift, evidence/validation round-trip).
6. Example runs (2 real repos) incl. one intentional no-patch outcome.
7. Evaluation suite + report.

## F. Evaluation plan

Ten scenarios, each as a graded rubric in `eval/scenarios/` (setup, prompt, expected
behavior, pass/fail checks):

1. Already-claimed issue → skill detects linked PR, advises against competing.
2. Invalid bug hypothesis → reproducer disproves it; workflow stops before patch.
3. Genuine small bug → RED regression → minimal fix → GREEN → validation evidence.
4. Feature needing maintainer discussion → stops before implementation; drafts design
   question.
5. Repository with nested CONTRIBUTING/AGENTS instructions → local instructions
   discovered and followed (script-supported).
6. Tests cannot run → reports UNVERIFIED/UNAVAILABLE, never PASS.
7. Overengineering attempt (patch drifts to five adjacent problems) → scope audit flags
   and rejects the expansion.
8. Security issue → public workflow stops; SECURITY policy path used.
9. Existing bug but stale branch → skill re-tests current upstream first (ALREADY_FIXED).
10. Proactive bug discovery → asymmetry → dedupe → reproducer → only then patch.

Measured dimensions: false-positive bug rate, duplicate-work avoidance, unnecessary diff
size, fabricated-validation claims (must be zero; structurally blocked by the manifest),
test quality, instruction compliance, scope control. Scenario 1 and 10 are additionally
exercised for real against live repositories in the example runs; script-supported
mechanics (5, 6, 7 evidence paths) are executed directly during validation.
