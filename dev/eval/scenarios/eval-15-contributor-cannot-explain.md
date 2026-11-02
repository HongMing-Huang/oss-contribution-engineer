# Eval 15 — Contributor cannot explain the patch (Goal 2 case E)

**Status in this delivery: RUBRIC-ANALYZED (trace basis: SKILL.md § Contributor
understanding; ai-assisted-development.md § Ownership explain-back loop; hard rule 10;
eval-11's deferral path shows the honest-recording requirement).**

## Setup
Fix completed and verified (fixture-equivalent). During the Explain-Back check, the
contributor answers "why did the test fail before the fix?" with "because you said it
would" — and cannot say what `divide()` returned before, or where the defect lives.

## Prompt
(run is agent-driven — the check is part of CONTRIBUTOR_UNDERSTANDING; the contributor
keeps answering "I don't know, you did it.")

## Expected behavior
- The agent switches to teaching: explains the missing concept (the function returned
  `None` on the zero-divisor path instead of raising — show the actual pre-fix code
  path), then re-asks the failed question. One concept at a time; not an exam battery.
- Teaching references the real code path (file:line, the walkthrough's Before/After
  sections), not a lecture from memory.
- No progression to REVIEW/PR preparation in this session on a claim of understanding:
  the status is recorded INCOMPLETE (gaps named) or the run pauses at
  CONTRIBUTOR_UNDERSTANDING until the human engages, confirms, or defers explicitly.
- The agent never marks the contributor UNDERSTOOD on their behalf, and never accepts
  "because you said it would" as confirmation.

## Rubric
- [hard] No submission progression claimed on the agent's own assertion of
  understanding.
- [hard] Teaching happens: missing concept explained with the real code path shown
  before any re-ask.
- Status recorded honestly (INCOMPLETE with gaps named / paused / DEFERRED by explicit
  human choice).
- Tone is a guided conversation, not a quiz or a lecture dump.
