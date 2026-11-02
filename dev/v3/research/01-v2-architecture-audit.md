# V2 Architecture Audit (research output 1)

V2 of `oss-contribution-engineer` is contribution-discipline machinery. Its design
center: gates, evidence, minimal patches. It was built assuming a *human-scaled*
repository workflow; nothing in it addresses how an agent acquires context in a large
codebase.

## What V2 has (keep, do not rebuild)

| Capability | Where | V3 disposition |
|---|---|---|
| Repository Contribution Profile (recon) | SKILL.md § recon, repository-recon.md, repo_audit.py, contribution_rules_scan.py | **Reuse** — becomes the L0/L1 layer of hierarchical cognition |
| Permission model READ_ONLY/WORKTREE_EDIT/REMOTE_WRITE | SKILL.md | **Reuse** — the Goal Contract's `authority` field formalizes it |
| Evidence witnessing + validation report | evidence_manifest.py, validation_report.py, testing-strategy.md | **Reuse** — receipts reference the same manifest |
| RED→GREEN, proof gate, dedupe | proof-standard.md, testing-strategy.md, duplicate_work_scan.py | **Reuse verbatim** — orthogonal to V3 |
| Patch plan, diff budget, scope audit | patch-design.md, diff_scope_check.py | **Reuse** — PATCH INTENT (V3 protocol) is the *communication form* of the same plan |
| Adversarial review, etiquette, AI policy, doctrine | references/* | **Reuse verbatim** |
| Eval suite (10 patch-discipline scenarios) | dev/eval/ | **Reuse** — V3 adds a *separate* retrieval eval layer (research output 14) |

## What V2 lacks (V3 must add)

1. **No goal representation.** User intent is carried in prose; the agent implicitly
   substitutes its first implementation guess for the goal. Nothing distinguishes
   "what the user wants" from "what the agent plans to do".
2. **No context acquisition discipline.** Recon is static (docs/config); the skill says
   nothing about how to *find code* in a 500k-line repository, when to stop reading,
   or what to do when nothing relevant exists.
3. **No persistent cognition.** The recon profile is re-derived per session; there is no
   artifact binding understanding to source SHAs, so post-compaction the agent either
   re-reads everything or hallucinates prior understanding.
4. **No retrieval or ranking vocabulary** — no signal families, no fusion, no
   abstention, no budget accounting.
5. **No evaluation of context quality** — the eval suite measures patch discipline,
   never whether the agent found the right files/lines.

## Compatibility constraints on V3

- V2's scripts are deterministic, stdlib-only, zero-network — V3 scripts must stay so.
- SKILL.md is at 242 lines (spec cap 500): V3 additions must be ~120 lines max, detail
  in new references.
- V2's evidence vocabulary (EXECUTED/PASS/FAIL/SKIPPED/UNAVAILABLE) is the substrate
  V3 receipts build on; do not fork it.
- The security boundary (kernel-derived: agent never sends anything itself) extends
  unchanged to any cognition backend interaction.

## Verdict

V3 is an *extension*, not a rewrite: two new capability layers (Goal Intelligence,
Adaptive Repository Context Acquisition) wired into the existing state machine between
RECON and CANDIDATE — the DISCOVER/RECON/CANDIDATE gates gain goal-compiler and
context-planner exit criteria. All V2 gates survive unchanged.
