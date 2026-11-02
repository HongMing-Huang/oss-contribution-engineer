# Gap Analysis — Goal 2: Contributor Understanding & Upstream Communication

Companion to [`design.md`](design.md) (v1 architecture record — unchanged by this goal)
and [`validation-results.md`](validation-results.md) (v1 validation record — unchanged).
All dates: 2026-10-05. This goal is incremental by mandate: no architecture redesign, no
rebuild of cognition/evidence/permission/RED→GREEN/contribution systems.

## Principle

> AI assists the contribution; the human must understand and own it.

## Fresh research basis (fetched 2026-10-05, authoritative sources)

- Linux kernel, `Documentation/process/submitting-patches.rst`: *"Describe your problem.
  Whether your patch is a one-line bug fix or 5000 lines of a new feature, there must be
  an underlying problem"*; *"Describe user-visible impact"*; *"Separate each logical
  change into a separate patch"*; *"You must respond to those comments; ignoring
  reviewers is a good way to get ignored in return"*; *"Describe the expected downsides
  of your optimization so that the reviewer can weigh costs against benefits."*
- Linux kernel, `Documentation/process/generated-content.rst`: *"Ensure that you
  understand your entire submission and are prepared to respond to review comments"*;
  *"You are expected to understand and to be able to defend everything you submit. If
  you are unable to do so, then do not submit the resulting changes"*; maintainers may
  *"ask the submitter to explain in more detail … so that the maintainer can be assured
  that the submitter fully understands how the code works."*
- Git, `Documentation/SubmittingPatches`: *"The goal of your log message is to convey
  the _why_ behind your change to help future developers"*; body must explain the
  problem, justify the way the change solves it, and note discarded alternatives;
  *"You are expected to respond to them with 'Reply-All' … instead of letting an updated
  patch series be your only response"*; *"Defend your design decisions on the list
  first"*; later iterations *"give a summary of changes since the previous rounds"*;
  AI rule: reject content *"that senders don't understand or cannot explain."*

## Gap table (goal requirement → current state → gap → minimal change)

| # | Requirement | Current state (v1) | Gap | Minimal change |
|---|-------------|--------------------|-----|----------------|
| 1 | Contributor Understanding stage between REGRESSION and REVIEW | Only a REVIEW→PR_READY gate clause "Contributor Understanding Check prepared"; 10 questions buried in ai-assisted-development.md | No dedicated state, no walkthrough, check happens too late and has no teach-first loop | New state `CONTRIBUTOR_UNDERSTANDING` with two gates (REGRESSION→CU, CU→REVIEW); new section in SKILL.md |
| 2 | Change Walkthrough artifact | absent | — | New `assets/change-walkthrough.md` (Problem/Before/Root Cause/Relevant Data/Changed Code/Why This Fix/After/Regression Proof/Risk/Non-goals) |
| 3 | Explain-Back check | 10-question list exists, framed as "prepared" | Not a teaching loop; no human-confirmation rule | Explain-back protocol in SKILL.md § Contributor understanding; ai-assisted-development.md rewritten to the 5 explain-back questions + "never claim understanding without human confirmation" |
| 4 | Linux/Git doctrine integration | 10 principles with sources | Missing: problem-before-implementation, review-is-part-of-development, future-maintainer comprehension, automated-checks-≠-human-judgment; sources stale | Doctrine refreshed with 2026-10-05 fetches; §5/§6/§7 extended; new §11 "The problem comes first" and §12 "Understanding is part of the submission" |
| 5 | Issue preparation | bug-hunting.md says "draft concise issue text"; no artifact, no structure, no honesty framing | No template; speculative-issue risk unaddressed structurally | New `assets/issue-draft.md` (Problem/Reproduction/Expected/Actual/Impact/Evidence/Likely scope/Open questions) + UNCONFIRMED INVESTIGATION framing + bug-hunting.md pointer |
| 6 | PR preparation | Template decent (Problem/Root Cause/Change/Tests/Compat/Limitations) | Missing: Why this approach, Non-goals, Related issue; no anti-AI-changelog rule | Template restructured to the goal's 9 sections + "no Implemented X / Updated Y without why" rule |
| 7 | Review-response support | **absent entirely** — workflow ended at PR_READY | No loop, no concern taxonomy, no modify-vs-justify decision | New reference `references/review-response.md` + states `IN_REVIEW`/`UPSTREAM_RESOLVED` + Mode 9 |
| 8 | Review iteration summary | absent | — | Part of review-response reference + `assets/review-response.md` worksheet (concern → changed → evidence → unchanged-and-why) |
| 9 | Progress communication | absent | Status output unstructured | SKILL.md § Progress communication: FOUND/EVIDENCE/IMPACT/NEXT; PATCH INTENT/WHY/EXPECTED FILES/NON-GOALS/VALIDATION PLAN; RESULT/PROOF/WHAT CHANGED/WHAT DID NOT CHANGE/REMAINING RISK; REVIEWER CONCERN/INTERPRETATION/EVIDENCE/ACTION |
| 10 | Maintainer review simulation | code-review.md has the falsification checklist | No maintainer-perspective question pass tied to the actual patch | code-review.md § Maintainer-perspective simulation (8 patch-specific questions), folded into REVIEW→PR_READY gate |
| 11 | Preserve architecture | 11-state machine, 6 scripts, evidence manifest, gates | Risk of duplication | Reuse everything: scripts untouched, gates extended in place, artifacts added not duplicated |
| 12 | Eval cases A–E | 10 scenarios end at PR_READY understanding | None cover understanding gating, communication, review loop | New `eval/scenarios/eval-11..15-*.md` (A–E), eval README + evaluation report updated |

