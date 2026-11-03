# Changelog

## [2.1.0] — 2026-11-03

Real-usage fixes from a first external session (TypeScript monorepo, lobehub):
six reported problems, three of them blocking, all verified against source.

### Fixed
- Test-path recognition now covers the whole TS/JS family (`.test.ts/.tsx`,
  `.spec.ts/.tsx`, `.mjs/.cjs`, …) — co-located `*.test.ts` regression tests
  no longer fail classification, and test files never enter rules discovery
- `--test-file` resolution tries the caller's cwd, then `--cwd`, then the
  repo root; an unresolvable path is a loud warning instead of a silent
  identity drop that broke RED binding
- Goal-contract identity gate now explains that session identity is the
  ORIGIN slug (on a fork: `<you>/<repo>`, not upstream) and shows the
  recompile command
- `diff_scope_check.py --intended` accepts space-separated, repeated, and
  comma-separated forms
- SKILL.md script examples corrected (`contribution_rules_scan.py scan`,
  `duplicate_work_scan.py commands`); a new lint check now fails CI on any
  script invocation whose subcommand isn't in the real `--help` output

### Changed
- **Rules reading is two-step and honest**: READMEs, changelogs, and
  data/test files are no longer "binding governance docs" (a monorepo
  previously demanded 78 full reads). `read-rules` discovers the curated
  binding set, then takes one `--read PATH::rule` per document — the stated
  sentence is the claim of engagement; the receipt can't be mass-produced
- First-run check renamed reference in README (`envcheck.py`); envcheck now
  warns when the copy it checks differs from the copy an agent loaded

### Added
- `pr_style.py` — capture and profile how a project's contributors actually
  write merged PRs (title/commit/body conventions, size); the PR draft must
  mirror the profile instead of a generic template
  (references/maintainer-etiquette.md § Study the project's contributors first)
- `note --kind test` for recording what a test run showed during
  investigation

## [2.0.0] — 2026-11-02

First public release. Full lineage in `dev/` (experiment ledgers V3–V12).

### Added
- One-command production workflow: `contribution_session.py` with
  `investigate --from-issue` / `note` / `read-source` / `evidence` /
  `read-rules` / `refresh-context` / `explain-blocker` / `resume` / `report`
- Evidence-first contribution state machine: DISCOVER → RECON → CANDIDATE →
  DEDUPLICATE → PROVE → RED → PATCH → GREEN → REGRESSION →
  CONTRIBUTOR_UNDERSTANDING → REVIEW → PR_READY → IN_REVIEW with mechanical
  gates (no advance without machine evidence; no edit without human-granted
  authority; no remote write without explicit authorization)
- Repository intelligence: automatic backend selection (AOCI runtime / AOCI
  file volumes / Serena LSP / python-ast / lexical) with visible fallback
  chain; symbol spans with digest verification; WHY/RELATION/BACKEND/SOURCE
  provenance on every delivered context span
- Investigation State that survives restart/compaction (facts, hypotheses,
  evidence, contradictions, unresolved, candidate root causes, next action)
- Witnessed evidence manifest (tamper-evident JSONL; RED proofs via
  `--expect-fail`; head-bound GREEN; `--cwd` pinning; void for mistaken
  entries)
- Upstream lifecycle classification from captured PR state (MERGED is the
  only success; closed≠merged; 8 outcome classes)
- `envcheck.py` first-run environment check
- 95 tests; CI (lint + triangle audit + capability-claim validation)
- Anti-slop doctrine grounded in the 2025–26 community record (curl, Godot,
  OCaml, kernel); serial-contribution hard rule; security-informed reporting
  requirement; default no unsolicited AI markers

### Changed
- Disclosure default: silent policy → no AI markers; disclose only where
  policy requires (kernel `Assisted-by:` etc.) or when a maintainer asks
  directly

### Known limitations
- LSP symbol localization requires symbol names in the task text
  (held-out validated 1/2; code-grounded identifier extraction is the
  follow-up)
- django-scale repository routing p95 ≈ 46s (PageRank cost; no observed
  correctness failure from latency)
- Official AOCI upstream runtime unproven (contract-conformant service
  tested; official binary not installed per environment constraints)
