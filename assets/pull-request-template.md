# PR Draft — <title>

> Prepared, never published, without explicit REMOTE_WRITE authorization from the user.
> Follow the repository's own PR template if one exists (recon surfaces it); this draft
> is the content. The first sections must let a reviewer decide whether the change is
> worth merging *before* opening the diff. No AI-style change logs: "Implemented X",
> "Updated Y", "Added tests" without saying why are rejected — every section answers
> "why", not just "what". State what was tested — and what was not.

## Problem
<!-- the underlying problem first (kernel: "Describe your problem. … there must be an
     underlying problem"), with user-visible impact; link the issue with the project's
     preferred keyword ("Fixes #123" / "Closes #123") only when the maintainer workflow
     expects it -->

## Root Cause
<!-- the code-level cause; commit that introduced it if known (Fixes: <sha> where used) -->

## Change
<!-- what this PR does, minimal and factual; files touched and why; describe the change
     in plain English so the reviewer can verify intent before reading the diff -->

## Why this approach
<!-- why this location and this design; the alternatives considered and why they were
     rejected; what the change restores and why it is minimal (Git: the message must
     "justify the way the change solves the problem" and record discarded alternatives) -->

## Tests executed
<!-- tests actually run — RED evidence on unmodified upstream, GREEN, suites, static
     checks — with executed counts from the Validation Report; state plainly what was
     NOT tested and which levels are SKIPPED/UNAVAILABLE. Overclaiming testing is worse
     than admitting limits. -->

## Risks
<!-- behavioral changes visible to users; adjacent behavior that could regress; expected
     downsides so the reviewer can weigh costs against benefits (kernel rule);
     performance notes if relevant -->

## Non-goals
<!-- what is intentionally out of scope; unrelated problems noticed but not fixed here
     (one logical change per patch) -->

## Related issue / discussion
<!-- links to the issue, prior PRs, mailing-list or maintainer threads this builds on;
     note if design was agreed with maintainers first -->

## Disclosure (per repository AI policy)
<!-- AI-assistance note or Assisted-by line only if the project's policy asks for it;
     sign-offs/DCO are added by the human contributor, never by the agent -->
