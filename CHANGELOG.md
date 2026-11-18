# Changelog

## [2.4.2] — 2026-11-18

**Help-first repositioning.** User review: "not a tool that locks the whole
process down — we provide tools that help." The toolkit now says and does
exactly that:

- SKILL.md Runtime section opens with the help-first contract: every script
  works standalone with no session/contract/gate; the gated session is
  opt-in help for full runs with a tamper-evident record; gates protect
  evidence and upstream and NEVER block answering, analyzing or drafting
- `read-rules` works session-less: prints the binding rules list with zero
  files written (previously it demanded init + a Goal Contract just to LOOK
  at the rules — the exact over-gating this round removes)
- Regression test pins: session-less read-rules writes nothing; the SKILL.md
  help-first statement is lint-covered via the body budget

## [2.4.1] — 2026-11-18

PR-writing quality round: the kernel's SubmittingPatches and Google's CL
description rules audited against every PR-drafting surface (template,
etiquette, patch-design) and operationalized where doctrine had them but
draft time didn't:

- title/subject mechanics as defaults (imperative mood — kernel: write "as
  if you are giving orders to the codebase"; ≤72 chars, stands alone, blank
  line, ~75-col body) unless the pr_style profile dictates otherwise
- optimization PRs carry measured numbers with methodology and non-obvious
  costs — "a 'faster' claim without a number is a hope, not a description"
- diff budget gains the changed-lines norm (≲300; community consensus from
  Slack/Graphite/Codacy on review speed) alongside the file budget

## [2.4.0] — 2026-11-18

Learning round grounded in Anthropic's latest skill-authoring guidance and
Linus Torvalds's 2026 statements on AI contributions.

### Added
- **Contributor calibration** (`calibrate --familiarity new|some|expert`):
  the workflow now adapts to the user's basis — teach-first walkthroughs and
  smaller steps for newcomers, terse decision-surfacing for experts. It tunes
  explanation volume and step size ONLY; every gate and evidence requirement
  is identical at every level (deliberately not a mechanical tier)
- Lint: every `references/*.md` must be linked from SKILL.md; reference
  files over 100 lines must carry a `**Contents:**` TOC (per Anthropic's
  reference-organization rules) — 5 files got TOCs

### Changed
- **Doctrine correction (the kernel moved under us)**: the Linux kernel
  required LLM disclosure in Jan 2025 and DROPPED it in Oct 2026; Torvalds
  called banning AI "utterly stupid", opposes "vibe coding" (code the
  contributor does not understand) rather than assistance itself, and posted
  his own first LLM-assisted patch. references/ai-assisted-development.md
  now records the shift and its lesson: policies reverse — recon must read
  the project's CURRENT AI policy, never assume it from memory
- PR template: "Adapt, don't fill" (sections are a floor, not a form — a
  draft that reads like a filled-in form is a defect) and "Grounded, not
  invented" (every claim cites a validation artifact; unbacked claims are
  deleted, not hedged)

## [2.3.2] — 2026-11-18

Design-optimization round, evidence from a body-structure study of the
leading skill repos (anthropics/skills official set, obra/superpowers 319k★,
wshobson/agents 42.6k★):

### Changed
- SKILL.md body slimmed 37.3KB/499 lines → **30.6KB/414 lines** (activation
  cost ~9.3k → ~7.7k tokens, −18%) by moving detail that references/ already
  carried (or now carries): context-acquisition pipeline stages (pointer to
  references/context-acquisition.md et al.), the full communication block
  set (now in references/goal-contracts.md § Communication protocol), and
  the four strategy paths (new references/contribution-workflows.md). Body
  now holds only the runtime contract, gates, rules and indexes — per the
  superpowers principle: enforce mechanics with scripts, keep prose for
  judgment calls
- Body byte budget (≤32,000) added to the lint, locking the slimming

## [2.3.1] — 2026-11-18

Market/cross-tool survey round (9 comparable projects measured; full report
in the private companion repo `docs/market-survey-2026-11-18.md`):

### Fixed
- Degraded mode now specified: on tools without python3/git (chat-only or
  restricted sandbox), skip scripts and gates and apply
  contribution-doctrine + maintainer-etiquette as plain discipline,
  stating that no evidence gate ran (previously: silent dead end)
