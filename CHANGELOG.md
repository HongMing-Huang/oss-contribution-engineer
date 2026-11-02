# Changelog

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
- `doctor.py` first-run environment check
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
