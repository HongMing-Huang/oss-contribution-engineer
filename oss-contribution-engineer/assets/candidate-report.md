# Candidate Report — <issue number or bug-hunt candidate>

> Product of Issue Triage or Bug Hunt. One classification, stated with evidence.
> No patch is written until this report concludes GOOD_CANDIDATE and the user asks for a fix.

## Candidate
<!-- issue link or one-paragraph description of the suspected bug -->

## Evidence
<!-- what was actually observed/read: file:line references, commit SHAs, command output
     (reference evidence-manifest artifact paths), version applicability -->

## Duplicate status
<!-- dedupe scan results: issues searched, PRs found (open/merged), assignments,
     comments, recent commits in the area; record the tool that captured the data -->

## Classification (exactly one)
AVAILABLE / CLAIMED / PR_EXISTS / DESIGN_BLOCKED / NEEDS_MAINTAINER_DECISION /
INVALID / STALE / TOO_LARGE / TOO_TRIVIAL / GOOD_CANDIDATE

<!-- chosen: -->

## Expected scope
<!-- estimated production files (1–5), test files (1–3), dependencies (0), risks of growth -->

## Required environment
<!-- runtimes, credentials, OS specifics; anything that cannot be reproduced locally -->

## Likely files
<!-- concrete paths expected to change -->

## Testability
<!-- how a reproducer and regression test would be built; existing tests to extend -->

## Risks
<!-- duplicate work, architectural sensitivity, behavior ambiguity, flaky tests -->

## Recommendation
<!-- proceed to investigation / stop with reason / ask maintainers first -->
