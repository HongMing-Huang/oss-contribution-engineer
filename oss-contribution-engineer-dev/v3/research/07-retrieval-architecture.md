# Retrieval Architecture (research output 7)

The Retrieval Router combines independent signal families, routes by task type, and is
allowed to return nothing. It is deterministic, stdlib-only, offline (research outputs
02/03: hybrid beats every single family on ARB; agents as long-context processors
argue for bounded tool interaction over bulk loading).

## Signal families (v1 implementation)

| Family | Method (stdlib) | Strongest for | Weakness (why it's not authoritative) |
|---|---|---|---|
| lexical | BM25 over file tokens (identifier-aware tokenization: camelCase/snake_case split) | trace frames, error strings, named APIs (trace2code) | common-word dilution; no structure |
| path | path-segment match + directory proximity | config/docs/conventions; module guesses (explore) | names lie |
| symbol | regex symbol tables per language (def/class/fn/func/interface/struct) matched to query identifiers | issue2code, comment2context | misses dynamic dispatch |
| test-relations | production↔test pairing: naming conventions + import scan | code2test, edit2ripple | convention-dependent |
| history | `git log --name-only` recency/frequency (bounded window) | regression-prone areas, recent fixes (bug_hunt, trace2code) | shallow clones limited — recorded as such |
| cognition | backend.object()/search(): AOCI F/R/A/S text + tags, or prior receipts | explore, routing priors (L1 subsystems) | claims need verification (summary-as-source-truth is banned) |
| graph | bounded expansion (research output 8) | edit2ripple, review ripple | cost grows with radius; needs pruning |
| external-optional | Language Server / SCIP / embeddings — **pluggable, absent by default** | symbol-precise lookup; semantic similarity | deps/network/model — never authoritative; router works without them |

## Router flow

```
query + goal contract (task type, anchors, given files)
  → per-signal ranking (each family independently)
  → task-type priors weight families (05)
  → RRF fusion (09) + graph-distance penalties
  → bounded expansion of top candidates (graph)
  → abstention check (NO_RELEVANT_LOCAL_CONTEXT factors)   ← allowed to return nothing
  → ranked candidates with per-signal provenance + token-cost estimates
```

## Output schema (router result)

```jsonc
{
  "backend": "AOCI_NATIVE|NATIVE_PROJECT_MEMORY|LIGHTWEIGHT_FALLBACK",
  "task_type": "...", "query_digest": "...",
  "candidates": [ {"path": "...", "rank": 1, "rrf": 0.031, "signals":
                    {"lexical": 0.72, "symbol": 1, "test": 1},
                   "reason": "test file for src/calc.py (imports divide)",
                   "radius": 1, "est_tokens": 1800} ],
  "abstention": {"returned": true, "factors": {...}},   // see 09 § abstention
  "limits": ["history window 200 commits", "shallow clone: history weak"],
  "provenance": {"families_run": [...], "elapsed_ms": ...}
}
```

## Failure-mode notes from research

- BM25/TF-IDF alone ≈ random on SWE-Explore exploration — lexical is a *signal*, never
  the router.
- Embedding rankers fail at function level even with the function named (LocAgent) —
  identifier extraction from queries is mandatory (we do it lexically).
- Static ranking + interactive exploration are complementary (ARB seed pilot): the
  router *seeds*; the agent still explores with intent, and every read is recorded into
  the Task Cognition Receipt (13).
