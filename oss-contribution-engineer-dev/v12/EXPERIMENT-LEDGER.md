# V12 Experiment Ledger — Consumer-Side Skill Design Review

Status: **EXPERIMENTAL**. Protocol: every conclusion needs reproducible evidence
from the consumer side (SKILL.md as raw bytes, CLI --help, real refusal output,
cold-agent transcript). Self-authored summaries (CAPABILITIES/README/ledgers)
were audit TARGETS, never evidence of quality.

## §1 Mechanical compliance lint — `tests/test_skill_lint.py` (in CI via pytest)

6 checks, all green after fixing two lint-parser bugs (trailing sentence
punctuation in path refs; subcommand extraction now parses the argparse
`{a,b,c}` usage line instead of the wrapped two-column list):
- frontmatter keys ⊆ {name, description, license, compatibility, metadata} ✅
- description ≤1024 chars (and ≥200 for trigger coverage) ✅
- body ≤500 lines ✅
- all referenced references/assets/scripts paths exist ✅
- every bash-example subcommand+flag accepted by today's CLI --help ✅
- every production-surface subcommand appears in SKILL.md (no hidden surface) ✅

## §2 Triangle audit — `tests/test_triangle_audit.py` (in CI via pytest)

Three orphan classes, mechanically checked; two REAL orphans found and fixed:

1. **claimed-without-test**: `contributor_understanding` cited two test
   functions that no longer exist (consolidated away in earlier rounds).
   Fixed: citations now point at the tests that actually exercise the
   understanding gate (`test_happy_path_to_pr_ready`,
   `test_d_scope_conclusion_cannot_be_relabelled`).
2. **tested-but-undocumented**: `acknowledge-scope-finding` and
   `record-remote-action` were exercised by tests but never mentioned in
   SKILL.md. Fixed: upstream-lifecycle section now documents both (plus
   `accept-review-change` cross-reference).
3. **mentioned-but-nonexistent**: no orphans (evidence script paths all exist).

## §3 Decision-tree walkthrough — in-place recovery at every refusal

Systematic scan of all `GATE REFUSED` print sites in contribution_session.py;
"covered" = the refusal output itself names the next operation. Before: 6
sites printed the blocker with no recovery path. After: **0 unhinted sites** —
added in-place `next:` hints to: cannot-advance (→ explain-blocker), init
repository mismatch (→ recompile contract), stopping classification (→ report /
set-classification), post-hoc remote grant (→ honest upstream outcome),
request-rereview substate (→ re-capture), revalidation debt (→ RED→GREEN rerun
commands). 94 tests green after.

## §4 Cold-start usability test — zero-context sub-agent

Protocol: a fresh sub-agent received ONLY (a) the SKILL.md path, (b) a real
repository (/tmp/cold-tqdm), (c) the verbatim task "Investigate issue #1845
and determine whether we should contribute a fix" — no project context, no
command coaching. It must report: full command transcript, stuck points,
missing information, outcome, usability verdict.

**Result (transcript preserved in agent output; repo /tmp/cold-tqdm):** the
cold agent COMPLETED the task — investigated tqdm#1845 blind, found two open
fixing PRs via the issue's own timeline, classified PR_EXISTS, reproduced the
bug for the intended reason (take 2), and was correctly stopped at PROVE by
the STOPPING gate. Net: the workflow is usable cold, with real defects.

**Defects found (8 stuck points → D1–D8), fixes applied this round:**

| id | defect | fix |
|---|---|---|
| D1 | repo_audit.py JSON lacked repository_id → `record --kind recon` always rejected (HARD blocker; agent had to read runtime source and hand-derive the envelope) | repo_audit.py now emits gate-ready repository_id (origin slug) + digest; verified on /tmp/cold-tqdm |
| D2 | `--from-issue #123` bare form rejected despite help text promising it | _fetch_issue_source now infers the slug from the session repo's github origin; bare form verified working |
| D3 | done_when `artifact:` (colon) rejected — only space form matched, agents write the colon form | OBSERVABLE_PREFIXES accepts colon form of every prefix; verified |
| D4 | `status`/`explain-blocker` claimed "advance is legal / no blockers" while the gate mechanically refused under a STOPPING classification (contradiction) | both ops now report [BLOCKED: stopping outcome] and point to report/set-classification; verified |
| D5 | a mistaken evidence entry (wrong-reason FAIL) stayed active forever and flipped the final Validation Report to FAILED | `evidence_manifest.py void --id N --reason` appends a void record; validation_report excludes voided entries from conclusions (visible VOIDED note row); wrong-id rejected; end-to-end verified (FAILED→PASSED) |
| D6 | `--cwd` recorded but is not a PYTHONPATH — repro scripts failed on imports | documented in SKILL.md (repro scripts must insert repo into sys.path); behavior unchanged by design |
| D7 | cold-start retrieval ranked contrib wrappers over the file named in the issue import | known limitation (matches V11 finding: symbol names must appear in task text); grep fallback documented |
| D8 | no explicit NO_PATCH terminal state/finish op — refusal message is the only authority | recorded as known limitation; the refusal + status now both name the terminal path consistently (D4 fix) |

Also fixed during the loop restructure: a regression where non-execution rows
disappeared from the Validation Report (caught by 3 existing tests, repaired;
skip rows render again).
