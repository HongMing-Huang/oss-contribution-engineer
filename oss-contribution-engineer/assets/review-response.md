# Review Response + Iteration Summary — <PR link>, revision v<N>

> Product of IN_REVIEW, once per revision. Purpose: the reviewer never has to
> reconstruct previous discussion, and every meaningful comment is answered with
> evidence — not with a force-push (Git: respond in the discussion, not only with an
> updated patch). Responses are drafts; posting is REMOTE_WRITE.

## Revision baseline
<!-- PR link; base revision of this round; which validations stood at entry (manifest refs) -->

## Comment-by-comment worksheet

| # | Category | Concern (paraphrase + link) | Interpretation | Evidence checked | Action | Response draft |
|---|----------|-----------------------------|----------------|------------------|--------|----------------|
| 1 | correctness / design / scope / test coverage / compatibility / style / documentation / maintainability / question | | what it actually challenges | source, tests, docs, manifest re-checked | CHANGE / JUSTIFY / QUESTION | concise reply, evidence-linked |

<!-- Use one row per meaningful comment. Silence is not an answer, and neither is
     automatic agreement: if the implementation is technically justified, say so with
     evidence and respectfully (kernel: respond politely and address the problems;
     Git: defend your design decisions on the list first). -->

## What changed in v<N>

| Concern # | Change made | Evidence (artifact/test refs) |
|-----------|-------------|-------------------------------|

## What did NOT change and why

| Concern # | Why the existing implementation stands | Evidence |
|-----------|----------------------------------------|----------|

## Stale-validation record
<!-- After any code change: which validations were re-run (RED→GREEN if the fix or its
     test changed), which remain valid, validation report regenerated — superseded
     evidence never cited as current -->

## Iteration summary (goes at the top of the new PR revision / cover letter)
<!-- Reviewer concern → what changed → evidence → what did not change and why.
     One block per revision, newest first; self-contained enough that a reviewer who
     missed the earlier round can follow it without archaeology. -->