- metadata.version drifted (2.0.0 vs CHANGELOG 2.3.0) — fixed; a new lint
  check (`test_metadata_version_matches_changelog`) keeps frontmatter
  version and CHANGELOG in lockstep
- Windows note: compatibility field documents the `python`/py-launcher
  fallback when the `python3` alias is absent

## [2.3.0] — 2026-11-05

Standardized problem-digging harness — answers "where do the real problems
hide" with four reproducible layers instead of ad-hoc manual rounds:

- **A. synthetic real-shape monorepo** (always-on): package.json `exports`,
  tsconfig path aliases, barrel re-exports, same-name twin trap — the shapes
  self-authored fixtures lacked
- **B. frozen real corpus** (always-on, offline): 10 real merged lobe-chat
  PRs checked in; profile numbers pinned with gold assertions
- **C. first-mile sequence** (always-on): the exact SKILL.md quick-start
  command chain, asserted to work on a clean repo
- **D. real-repo probes** (network-optional, cached clone): gold-labeled
  rules/impact probes against lobe-chat; skips with reason when offline

Building the harness itself dug out four defects that BOTH the old fixtures
and the manual validation round missed:
- tsconfig alias star replacement was off-by-one: `@/const/trace` resolved
  to `packages/const/src/*/trace` — every alias-subpath DIRECT consumer was
  silently missed (manual validation only eyeballed the barrel fan-out)
- artifact digests covered `created_at`: the same scan twice → different
  digests; digests now cover the measurement, not the wall clock
- conventional-commit classifier missed gitmoji-prefixed titles
  ("🔨 chore(x): …"), mis-advising "no conventional commits" for a repo
  where 10/10 sampled titles carry the type(scope): shape
- consumer_impact scan-cap truncation was silent; now recorded in the
  artifact and warned on stderr

125 tests green (123 offline + 2 network probes).

## [2.2.1] — 2026-11-03

Real-repo validation round (lobehub/lobe-chat, 23k files) — three defects
found in consumer_impact.py's first cut and fixed:

- workspace package imports (`@scope/pkg` via package.json `exports`) and
  tsconfig path aliases (`@/x`) were unresolved — both dominant internal
  import forms in real monorepos; resolution now reads package.json exports
  maps and tsconfig paths precisely before falling back to tail matching
- barrel re-exports (`export * from './x'`) propagate consumption: importers
  of a package root are indirect consumers; the BARREL carries the verdict
  (799 indirect importers on lobe-chat covered by 1 barrel verdict) instead
  of demanding hundreds of sentences
- the 4k-file scan cap stopped inside the first directory tree on real
  monorepos (raised to 30k); the tail-match fallback now requires two
  matching path segments (killed the `@/types/trace` ≠ `const/trace`
  false-positive class)

Validated end-to-end on the real repo: 1-line edit to a widely re-exported
module → 808 consumers found in 3.7s → 4 barrel verdicts → COMPLETE. Also
validated on the same repo: read-rules tiering (78 auto-read docs → 16 real
binding rules), and pr_style against 10 real merged PRs (0% conventional
commits — an agent writing "fix:" would be the outlier).

## [2.2.0] — 2026-11-03

Second review round (consumer-side category critique). Gates prove actions,
not semantics — this release closes the semantic gap the first real run
exposed: every check green, three downstream consumers broken.

### Added
- `consumer_impact.py` — finds every importer of the changed production
  files (lexical import scan, python/js/ts/go; labeled heuristic). PR_READY
  now blocks until each listed consumer carries an auditable
  `--verdict "path::why safe / how verified"` sentence; thin or unlisted
  verdicts are refused
- PR template declares EXACTLY ONE problem per PR — a second problem found
  mid-work means a separate investigation and PR

### Fixed
- Session evidence can no longer leak into a contribution: `init` adds
  `.oss-contrib-evidence/` to `.git/info/exclude` (repo-local ignore, zero
  diff pollution, idempotent)
- Scope audit expands wholly-untracked directories to real file paths
  (was: `unintended_changes: ["__tests__/"]` until staged)

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
