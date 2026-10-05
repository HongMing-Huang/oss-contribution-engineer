# Patch Design

Before editing production code, write the PATCH PLAN (assets/implementation-plan.md).
Editing without a plan is how scope creep happens.

## PATCH PLAN (required fields)

- **Violated invariant** — the rule the bug breaks
- **Files expected to change** — exact paths (production and test)
- **Behavior changing** — precisely what
- **Behavior explicitly NOT changing** — adjacent behaviors that look related but must
  stay identical
- **Regression test** — the RED test from testing-strategy.md
- **Compatibility considerations** — public API? serialized formats? downstream behavior?
- **Rollback risk** — how cleanly can this be reverted?

## Minimum-change principles

- Ask: "Can this bug be correctly fixed with **less** code?" If yes, prefer the smaller
  correct implementation.
- Follow the repository's existing style; do not impose generic "clean architecture"
  patterns on a mature codebase. Kernel coding-style exists because reviewers maintain
  the code for decades — local style wins over your habits.
- Reject: new abstractions without demonstrated need, helper classes for one call site,
  new dependencies for small fixes, renames, global reformatting, adjacent cleanup,
  speculative extensibility ("we might need this later").
- Never move code and modify it in the same change (kernel rule — it destroys review
  and blame).
- Format only the lines you touch, with the project's own formatter (LLVM's
  `git clang-format` is the model: format changed lines, not files).
- If investigation shows no patch is necessary, "no change required" is a successful
  result — say so plainly.

## Diff budget (heuristic, not law)

For a small bug fix, prefer:

- production files: 1–5
- test files: 1–3
- new dependencies: 0
- unrelated refactors: 0
- global formatting: 0

If scope grows beyond the PATCH PLAN mid-implementation: **stop**, explain the growth to
the user, and let them decide (fix separately, split the patch, or continue). Never
silently expand the task. Bigger is not automatically wrong — a fix that genuinely needs
5 files is fine when the plan said so — *unexpected* growth is the problem.

## Scope audit (before PR preparation)

```bash
python3 <skill-dir>/scripts/diff_scope_check.py <repo> --base <base-ref> --intended <files...>
```

Report: changed files, added/deleted lines, dependency/lockfile changes,
formatting-only files, generated files, new public API surface, test/doc changes, and
any file outside the intended list. Adapt the base ref to repository convention
(`origin/main`, `main`, `master`, integration branches). Complementary manual commands:

```bash
git status && git diff --stat && git diff --check
git log --oneline <base>..HEAD && git diff <base>...HEAD
```

Anti-garbage-code rules the audit enforces: no abstractions without need, no
dependency additions for trivial problems, no unrelated refactors, no comments explaining
obvious code, no defensive frameworks around small bugs, no duplicated utilities, no
`any`/casts just to make the compiler quiet, no swallowed errors, no weakened or deleted
failing tests, no blind snapshot updates, no skipped validation "because it's obvious".
