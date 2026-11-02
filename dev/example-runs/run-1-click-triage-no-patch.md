# Example Run 1 — pallets/click: Issue Triage that ends in NO patch

Real run, 2026-10-03, local clone `/tmp/oss-repos/click` (shallow, current `main`),
`gh` used for platform data. Modes exercised: Repository Recon (1) → Issue Triage (2).
No file in the repository was modified. This is the run demonstrating the skill's
decision **not to compete**.

## Repository Contribution Profile (abbreviated)

| Field | Value | Source |
|-------|-------|--------|
| project | Click, a Python package for creating command-line interfaces | README.md |
| language | Python (88 files) | repo_audit.py |
| package manager | uv (uv.lock) | repo_audit.py |
| tests | pytest, `testpaths = ["tests"]`, `filterwarnings = ["error"]` | pyproject.toml |
| extra test envs | `tox r -e stress` (races), `tox r -e random` (order/pollution) | docs/contributing.md |
| format/lint | ruff-check + ruff-format via pre-commit; codespell; uv-lock | .pre-commit-config.yaml |
| style rules | no ternaries (coverage limitation); no unnecessary dependencies; 80-col Markdown | docs/contributing.md |
| PR process | open a ticket first; tests that fail without the change; changelog entry | .github/pull_request_template.md |
| changelog | actual file is **CHANGES.md** (PR template still says CHANGES.rst — stale) | repo scan |
| AI policy | none found (no AGENTS.md/CLAUDE.md) → default: offer honest disclosure note | repo scan |
| discrepancy noted | PR template references root CONTRIBUTING.rst; none exists in-repo (guide lives on palletsprojects.com) | repo scan |

Local-rules precedence noted: tests must fail without the change (this is the RED gate,
required by the repository itself), changelog entry required, "fixes #N" convention.

## Triage target

Issue **pallets/click#3362** — "`HelpFormatter.write_usage` breaks options at a hyphen"
(open, 0 assignees, label `help output`, 1 comment). On the surface: open + unassigned =
looks available.

## DEDUPLICATE gate (duplicate_work_scan.py)

Capture via `gh` (issue body + 2 timeline pages), parsed deterministically:

- **1 real upstream PR in flight**: pallets/click#3782 "Do not break usage line
  arguments at a hyphen" — **open**
- **8 fork PRs** referencing the issue from AI-agent pipelines
  (@Apoo3va/click ×7, @yoda77777/click ×1) — five labeled "[AI Agent] Fix for #3362",
  several merged *in their own fork repos*, none in upstream
- 20 commits referencing the issue (analysis/fix attempts)

(An earlier render labeled the fork merges just "merged"; the parser now prints
"merged in own repo @fork" so a fork merge is never mistaken for an upstream merge.)

## Classification: **PR_EXISTS — do not compete**

- A maintainer-facing implementation (#3782) is already open upstream. Hard rule 7 and
  the DEDUPLICATE gate forbid competing work without an explicit maintainer invitation.
- The fork pile illustrates exactly what this skill exists to prevent: multiple
  AI-generated fix PRs for the same open issue, none apparently carried upstream —
  pure maintainer-attention waste.
- Further work on #3362 by us would be contribution #11. **No patch. Run ends.**

## What a useful action would be (not taken without authorization)

If the user wanted to help: review #3782's diff against the reproduced defect (READ_ONLY
feedback is REMOTE_WRITE once posted → requires explicit authorization), or nothing.

## Gate outcome

`DEDUPLICATE` gate → classification PR_EXISTS ≠ GOOD_CANDIDATE → **stop before PROVE**.
No reproducer was built (the bug itself is real — click's `write_usage` does wrap at
hyphens — but triage does not need a reproducer to know the slot is taken; building one
would be Mode 4 work requested separately).
