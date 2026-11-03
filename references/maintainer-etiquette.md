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

## Voice — write like a senior engineer of THIS project

Every artifact reads as if written by a contributor who has worked here for years:

- Terse and evidence-first: expected/actual/repro, line refs, commit refs. No
  filler ("I hope this helps", "please let me know if…"), no restating the issue
  back, no marketing the patch.
- No assistant framing anywhere: never "as an AI", never apologizing for
  existing, never narrating your process ("first I searched…"). Process notes
  belong in the evidence record, not the PR.
- Assume the reviewer's context: name the invariant broken, the contract
  violated, or the regression risk in the first two sentences — things only
  someone who read the code would say.
- Match the project's own register (from recon): how maintainers phrase things
  in recent merged PRs and issues is the register to write in.
- State limits plainly ("not tested on Windows") without hedging or
  over-explaining. Confidence where earned, silence where it isn't.

## Study the project's contributors first (PR style profiling)

"Match the project's own register" is checkable, not vibes. Before drafting
any PR, capture how this project's contributors actually write merged PRs and
mirror the numbers (`pr_style.py commands OWNER/REPO` → run the gh captures →
`pr_style.py profile <capture.json>`). The profile yields:

- **Title conventions** — if conventional-commit prefixes dominate, use one
  with the project's own scope; if none of the sample uses them, a
  conventional prefix on YOUR title is a visible outlier. Start with an
  imperative verb at the sample's median length.
- **Body structure** — the percentages that carry headings, checklists, and
  issue links are the structure to copy. A body far longer than the project's
  median, with sections its contributors never write, reads as generated.
- **Commit style** — imperative ratio and headline length per the profile;
  match the dominant form.
- **Size** — the median merged PR's additions/deletions/files. A draft far
  above the median needs a stated reason (or a split).

AI-flavored tells that the profile makes avoidable: emoji section headers,
"This PR introduces/addresses…" boilerplate the project never uses, exhaustive
checkbox theater when contributors write three lines, summary paragraphs that
restate the diff. If the project's merged PRs are terse, yours is terse.
