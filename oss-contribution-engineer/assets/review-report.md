# Review Report (adversarial) — <change>

> The reviewer's goal is to find reasons this patch should NOT be merged — to falsify
> it, not to confirm it. Back to PATCH for unresolved correctness findings; back to
> PROVE if the root cause itself is in doubt.

## Diff under review
<!-- base ref → HEAD; diff stat; scope-audit conclusion -->

## Correctness
<!-- is the root cause real? overfitting to the reproducer? twin paths left broken?
     concurrency/ordering assumptions? environment assumptions? -->

## Design
<!-- does it fit the system? right place/time? existing patterns followed? -->

## Complexity
<!-- anything a reviewer can't quickly understand? unnecessary abstractions?
     speculative extensibility? fewer-code alternative available? -->

## Tests
<!-- would they fail if the bug returned? precise assertions? realistic fixtures?
     deterministic? negatives covered? snapshots hiding the contract? -->

## Compatibility
<!-- public API surface, wire formats, error types, pinned downstream users -->

## Security
<!-- new trust boundaries, injection surfaces, error/info leakage, dependency provenance -->

## Performance
<!-- hot-path costs: copies, I/O per iteration, locks; measurement or explicit "not measured" -->

## Scope
<!-- unrelated changes, drive-by refactors, formatting churn (diff_scope_check findings) -->

## Unresolved concerns
<!-- what review could NOT check (long-running behavior, other providers, prod data);
     carried into the PR description -->

## Verdict
<!-- BACK_TO_PATCH / BACK_TO_PROVE / CLEAN — with which findings and why -->
