# Cognition Backend Interface (research output 6)

One abstraction, three backends, one priority order. The interface exists so the skill
never regenerates a competing whole-repository index when a valid aligned index exists
(inherited from AOCI-CODE's own governance rule).

## Backend selection (evaluated at recon, re-validated at each receipt open)

```
1. AOCI_NATIVE            — an AOCI index exists in the repo (aoci.txt volume) AND
                            alignment check passes for sampled entries
2. NATIVE_PROJECT_MEMORY  — this skill's own persisted artifacts exist
                            (repository contribution profile + Task Cognition
                            Receipts + evidence manifest) and bind to the same base SHA
3. LIGHTWEIGHT_FALLBACK   — deterministic on-demand collection only
                            (repo_audit + rules scan + retrieval router)
```

Detection (mechanical): presence of `aoci.txt` / `aoci.meta.txt` / `aoci.code.txt` and
a `.aoci/baseline.json`. Alignment check: for a bounded sample of entries, re-hash the
bound source file and compare to the baseline digest; report
`aligned | drifted(<n>) | stale(<n>) | unbaselined(<n>)`. Any non-aligned state downgrades
AOCI usage to "as a map of where things are" — never as truth.

## What each backend may provide (and its evidentiary status)

| Backend | Provides | Evidentiary status |
|---|---|---|
| AOCI_NATIVE | architecture, object responsibilities (F), strong relations (R), exposed contracts (A), high-entropy constraints (S); importance tags for budget allocation | **Cognition** — selects; never proves. Entry claims must be re-verified against current source before edits |
| NATIVE_PROJECT_MEMORY | prior recon profile, past receipts, evidence artifacts, conclusions of earlier investigations | Cognition for *what we did/learned before*; same select-don't-prove rule |
| LIGHTWEIGHT_FALLBACK | repo structure, manifests, CI, contribution docs + live retrieval signals | Deterministic facts about the repo; still not implementation truth until source read |

## Interface (what the skill consumes, backend-agnostic)

```
backend.identity()            -> {kind, version/index-digest, aligned_state}
backend.hierarchy()           -> L0/L1 view (subsystems, entry points, risk areas)
backend.object(path)          -> {responsibility, strong_relations[], contracts[],
                                  constraints[], importance}      # L2/L3 claims
backend.related(path, edge)   -> paths for edge in {imports, calls, references,
                                  inherits, implements, tests, configured_by,
                                  generated_by, changed_with, reviewed_with}
backend.search(query, scope)  -> candidate objects (backend-local ranking)
```

- Every returned object claim carries `source_binding` (path + digest when available).
- The skill MUST read current source (L4) before editing any object — the backend's
  word is a lead, not a license.
- `related()` for AOCI_NATIVE returns only explicit R-field edges (AOCI's own rule: its
  relations are *not* a call graph); `LIGHTWEIGHT_FALLBACK` derives edges by bounded
  source scanning.

## Non-goals

- No new index format competing with AOCI.
- No model-generated summaries stored as authoritative facts without source binding.
- No networked/cloud indexing (V2 portability constraint).
