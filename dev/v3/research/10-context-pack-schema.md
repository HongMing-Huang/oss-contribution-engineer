# Context Pack Schema (research output 10)

A Context Pack is the bounded, provenance-carrying unit the agent actually reads for a
task stage. It is generated from a Task Context Plan (goal contract + router output)
and is **not** a replacement for reading current source before edits — it carries
pointers, digests, and ranges; the agent verifies at L4.

## Task Context Plan (pre-load artifact)

```jsonc
{
  "goal_digest": "...", "task_type": "...",
  "primary_subsystem": "<L1 area + why>",
  "radius_1": [ {"path": "...", "reason": "...", "est_tokens": N} ],  // target objects, direct strong relations, direct tests, contracts
  "radius_2": [ {"path": "...", "reason": "...", "trigger": "<read only if R1 insufficient>"} ],  // callers/callees/importers/siblings/harnesses
  "radius_3": [ {"kind": "subsystem-architecture|historical-PRs|cross-module", "trigger": "..."} ],
  "token_allocation": {"cognition": N, "source": N, "test": N, "history": N, "spec": N},
  "excluded_candidates": [ {"path": "...", "reason": "..."} ],   // visible exclusions, not silent drops
  "backend": "..."
}
```

Nothing in radius_2/3 is read until a recorded reason exists (SWE-Explore/RepoCoder:
expansion needs a trigger; ARB: seeds reduce exploration cost but interaction remains
necessary).

## Context Pack

```jsonc
{
  "pack_version": 1, "goal_digest": "...", "task_type": "...",
  "cognition": {"backend": "...", "claims": [{"object": "...", "claim": "...",
                "binding": {"path": "...", "digest": "..."}}]},        // select-only
  "source_ranges": [ {"path": "...", "lines": "120-165", "symbol": "divide",
                      "why": "RED-gate target; entry S says zero-div guard lives here",
                      "digest": "<sha of file at read time>"} ],
  "structural": [ {"edge": "imports", "from": "...", "to": "...", "why": "..."} ],
  "tests":       [ {"path": "...", "why": "covers failure boundary"} ],
  "history":     [ {"commit": "<sha>", "why": "introduced behavior"} ],
  "external_contracts": [ {"ref": "<doc/spec path or URL>", "claim": "..."} ],
  "invariants":  ["..."],                       // only repo-verifiable statements
  "unresolved":  ["..."],
  "excluded":    [ {"path": "...", "reason": "..."} ],
  "token_accounting": {"cognition": n, "source": n, "test": n, "history": n,
                       "spec": n, "total": n, "soft": N, "hard": N},
  "pack_digest": "sha256(canonical json)"
}
```

Rules:
- Every source range has a `why`; ranges cite symbol boundaries where known (SWE-Explore:
  line-level is where agents are weak — pack spans, not whole files).
- `digest` at read time enables drift detection later (receipt verify).
- The pack is stored with the receipt (13) so a compacted context can rebuild.

## Radius discipline

| Radius | Contents | Requires |
|---|---|---|
| 1 | target objects, direct strong relations, direct tests, direct contract evidence | plan only |
| 2 | callers, callees, importers, siblings, test harnesses | recorded insufficient-evidence note |
| 3 | subsystem architecture, historical PRs, cross-module deps | recorded reason + budget headroom |

Every expansion names what R1 failed to establish. "More context" is never the reason
(SWE-Explore: missing core evidence is fatal, moderate noise tolerable — expand for
*specific missing evidence*, not comfort).
