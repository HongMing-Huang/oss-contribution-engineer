# Graph Schema Proposal (research output 8)

Edges first-class, traversal second-class. The graph is a *signal source*, bounded by
construction; uncontrolled BFS is an anti-pattern (LocAgent/OrcaLoca pruning lessons).

## Edge vocabulary

| Edge | Meaning | Source (deterministic) |
|---|---|---|
| contains | dir→dir, dir→file, file→symbol | path walk + symbol table |
| imports | file→file | language-specific import/include/require/`use` scans |
| calls | symbol→symbol | name-reference heuristic (LSP/SCIP upgrade path) |
| references | symbol→symbol non-call | identifier occurrences |
| inherits / implements | class→class | keyword/class-decl heuristics |
| tests | test file→production file | naming conventions + import scan (V3) / build systems |
| configured_by | object→config file | manifest/CI/config proximity rules |
| generated_by | generated→source/template | generated-path patterns (from diff_scope_check table) |
| changed_with | file↔file | git history co-change (bounded window) |
| reviewed_with | file↔file | CODEOWNERS/Maintainers grouping (weak prior) |

All edges carry `confidence: exact | heuristic` — heuristic edges never gate edits
alone; the source-verification rule still applies to every touched object.

## Bounded expansion (the only traversal allowed)

Priority-queue frontier expansion (Dijkstra-flavored), never BFS:

```
score(n) = base_relevance(n) × distance_penalty^depth × type_prior(edge)
prune when: depth > max_depth (default 2; 3 only with recorded reason)
            OR cumulative node budget spent (default 50 nodes)
            OR estimated token cost > allocation for this expansion
            OR score < prune_floor (default: 0.25 × best frontier score)
```

- `type_prior`: tests ×1.0 for code2test/edit2ripple; imports ×1.0 for edit2ripple;
  contains ×0.8 for explore; changed_with ×0.9 for bug_hunt (etc. from 05).
- Every emitted expansion node records: parent, edge type, depth, penalty, reason.
- Rebuild-vs-reuse: `changed_with`/`imports` are computed per-run over bounded inputs;
  no persistent whole-repo graph is stored (that is AOCI's/external tooling's job when
  present).

## Why this shape

- OrcaLoca: pruning before the LLM sees anything — our frontier pruning happens in the
  router, before any read.
- LocAgent: relevance decays with graph distance between mentioned and patched
  entities — our distance_penalty encodes exactly that.
- RepoGraph: graph access must be available *mid-task* — expansion is invokable per
  candidate set, not only at plan time.
