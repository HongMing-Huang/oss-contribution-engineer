# V10 Experiment Ledger — Skill Integration & Usability

Status: **EXPERIMENTAL** (unchanged). This ledger extends `../v9/EXPERIMENT-LEDGER.md`.

## Production surface (the deliverable)

`contribution_session.py` is now the Agent-facing workflow: investigate /
note / read-source / evidence / read-rules / refresh-context / explain-blocker /
resume / report. `repository_intelligence.py` composes backends with an explicit,
printed fallback chain. Implementation modules (retrieval_router, localize_two_stage,
context_planner, repository_intelligence internals) are non-surface per SKILL.md.

## Failure records closed this round

- **F4 CLOSED**: `evidence_manifest.py record --cwd <dir>` implemented (entry
  records the EFFECTIVE cwd; regression test
  `tests/test_v10_skill_surface.py#test_evidence_cwd_pins_the_witnessed_run`).
  Root-caused en route: the entry dict had a SECOND pre-existing `"cwd"` key
  (caller cwd) that shadowed the new one — a dict literal keeps the last key.
- **F6 CLOSED**: `UNCONFIRMED` added to CLASSIFICATIONS + STOPPING
  (regression test `tests/test_v10_skill_surface.py#test_unconfirmed_is_a_stopping_classification`
  verifies patch-side states are blocked). click-3802's honest verdict is now
  expressible directly instead of borrowing DESIGN_BLOCKED.

## Second real-task acceptance (fresh blind task, session ops only)

`runs/v10b-requests-result.json` — psf/requests @661970d1 (blind PR_TITLE:
"Fix `_encode_files` detection for `__getattr__`-based file wrappers"):

- `investigate` (one op) → backends PYTHON_AST+LEXICAL (fallback chain printed)
  → target `src/requests/models.py::_encode_files [184,252]` digest=CURRENT.
- `read-source` showed the detection loop; `read-source --follow-question`
  followed one semantic relation on request (recorded into evidence).
- Investigator notes recorded via `note`; the repro was written FROM the read
  source: a `__getattr__` file wrapper is not detected → raw wrapper reaches
  urllib3 → TypeError (witnessed RED at base).
- Independent fix: duck-typed read detection (`not hasattr(fp,"__len__") and
  hasattr(fp,"read")`) — the mechanism matches upstream 7502 but was derived
  from the investigation, not copied.
- head-bound GREEN (regression test passes) + upstream subset 241 passed →
  UNDERSTOOD (human-confirmed) → scope audit → **PR_READY**. `resume` OK.

Honest notes: the full upstream suite had 203 collection errors from
incomplete local deps → a bounded subset was used and recorded; stage-2
exact-matching surfaced same-named TEST functions before the pack carried the
production file (weakness known from V9, re-confirmed on a second blind task).

## Maturity upgrade

`session_workflow_investigate_note_read_source_resume_report`:
IMPLEMENTED → **REAL_TASK_VALIDATED** (two independent real-repository runs —
click-3805 PATCH_READY and requests-7502 PATCH_READY — driven solely through
the session surface; CAPABILITIES.json updated).

## Incident note (kept for honesty)

`rm -rf` of the benchmark clone while the tool shell's cwd was inside it
killed the shell (spawn ENOENT); recovered by recreating the directory with
the file tool, then re-running cleanup from the repo root. Lesson: `cd` out
before deleting the directory the shell stands in.
