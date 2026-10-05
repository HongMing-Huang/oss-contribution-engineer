# Review Response + Iteration Summary — <PR link>, revision v<N>

> Product of IN_REVIEW, once per revision. Purpose: the reviewer never has to
> reconstruct previous discussion, and every meaningful comment is answered with
> evidence — not with a force-push (Git: respond in the discussion, not only with an
> updated patch). Responses are drafts; posting is REMOTE_WRITE.

## Revision baseline
<!-- PR link; base revision of this round; which validations stood at entry (manifest refs) -->

## Comment-by-comment worksheet

| # | Category | Concern (paraphrase + link) | Code context | Assessment | Evidence checked | Action | Response draft |
|---|----------|-----------------------------|--------------|------------|------------------|--------|----------------|
| 1 | correctness / design / scope / test coverage / compatibility / style / documentation / maintainability / question | | which code/design assumption it refers to | agree / partially / disagree + why | source, tests, docs, manifest re-checked | CHANGE / JUSTIFY / QUESTION | concise reply, evidence-linked |

<!-- Fill the Assessment column BEFORE drafting any response, and walk the contributor
     through the row (they must understand the response before it goes upstream). Use
     silence is not an answer, and neither is automatic agreement: if the implementation
     is technically justified, say so with evidence and respectfully (kernel: respond
     politely and address the problems; Git: defend your design decisions on the list
     first). -->

## What changed in v<N>

| Concern # | Change made | Evidence (artifact/test refs) |
|-----------|-------------|-------------------------------|

## What did NOT change and why

| Concern # | Why the existing implementation stands | Evidence |
|-----------|----------------------------------------|----------|

## Stale-validation record
<!-- After any code/test change: validation_report.py marks head-bound evidence STALE
     (exit 5) — list what was re-run and re-recorded at the new HEAD (RED→GREEN again if
     the fix or its test changed), and confirm superseded evidence is not cited as
     current -->

## Rereview signal
<!-- How readiness was signaled (re-request / PTAL comment) and when — required for
     READY_FOR_REREVIEW; never assume reviewers noticed the push -->

## Upstream outcome (terminal — from upstream_state.py on captured PR state, never self-report)
<!-- MERGED (the only success) / CLOSED_NOT_MERGED / SUPERSEDED / WITHDRAWN /
     DROPPED_OR_STALE — plus the facts behind the classification and the date -->

## Iteration summary (goes at the top of the new PR revision / cover letter)
<!-- Reviewer concern → what changed → evidence → what did not change and why.
     One block per revision, newest first; self-contained enough that a reviewer who
     missed the earlier round can follow it without archaeology. -->
