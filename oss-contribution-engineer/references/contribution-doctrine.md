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

## 5. Static checks ≠ behavioral correctness

Lint, formatting, and type checks prove conformance, not correctness. Run both, report
both, and never present a clean linter as a passing test. State explicitly what was NOT
tested and what could not be executed (kernel requires stating undone verification).

## 6. Review is falsification

Google's review order — design, functionality (concurrency especially: races are hard to
find by running), complexity (beware over-engineering for speculative needs), tests,
naming, comments (why not what) — is a checklist for finding defects
([looking-for](https://google.github.io/eng-practices/review/reviewer/looking-for.html)).
LLVM demands explicit approval, never silence; authors answer every comment. The
reviewer's job is to try to break the change, not to confirm it.

## 7. Descriptions are permanent records

Imperative first line; body explains the problem and why this approach; readers years
from now search for your change (Google, [CL descriptions](https://google.github.io/eng-practices/review/developer/cl-descriptions.html)).
"Fix bug" is inadequate. Kernel adds `Fixes:` tags and the base commit so reviewers know
where the change applies.

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
