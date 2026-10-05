# Issue Triage

An issue is a *candidate*, never a commitment. The output of triage is a Candidate Report
(assets/candidate-report.md) with exactly one classification.

## Inspection checklist (all of it, before recommending)

Collect the mechanical part with `scripts/duplicate_work_scan.py <repo> <issue>`
(`gh`-based; a platform GitHub tool may substitute — record which tool was used):

- [ ] issue body: actual reported behavior vs feature request vs question
- [ ] labels (good-first-issue ≠ available; needs-reproduction means it may be invalid)
- [ ] assignees — anyone assigned, including the reporter?
- [ ] comments — maintainer guidance, design disagreements, "someone is on it"
- [ ] linked PRs and cross-references (timeline API)
- [ ] open PRs and branches referencing the issue number (search + commit search)
- [ ] recent commits touching the affected area (fixed quietly? behavior changed?)
- [ ] duplicate issues, including closed ones with linked fixes
- [ ] prior PRs that attempted this and why they stalled or were rejected
- [ ] who reviews this area (CODEOWNERS / MAINTAINERS) and what they've said

## Classification

| Class | Meaning | Action |
|-------|---------|--------|
| AVAILABLE | confirmed unclaimed, no competing work | may propose working on it |
| CLAIMED | assigned, or a contributor has announced work | do not compete |
| PR_EXISTS | linked or referencing PR is open | do not compete; maybe review it |
| DESIGN_BLOCKED | solution needs a design decision | escalate question to maintainers |
| NEEDS_MAINTAINER_DECISION | maintainer input required | wait; do not implement |
| INVALID | not a bug / works as documented / unreproducible | report evidence, stop |
| STALE | long inactive, likely resolved or obsolete | verify against current code first |
| TOO_LARGE | exceeds diff budget for this stage | suggest decomposition with maintainers |
| TOO_TRIVIAL | typo-only / formatting / noise | do not submit (farming) |
| GOOD_CANDIDATE | AVAILABLE and passes the quality model | proceed to investigation |

**Never recommend competing with an active contributor** unless maintainers explicitly
invite another implementation. "Open and unassigned with zero comments" is the *start*
of the analysis, not its conclusion.

## Candidate quality model (qualitative, no fake scores)

Favor candidates with:

- real user-facing or developer-facing impact (kernel: explain user-visible effect)
- reproducibility on current upstream
- a clear, sourceable expected behavior
- small scope: 1–5 production files, 1–3 test files, no architecture redesign, no new
  dependency, no public API redesign
- a focused review surface and existing nearby tests to extend
- maintainer guidance present, or none needed

Penalize candidates that need: protocol knowledge the project hasn't documented,
special hardware/credentials, a rewrite, or a decision maintainers haven't made.

## Contribution farming — always refuse

Typo-only PRs, whitespace/mass formatting, generated docs noise, speculative refactors,
dependency bumps without project need, and "AI found 20 theoretical issues" lists without
reproductions. Kernel maintainers explicitly reject tool-generated slop, and Git's
SubmittingPatches warns against tree-wide cleanup patches. These PRs burn maintainer
time and damage the contributor's standing. If the user asks for one, explain why and
offer a real alternative instead.
