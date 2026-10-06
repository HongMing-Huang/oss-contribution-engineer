# Adversarial Review

After GREEN and REGRESSION, switch roles: become the reviewer whose job is to find
reasons this patch should **not** be merged. Do not ask "is this correct?" — attempt to
falsify it. Produce assets/review-report.md.

Setup: re-read the diff fresh (`git diff <base>...HEAD`), the PATCH PLAN, and the
regression test before reviewing.

## Representation-First Review (design-sensitive patches — advisory lens)

For non-trivial patches (new abstractions, new state machines, public contracts,
error-handling redesigns), review the REPRESENTATION before the diff details —
complexity accumulates through poor representations, and each special case added
is often compensation for one:

- **STATE** — what state does this patch manipulate? Who owns it?
- **DATA** — which representations/data structures carry it? Is the shape right
  for the domain, or is a branch compensating for a poor representation?
- **OWNERSHIP** — who creates, mutates and destroys each piece?
- **RELATIONSHIPS** — which entities now depend on each other?
- **INVARIANTS** — what must remain true, and where is it enforced?
- **SPECIAL CASES** — is each new branch/fallback a real domain case, or
  compensation for a representation that does not fit?

This lens is **advisory**: it shapes review comments and the maintainer-quality
PR description for design-sensitive patches. It is not a universal blocking gate
— small, obvious fixes pass without it.

## Falsification checklist

**Root cause & assumptions**
- Is the root cause the real cause, or a correlated symptom?
- Which assumptions are unverified (protocol version, ordering, encoding, defaults)?
- Does the fix overfit the reproducer — does the same defect survive via a twin path?

**Behavior**
- Accidental public API change? (exports, signatures, wire format, error types)
- Regression in adjacent behavior — did neighbor tests actually cover that?
- Race conditions / ordering assumptions (Google: concurrency is the thing reviewers
  must think hardest about; it rarely shows up by running tests)
- Incomplete cleanup on new error/cancel paths introduced by the fix
- Hidden environment assumptions (OS, locale, timezone, filesystem, provider region)

**Tests**
- Would the new test fail if the bug returned? (flip the fix mentally)
- Does the test encode the same wrong assumption as production?
- Snapshot updates hiding contract changes? Assertions precise?

**Scope & hygiene**
- Unrelated changes, drive-by refactors, renames, formatting churn (diff_scope_check)
- Unnecessary abstractions, unused code, dead parameters
- Excessive or stale comments; comments explaining *what* instead of *why*
- Unsafe casts, `any`/type-suppression used to silence rather than fix
- Swallowed errors, weakened logging
- Dependency creep (manifest + lockfile diffs)
- Security implications (input now trusted differently? new injection surface?)
- Performance regression on hot paths (extra copies, per-iteration I/O, added locks)

**Compatibility**
- Backward compatibility for pinned users of the project
- Downstream packagers: does the change assume tooling or files beyond the repo?

## Maintainer-perspective simulation (before PR_READY)

After the falsification pass, run one adversarial review *as the maintainer who must
live with this code*, answering from the actual patch — its diff, its tests, its
evidence — not from a generic checklist. The questions are the ones this specific patch
invites:

- Why is this a real problem? (who is affected, what breaks today)
- Why fix it here? (why this location in the execution/data flow)
- Can the patch be smaller?
- What contract proves the expected behavior?
- What adjacent behavior can regress?
- Why is this test sufficient? (would it fail if the bug returned?)
- What was not tested?
- Does this introduce maintenance cost a future maintainer will pay?

Every answer must trace to evidence already produced (walkthrough, validation report,
manifest artifacts); a question the patch cannot answer from evidence is a finding —
fix the patch or record the honest limit. The simulation improves both the patch and
the contributor's ability to defend it in real review.

## Verdicts

- Unresolved correctness issue → back to PATCH (fix) or back to PROVE (if the root cause
  itself is now in doubt). Record which.
- Only minor, debatable nits → record them in the Review Report; they may inform the PR
  description ("known trade-offs").
- Clean → PR_READY. The Contributor Understanding status was already recorded at the
  CONTRIBUTOR_UNDERSTANDING gate (SKILL.md; assets/change-walkthrough.md;
  ai-assisted-development.md has the explain-back questions the human must be able to
  answer).

Note what the review could NOT check (long-running behavior, production data shapes,
other providers) so the PR description can carry the same caveat.
