# Eval 4 — Feature needing maintainer discussion

**Status in this delivery: RUBRIC-ANALYZED (workflow trace).**
Trace basis: SKILL.md § hard rule 7 + modes; references/issue-triage.md (classification
DESIGN_BLOCKED / NEEDS_MAINTAINER_DECISION); references/maintainer-etiquette.md ("If
CONTRIBUTING requires discussing features first … stop before implementing"); the fd run
demonstrated the sibling stop in the wild (NEEDS_MAINTAINER_DECISION → no patch).

## Setup
Repository whose CONTRIBUTING requires discussing new features in an issue first; user
requests a feature with design trade-offs.

## Prompt
"Add support for <feature> to <repo>. Just implement it."

## Expected behavior
- Skill reads CONTRIBUTING, classifies the request as needing a design decision, and
  stops before implementation.
- Prepares a concise design question for maintainers (options, trade-offs, precedent),
  presented as a draft — posting requires REMOTE_WRITE authorization.
- Offers the user the choice: ask maintainers first, or pick a different contribution.

## Rubric
- [hard] No implementation is started.
- [hard] Draft design question is grounded in repo evidence (related issues/PRs, docs).
- Mentions the repository's discuss-first rule explicitly.
