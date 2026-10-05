# Review Response (Mode 9 — IN_REVIEW)

The workflow does not end when a PR is opened. Review is part of development (kernel:
"You must respond to those comments; ignoring reviewers is a good way to get ignored in
return"; Git: "Defend your design decisions on the list first"). This file governs the
loop from "review received" to "resolved". Worksheet artifact: assets/review-response.md.

## The loop

1. **Review received.** Read every comment before reacting. Note which are questions and
   which are change requests; note who said them (maintainer vs drive-by).
2. **Classify each concern.** Use the taxonomy below; a comment may carry two concerns —
   split it rather than averaging.
3. **Inspect before interpreting.** Re-read the relevant source, tests, and docs; pull
   evidence from the evidence manifest. A concern about behavior the patch did not
   change gets checked against the pre-patch code, not assumed away.
4. **Explain the concern to the contributor.** What the reviewer actually challenges —
   often not what the words literally say ("this test is fragile" may challenge the
   fixture, not the fix). Use the REVIEWER CONCERN / INTERPRETATION / EVIDENCE / ACTION
   progress block (SKILL.md).
5. **Decide: CHANGE or JUSTIFY (or QUESTION, if intent is unclear).** Never automatic
   agreement — evaluate each concern against evidence. Where the existing implementation
   is technically justified, prepare a respectful, evidence-backed response and say what
   would change your mind. Where the reviewer is right, say so plainly and fix it.
6. **If CHANGE:** re-enter the state machine at PATCH. The concern may add a test (test
   coverage → RED→GREEN discipline applies), alter behavior, or restructure — the PATCH
   PLAN is updated first. Affected validation is now **stale**: re-run the affected
   levels and record them (see testing-strategy.md § Stale validation); regenerate the
   Validation Report; refresh the Change Walkthrough and the understanding status if the
   change is more than cosmetic.
7. **Prepare the response(s).** One concise reply per comment thread: what changed and
   why, or why not, with references. Drafts only — posting is REMOTE_WRITE.
8. **Update the evidence record.** New manifest entries, updated worksheet, revision
   baseline for the next round.

## Concern taxonomy

| Category | Typical right action |
|----------|----------------------|
| correctness | re-check evidence; change unless provably justified |
| design | justify with evidence or adapt; may need PATCH PLAN restructure |
| scope | check against diff budget/plan; trim or justify the breadth |
| test coverage | add the test (RED→GREEN); this is almost always a change |
| compatibility | verify against pinned users/docs; guard, test, or document |
| style | follow repository convention; local rules win |
| documentation | small fix; update commit message/docs with it |
| maintainability | weigh against minimum-change; refactor only with demonstrated need |
| question / clarification | answer with evidence; no code change unless the answer reveals one |

## Response discipline

- Answer **every** meaningful comment, even the ones you decline (LLVM treats
  unacknowledged feedback as blocking; Git: "Before sending another version, make sure
  you have answered meaningful review comments in the existing discussion").
- Never let a push be the only response (Git: reply in the discussion, not just with a
  new revision).
- One revision note per round; do not send more than one new version per day (Git) —
  batch and verify before resubmitting.
- Tone: polite, specific, evidence-linked. No defensiveness, no capitulation — both are
  dishonesty. "You're right, fixed" is a fine sentence.
- If the PR is abandoned, say so explicitly and close it — stale open work costs
  maintainers context.

## Iteration summary (every v2/v3)

Each revision starts with a summary the reviewer can follow without archaeology —
Git cover-letter rule: "give a summary of changes since the previous rounds":

> **Reviewer concern** → **what changed** → **evidence** → **what did not change, and
> why.**

Keep it self-contained: name the comment (or quote its gist), state the decision, link
the new test/artifact. Multiple rounds stack newest-first. This is the same principle as
the commit message: readers years from now reconstruct why the code is what it is from
these records — write for them, not just for this reviewer.
