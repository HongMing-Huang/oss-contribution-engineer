# Task Classification Taxonomy (research output 5)

Task type routes retrieval: **no universal ranking policy** (ARB: per-task winners
differ sharply). Classification happens at Goal Compile time and may be revised with a
recorded reason.

| Task type | Query signal | Retrieval priority (priors) | Radius policy | Gold intuition |
|---|---|---|---|---|
| `explore` | free-form understanding request | cognition (L0–L2) + RepoMap-style structural prior + path | R1 broad, slow descent | subsystem overview |
| `code2test` | implementation change / PR intent | **test relationships** ↑, symbol ↑, lexical | R1 = change target + its tests; R2 = shared fixtures/harnesses | related tests (ARB code2test) |
| `comment2context` | review comment + given file | **sibling/neighborhood** (same dir/abstractions) ↑, symbol refs ↑; given file is *given*, not gold | R1 = reviewed file + close neighbors; R2 = implementing siblings of touched symbol | additional context files (ARB comment2context) |
| `trace2code` | failure output / stack trace | **lexical (frames)** ↑↑, history (recent fixes) ↑, path; tests are auxiliary, not gold | R1 = frame files + their callees on failure paths; R2 = test harness; R3 = recent history | root-cause source (ARB trace2code) |
| `edit2ripple` | anchored change | **graph expansion (importers/callees)** ↑↑, test relationships ↑ | R1 = anchor + direct relations; R2 = ripple candidates w/ impact ranking | affected files (ARB edit2ripple) |
| `issue2code` | issue text | lexical + symbol + cognition domains; history for regressions | R1 candidates → descend on best | patched files (LocAgent issue→code) |
| `review` | diff/PR | diff files are given; **graph + history** for context around changed hunks | R1 = changed files + direct relations; R2 = callers/tests of changed symbols | evidence a maintainer would demand |
| `bug_hunt` | "find a bug" | recent-fix history ↑↑, sibling/parity pairs ↑, test-gap signals | R3-style survey lens, then R1 on candidate | reproducer files |

Classifier output: `{primary: <type>, secondary?: <type>, confidence: qualitative
(high/med/low) + reason}` — never a numeric probability (V2 rule: no fake precision).

Ambiguity rule: when primary is unclear, use `issue2code` priors (the safest general
mix) and record why; the router output exposes which signals fired so misrouting is
visible and correctable.
