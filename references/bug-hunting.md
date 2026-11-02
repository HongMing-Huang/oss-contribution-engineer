# Bug Hunting (proactive discovery)

Goal: find a *real* unreported bug, prove it, and only then offer a fix. This is not a
"good first issue" wrapper — it generates candidates from code asymmetry and history.
Every candidate must pass the Proof Gate (references/proof-standard.md) before it may be
reported to anyone.

## Lenses (work them in order; keep notes per lens)

### 1. Recent fixes first (highest yield)
Study recent bug-fix PRs and commits (`git log --oneline --grep="fix"`; merged PRs).
For each, extract: what invariant was violated? Then ask:
- do **sibling paths** implement the same invariant differently?
- was only one provider/platform/implementation fixed?
- does the test added with the fix cover the boundary or just the happy path?

### 2. Cross-implementation parity
Compare parallel implementations of the same contract: Python vs TypeScript, sync vs
async, streaming vs non-streaming, browser vs Node, Windows vs POSIX, provider A vs
provider B, old code vs rewritten module. Asymmetric handling of the same input is a
candidate — one side is wrong (or the asymmetry is load-bearing; find out which).

### 3. Sibling path analysis
After finding a fixed bug, enumerate sibling code paths (same helper, same protocol, same
switch arm). **Test before assuming** the sibling is broken — symmetry is a hypothesis,
not evidence.

### 4. Error handling
Swallowed exceptions, wrong fallbacks, `is None` vs falsy confusion, missing cleanup on
error paths, retries without backoff/limits, ignored cancellation, timeouts that don't
cover the slowest step, partial-failure states that leak.

### 5. Resource lifecycle
Listeners, sockets, subprocesses, temp files, timers, abort signals, connection pools:
allocated on every path? released on every exit path including errors and cancellation?

### 6. Protocol / API contract comparison
Compare behavior against the authoritative spec or API docs (use documentation tools or
fetch the spec). Check **version applicability** — docs for v2 do not indict v1 code.
Do not treat external docs as infallible; where doc and code disagree, test which one
real systems expect.

### 7. Test gaps
Missing negative tests for input validation, skipped/xfail tests that encode permanent
bugs, regression tests that assert implementation details instead of behavior, snapshot
tests hiding contract changes.

## Discipline

- Time-box each lens; stop when a strong candidate emerges.
- One candidate at a time through DEDUPLICATE → PROVE. Do not batch-report "20 issues".
- If a candidate turns out to be intended behavior (git blame/comments/tests say so),
  record why and drop it. Do not "fix" intentional behavior that merely looks unusual.
- Report candidates through the Candidate Report; the user decides whether to seek
  maintainer input. For a NEW bug report, draft the issue with assets/issue-draft.md
  (Problem / Reproduction / Expected / Actual / Impact / Evidence / Likely scope /
  Open questions). If the bug is not sufficiently proven, the draft is framed as an
  **UNCONFIRMED INVESTIGATION** — a question to maintainers, not a confident report —
  or is not prepared at all. Static suspicion alone never becomes an issue. Posting
  anything is REMOTE_WRITE.

## Anti-patterns

- Static-only claims ("this looks like it could throw") without a reproducer.
- Reporting style or robustness nits as bugs.
- Flooding the tracker with low-severity speculation — kernel maintainers explicitly
  struggle with this; it gets contributors blocked.
- Assuming the newest docs describe the pinned version in the repo.