## Design deltas (the complete list — nothing else changes)

**States.** `REGRESSION → CONTRIBUTOR_UNDERSTANDING → REVIEW → PR_READY` replaces the
direct `REGRESSION → REVIEW`. After publication (REMOTE_WRITE) the machine continues:
`PR_READY → IN_REVIEW → UPSTREAM_RESOLVED`, with `IN_REVIEW → PATCH` when a review
comment requires a code change (re-enters RED→GREEN under stale-validation rules).

**Gates added/extended.**
- REGRESSION → CONTRIBUTOR_UNDERSTANDING: Change Walkthrough drafted from the real diff,
  current source (file:line), and the actual tests; explain-back questions prepared;
  evidence not stale.
- CONTRIBUTOR_UNDERSTANDING → REVIEW: the human confirmed they can explain the change —
  or explicitly deferred. The agent never records understanding on the human's behalf.
- REVIEW → PR_READY: existing criteria + maintainer-perspective simulation answered from
  the actual patch.
- PR_READY → IN_REVIEW: published with explicit REMOTE_WRITE (draft remains non-publish).
- IN_REVIEW → PATCH / UPSTREAM_RESOLVED: per review-response reference.

**New artifacts (3).** `assets/change-walkthrough.md`, `assets/issue-draft.md`,
`assets/review-response.md`.

**New reference (1).** `references/review-response.md`. Existing references get
targeted extensions only: doctrine (principles), code-review (simulation section),
maintainer-etiquette (responding-to-review section), ai-assisted-development
(explain-back rewrite), testing-strategy (stale-validation section), bug-hunting
(issue-draft pointer).

**Modes.** Mode 9 (Review Response) added. Modes 1–8 keep their permissions; Mode 9 is
READ_ONLY while analyzing review, WORKTREE_EDIT only when a decided change re-enters the
patch path, REMOTE_WRITE only for posting the response.

**Scripts.** Zero changes. The evidence manifest already covers re-runs after
review-driven changes; `validation_report.py` already renders true statuses.

**Stale-evidence rule (new, in testing-strategy.md).** Any production/test change after
GREEN (review fix, rebase, rework) invalidates evidence that depends on the changed
code: affected levels re-run and re-recorded (RED→GREEN if the fix or its test changed),
validation report regenerated, walkthrough refreshed. Superseded evidence is never cited
as current.

## Deliberately NOT built

- No separate "understanding workflow" — it is a state in the existing machine.
- No new scripts, no scoring/quiz tooling — explain-back is conversational, not an exam.
- No second philosophy document — doctrine grows by ~15 lines with sources.
- No automatic review-reply tooling — responses are drafts; posting is REMOTE_WRITE.
- No `PR_READY`-bypass: understanding deferral is recorded, never silently skipped.
