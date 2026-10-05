# Adaptive Repository Context Acquisition

Research basis: v3/research/06 (backend interface), 02 (matrix), 03 (synthesis).
Principle: **never assume a large repository should be loaded into context**. The
pipeline is Persistent Cognition → Goal Understanding → Task Classification → Adaptive
Retrieval → Structural Expansion → Context Packing → Source Verification, under one
law:

> **Cognition selects. Source proves. Tests verify. History explains.**

## Hierarchical cognition (L0–L4)

| Level | Content | Loading rule |
|---|---|---|
| L0 Project | purpose, layout, stack, contribution process (recon profile) | always (once per session) |
| L1 Domain/Subsystem | subsystem map, entry points, risk areas | on task start, via backend |
| L2 Component | component responsibilities, strong relations | only for likely domains |
| L3 Object/File/Symbol | responsibilities, contracts, constraints (e.g. AOCI F/R/A/S) | only for routed candidates |
| L4 Current Source | actual bytes, spans | **only for the areas a task touches — never the whole repo** |

A task begins at L0/L1 and descends only through relevant areas.

## Cognition backends (selected at recon, re-validated per receipt)

1. **AOCI_NATIVE** — `aoci.txt`/`aoci.meta.txt`/`aoci.code.txt` volumes present AND
   alignment check passes (sampled entries re-hashed vs `.aoci/baseline.json`).
   Provides architecture, responsibilities, strong relations, contracts, high-entropy
   constraints. If drifted/stale → usable as a *map*, never as truth.
2. **NATIVE_PROJECT_MEMORY** — this skill's own persisted profile + receipts +
   evidence manifest. Same select-don't-prove rule.
3. **LIGHTWEIGHT_FALLBACK** — deterministic on-demand collection only.

Never regenerate a competing whole-repo semantic index when an aligned AOCI index
exists. The backend's claims are leads: **persistent summary, embedding result, graph,
history, or memory cannot substitute for reading current source.**

## Source verification rule (hard)

Before modifying any object, read its current source. Before editing a symbol, retrieve
enough enclosing context for: signature, call assumptions, error handling, local
invariants, nearby tests. `cognition_receipt.py verify` re-hashes recorded reads — a
CHANGED verdict invalidates every cached claim about that file (mixing obsolete source
with current source is an anti-pattern).

## Progressively: the radius discipline

See context-packing.md (Context Pack schema): Radius 1 = targets + direct strong
relations + direct tests + contracts; Radius 2 = callers/callees/importers/siblings/
harnesses; Radius 3 = subsystem architecture + historical PRs + cross-module deps.
Every expansion names the specific evidence R1 failed to establish. "More context" is
never a reason (SWE-Explore: missing core evidence is fatal, moderate noise tolerable).

## Anti-patterns (explicitly rejected)

load-the-entire-repository · embedding-only retrieval · blind top-K chunk retrieval ·
unbounded graph traversal · summary-as-source-truth · context size as a proxy for
understanding · "100% of the repository understood" claims · rebuilding AOCI when an
aligned AOCI index exists · mixing obsolete source with current source · silent context
truncation · unproven semantic summaries.
