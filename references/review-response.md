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
4. **Explain the concern to the contributor** — before any upstream reply is drafted —
   using the 5-part review block:
   **REVIEWER CONCERN** (what the reviewer is actually worried about) / **CODE CONTEXT**
   (which code or design assumption the comment refers to) / **ASSESSMENT** (agree,
   partially agree, disagree) / **EVIDENCE** (what source, test, history or contract
   supports that assessment) / **ACTION** (what will change, or why no change is
   appropriate). The contributor must understand the response they are about to send.
   Often the words say one thing and the challenge is another ("this test is fragile"
   may challenge the fixture, not the fix).
5. **Decide: CHANGE or JUSTIFY (or QUESTION, if intent is unclear).** Never automatic
   agreement — evaluate each concern against evidence. Where the existing implementation
   is technically justified, prepare a respectful, evidence-backed response and say what
   would change your mind. Where the reviewer is right, say so plainly and fix it. A
   **design** objection is resolved in discussion *before* rewriting code (Git: defend
   or adapt the design on the list first; topics with unresolved fundamental design
   critiques are not ready to merge).
6. **If CHANGE:** re-enter the state machine at PATCH. The concern may add a test (test
   coverage → RED→GREEN discipline applies), alter behavior, or restructure — the PATCH
   PLAN is updated first. Affected head-bound evidence is now **STALE**: the Validation
   Report marks it (exit 5) and lists files changed since; rerun the affected levels,
   re-record at the new HEAD, regenerate the report (testing-strategy.md § Stale
   validation). Refresh the Change Walkthrough and the understanding status if the
   change is more than cosmetic. Push fixes as **new commits, not squashed**, so
   reviewers can diff exactly the revision (Kubernetes rule; squash only when asked).
7. **Prepare the response(s).** One concise reply per comment thread: what changed and
   why, or why not, with references. Drafts only — posting is REMOTE_WRITE.
8. **Signal readiness for another review.** After all comments are addressed and
   evidence re-recorded, explicitly request re-review — re-request reviewers or comment
   PTAL ("please take another look") per the project's convention; do not assume
   reviewers noticed the push. Only then is the PR READY_FOR_REREVIEW.
9. **Update the evidence record.** New manifest entries, updated worksheet, revision
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

## Upstream outcome classification (terminal, evidence-bound)

Never end a run at "PR opened", and never report `closed=true` as success. Classify the
end state from captured platform data (`upstream_state.py classify` on captured
PR/reviews/timeline JSON; `upstream_state.py commands` prints the capture commands):

| Outcome | Meaning | Typical closure signal |
|---------|---------|------------------------|
| MERGED | the only success terminal | state=closed, merged=true |
| CLOSED_NOT_MERGED | rejected / maintainer-closed | closed without merge by a non-author |
| SUPERSEDED | another PR/commit took over | cross-reference "superseded by #N" |
| WITHDRAWN | the author closed it themselves | closer == author |
| DROPPED_OR_STALE | died of inactivity | stale label, bot closure (k8s: 90-day rule; Git: 4 weeks with unaddressed comments) |
| WAITING_FOR_REVIEW | open; fixes pushed but readiness not signaled (or no review yet) | no re-review signal after push |
| CHANGES_REQUESTED | open; latest review blocks, head unchanged since | review state + no commits after |
| READY_FOR_REREVIEW | fixes pushed AND validation re-recorded AND re-review explicitly signaled (PTAL / re-request) | author signal after push |

Ambiguity policy: when the capture cannot distinguish (no timeline, unknown closer),
the classifier says so and picks the more-honest branch — never MERGED, never
READY_FOR_REREVIEW without a signal. Record the classification, the facts behind it, and
the final iteration summary; a CLOSED_NOT_MERGED that produced a good investigation and
a polite withdrawal is an acceptable ending — a misreported one is not.

Operational behaviors encoded here (kernel/Git/Kubernetes, distilled): review is part of
development; design objections are settled before re-implementing; every meaningful
comment gets an answer; each revision explains what changed and what did not; reviewer
time is scarce (small self-contained changes, one revision per day, weekly pings max);
readiness for re-review is signaled explicitly, never assumed; inactivity, rejection,
supersession, withdrawal and merge are different endings with different names.
