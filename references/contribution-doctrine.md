# Contribution Doctrine

The engineering principles this skill encodes, paraphrased from mature projects. Read
once per repository. These are principles, not formatting rules — the target
repository's own conventions take precedence over anything here.

## 1. Solve real problems, not hypothetical ones

Every patch traces to a real problem with observable impact (Linux kernel,
[submitting-patches](https://www.kernel.org/doc/html/latest/process/submitting-patches.html)).
Reviews judge "is this a problem worth solving?" as much as implementation quality
(Git, [SubmittingPatches](https://github.com/git/git/blob/master/Documentation/SubmittingPatches)).
"Could be cleaner" is not a defect. Expected behavior needs a source: documented
behavior, protocol spec, maintainer statement, or the project's own tested behavior
elsewhere — never personal taste.

## 2. Reproduce before you claim

For non-trivial bugs the kernel expects a reproducer, and warns that unverified reports
"happen to be invalid"
([coding-assistants](https://raw.githubusercontent.com/torvalds/linux/master/Documentation/process/coding-assistants.rst)).
LLVM requires reproducing against current trunk with assertions enabled before reporting
([Contributing](https://llvm.org/docs/Contributing.html)). Static reading produces
hypotheses; execution produces evidence. If it cannot be reproduced, the claim is
UNCONFIRMED — say so and stop.

## 3. One logical change, small

Google: the right size is *one self-contained change*; ~100 lines is reasonable, ~1000
usually too much, reviewers may reject purely for size
([Small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html)).
Kernel: one logical change per patch; never move code and modify it in the same patch
(it destroys review and blame). Git: split separate concerns into separate commits; avoid
tree-wide cleanup noise. LLVM: isolated patches, format only changed lines
(`git clang-format`).

## 4. Tests are part of the change

Bug fixes need regression tests; new features need tests that show the feature working
*and* not triggering without it (Git). Tests ship in the same change (Google), and the
reviewer asks: would this test fail if the code broke? (Google,
[looking-for](https://google.github.io/eng-practices/review/reviewer/looking-for.html)).
A test that cannot fail, or that encodes the same wrong assumption as production, is not
evidence.

## 5. Static checks ≠ behavioral correctness, and neither replaces judgment

Lint, formatting, and type checks prove conformance, not correctness. Run both, report
both, and never present a clean linter as a passing test. State explicitly what was NOT
tested and what could not be executed (kernel requires stating undone verification).
Automated checks inform human judgment, never replace it: the kernel's Reviewed-by is a
human certifying the change is worthwhile and free of known issues — green CI cannot
certify anything, and AI-generated code is not accepted merely because CI is green.

## 6. Review is falsification — and part of development, not after it

Google's review order — design, functionality (concurrency especially: races are hard to
find by running), complexity (beware over-engineering for speculative needs), tests,
naming, comments (why not what) — is a checklist for finding defects
([looking-for](https://google.github.io/eng-practices/review/reviewer/looking-for.html)).
LLVM demands explicit approval, never silence; authors answer every comment. The
reviewer's job is to try to break the change, not to confirm it. Receiving review is the
same process from the other side: respond to every meaningful comment with evidence, in
the discussion, not just with a new revision (Git:
"You are expected to respond to them with 'Reply-All' … instead of letting an updated
patch series be your only response"; "Defend your design decisions on the list first").
Ignoring review ends conversations — kernel: "ignoring reviewers is a good way to get
ignored in return."

## 7. Descriptions are permanent records — write for future maintainers

Imperative first line; body explains the problem and why this approach; readers years
from now search for your change (Google, [CL descriptions](https://google.github.io/eng-practices/review/developer/cl-descriptions.html)).
"Fix bug" is inadequate. Git states the standard: "The goal of your log message is to
convey the *why* behind your change to help future developers" — the body explains the
problem, justifies the way the change solves it, and records the alternatives that were
considered and rejected. Kernel adds `Fixes:` tags and the base commit so reviewers know
where the change applies. Future maintainers must be able to understand why the code
exists without interviewing its author.

## 8. Respect maintainer time

Claim with a plan, not "I want to work on this" (LLVM: comment to signal you're starting,
after understanding). Ping politely at most weekly (LLVM), or one version per series per
day (Git). Security issues go to private reporting, never the public tracker (kernel,
Git, LLVM all agree). Never post speculative bug reports or competing PRs.

## 9. AI-assisted work has extra duties

The kernel requires an `Assisted-by` tag, forbids AI from adding `Signed-off-by` (only
humans certify origin), demands disclosure of tools/prompts/affected parts/testing, and
holds that "you are expected to understand and to be able to defend everything you
submit"
([generated-content](https://raw.githubusercontent.com/torvalds/linux/master/Documentation/process/generated-content.rst),
[coding-assistants](https://raw.githubusercontent.com/torvalds/linux/master/Documentation/process/coding-assistants.rst)).
Git rejects AI content that is unexplainable "slop". Details: ai-assisted-development.md.

## 10. Stopping is a contribution

When the bug is already fixed upstream, invalid, duplicated, or a design question,
the correct output is that conclusion with evidence — not a patch anyway. Kernel stable
rules apply the same spirit: only obviously correct, tested, already-mainline changes
belong in stable trees
([stable-kernel-rules](https://www.kernel.org/doc/html/latest/process/stable-kernel-rules.html)).

## 11. The problem comes first — before the implementation

Kernel rule, verbatim: "Describe your problem. Whether your patch is a one-line bug fix
or 5000 lines of a new feature, there must be an underlying problem"
([submitting-patches](https://www.kernel.org/doc/html/latest/process/submitting-patches.html)).
Every artifact — investigation, issue, PR, commit message — states the problem and its
user-visible impact before any implementation detail, and states expected downsides so
the reviewer "can weigh costs against benefits". A patch that cannot explain the problem
it solves is not ready to propose, however clean the diff.

## 12. Understanding is part of the submission

Kernel: "You are expected to understand and to be able to defend everything you submit.
If you are unable to do so, then do not submit the resulting changes"
([generated-content](https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/plain/Documentation/process/generated-content.rst));
maintainers may "ask the submitter to explain in more detail … so that the maintainer
can be assured that the submitter fully understands how the code works." Git rejects
content "that senders don't understand or cannot explain". For AI-assisted work this is
the hard boundary: the agent may draft, test, and explain, but understanding and
ownership live with the human — the skill's job is to make that understanding real
(walkthrough, explain-back), never to simulate it.


## Doctrine freeze (V5.3)

The doctrine above is now closed and represented as engineering lenses:

REAL PROBLEM · REPRODUCE · ONE LOGICAL CHANGE · DATA/RELATIONSHIPS ·
SIMPLE OVER CLEVER · READABILITY · COMPLEXITY DELTA · TWO HATS ·
HUMAN OWNERSHIP · REVIEW AS COLLABORATIVE DESIGN · MAINTAINER TIME

New developer quotations are not added after this point unless they expose a
genuinely missing engineering rule. New mechanics land as executable gates and
tests, not as new prose.
