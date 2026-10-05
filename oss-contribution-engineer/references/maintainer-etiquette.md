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
  description rules; assets/pull-request-template.md). Problem before implementation —
  the description must let a reviewer decide the change is worth merging before opening
  the diff.
- Follow the repository's PR template and commit conventions exactly (from recon).
- Include changelog entries if the project requires them; note the issue with the
  project's preferred keyword ("Fixes #N" vs "Closes #N").
- State what was tested and what was not, plainly. Overclaiming testing is worse than
  admitting limits — kernel reviewers and Git both call out unverified claims.
- Choose reviewers via CODEOWNERS/MAINTAINERS rather than @-mentioning strangers.
- If the PR goes stale and you abandon it, say so and close it — abandoned work left
  open costs maintainers context-switching.

## Responding to review

- Answer every meaningful comment in the discussion — never let a push be the only
  response (Git: "Reply-All" rule; LLVM treats unacknowledged feedback as blocking).
- One revision note per round: what changed per concern, evidence, and what did not
  change and why — the reviewer should never reconstruct prior discussion (Git
  cover-letter rule: "give a summary of changes since the previous rounds"). Worksheet:
  assets/review-response.md; protocol: references/review-response.md.
- Max one new version per day (Git), batched and verified before resubmitting.
- Disagreement is allowed and sometimes right: a respectful, evidence-backed "here is
  why the current implementation stands" is a valid response — capitulation is not
  required, silence never is.

## What never to do

- Spam or mass-comment; farm typo/formatting PRs; bump stale threads.
- Claim exhaustive testing that wasn't run; hide AI assistance where disclosure is
  required (see ai-assisted-development.md).
- Publish anything — issue, comment, branch, PR — without the user's explicit
  authorization for that action (REMOTE_WRITE).
