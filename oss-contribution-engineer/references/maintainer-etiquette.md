# Maintainer Etiquette

Maintainer attention is the scarcest resource in open source. Every artifact this skill
produces should shorten their review, not extend it.

## Before commenting "I'd like to work on this"

Investigate enough to say, in two or three sentences:
- what path is affected and why the bug (or need) is real,
- how you plan to reproduce/verify it,
- intended scope (files, kind of change),
- test strategy.

If CONTRIBUTING requires discussing features first, or the issue is
DESIGN_BLOCKED/NEEDS_MAINTAINER_DECISION — stop before implementing and prepare the
design question instead.

## Commenting discipline

- One comment per issue, not a stream. No repeated pings: LLVM — politely ping weekly;
  kernel — wait about a week; Git — one version of a patch series per day maximum.
- Ask specific questions with evidence ("this assert on line X contradicts doc Y — which
  is authoritative?"), never "any updates?".
- Do not create speculative bug reports or issue-list dumps. One candidate, one thread,
  with reproducer attached.
- No giant AI-written issue bodies. A maintainer should be able to read it in under a
  minute: expected / actual / repro / environment / versions.
- Never open competing PRs for the same problem, and never double-track (issue + PR
  asking the same question).

## PR preparation

- Small, self-contained, described so the first line alone tells the story (Google CL
  description rules; assets/pull-request-template.md).
- Follow the repository's PR template and commit conventions exactly (from recon).
- Include changelog entries if the project requires them; note the issue with the
  project's preferred keyword ("Fixes #N" vs "Closes #N").
- State what was tested and what was not, plainly. Overclaiming testing is worse than
  admitting limits — kernel reviewers and Git both call out unverified claims.
- Choose reviewers via CODEOWNERS/MAINTAINERS rather than @-mentioning strangers.
- Expect iteration: answer every review comment, or state explicitly why a suggestion
  was not applied (LLVM treats unacknowledged feedback as blocking).
- If the PR goes stale and you abandon it, say so and close it — abandoned work left
  open costs maintainers context-switching.

## What never to do

- Spam or mass-comment; farm typo/formatting PRs; bump stale threads.
- Claim exhaustive testing that wasn't run; hide AI assistance where disclosure is
  required (see ai-assisted-development.md).
- Publish anything — issue, comment, branch, PR — without the user's explicit
  authorization for that action (REMOTE_WRITE).
