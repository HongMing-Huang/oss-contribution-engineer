# AI-Assisted Development Policy

This skill produces AI-assisted contributions. Mature projects have converged on rules
for this; violating them gets submissions rejected without review.

**Contents:** [The 2025–26 "AI slop" wave](#the-202526-ai-slop-wave-grounding-not-decoration) ·
[Ownership](#ownership) · [Legal certification](#legal-certification) ·
[Disclosure](#disclosure) · [Truth in testing](#truth-in-testing) ·
[Authorization boundaries](#authorization-boundaries) · [Auditability](#auditability)

## The 2025–26 "AI slop" wave (grounding, not decoration)

The dominant community complaint is **cost asymmetry**: AI made generating
submissions nearly free while human review stayed expensive. curl found ~20% of
its security reports were AI-generated false positives and retired its $90K bug
bounty over it ([curl AI guidelines, May 2025](https://curl.se/mail/lib-2025-05/0013.html));
Godot and ITK maintainers reported being overwhelmed by low-quality AI PRs; OCaml
maintainers rejected a 13,000-file AI PR outright; GitHub began prototyping
maintainer-side controls against slop volume (Feb 2026). The human cost is real:
a long-time kernel maintainer stepped down after being inundated with
AI-generated submissions (Oct 2026).

**The kernel's position moved — and that is the lesson.** Jan 2025: the kernel
required LLM disclosure (`Assisted-by:`). 2026: Torvalds called banning
AI-generated code "utterly stupid" — tools are a poor proxy for whether a
contributor understands their work; the failing mode he names is **"vibe
coding": submitting code you do not understand**, not using assistance. Oct
2026: the kernel **dropped the mandatory disclosure rule**, and Torvalds posted
his own first LLM-assisted patch (a synthetic test, reported ~23× faster).
The bar never moved: quality, understanding, human ownership. **Policies
change; recon must read the project's CURRENT AI policy, never assume one
from memory or from this file.** The rules below exist so that a run of this
skill is on the right side of every one of those lines.

**Serial-contribution rule (the missing rule the slop wave exposed):** one open
contribution at a time per project, resolved or closed before the next opens; and
never generate submission volume the human cannot personally review end-to-end
before authorizing. A flood of individually-acceptable PRs is still slop.

## Ownership

- The **human contributor owns the submission** — every line, every claim, every test.
- "You are expected to understand and to be able to defend everything you submit"
  (kernel, generated-content.rst). If the human cannot explain the change, the skill's
  job is to help them review it, not to submit it anyway.
- At the CONTRIBUTOR_UNDERSTANDING stage, produce the Change Walkthrough
  (assets/change-walkthrough.md) and run the **Explain-Back check** — a conversation,
  not an exam. The human should be able to answer, in their own words:
  1. What is the bug/problem?
  2. How does the affected code currently work?
  3. Why does the patch fix it?
  4. Why did the test fail before the fix?
  5. What is the main regression risk?
- Incomplete understanding → explain the missing concept, show the relevant code path,
  continue. One concept at a time. Record the outcome as UNDERSTOOD (only on the
  human's explicit confirmation — the agent never claims it), DEFERRED, or INCOMPLETE
  (gaps named). A DEFERRED or INCOMPLETE status never blocks reporting honestly, but
  must never be laundered into "contributor understands".
- AI-generated code is not accepted merely because CI is green.

## Legal certification

- **Never add sign-offs, DCO certifications, CLA acceptances, or legal attestations on
  behalf of a human.** The kernel forbids AI agents from adding `Signed-off-by`; the DCO
  is a human certification of origin. The human adds it themselves, after review.
- Co-authored-by / attribution follows the repository's convention; the human decides.

## Disclosure

- Respect the repository's CURRENT AI policy (recon surfaces it: CONTRIBUTING
  sections, AGENTS.md, AI contribution policies) — **current, as of this run**:
  policies reverse (the kernel required disclosure Jan 2025 and dropped it Oct
  2026). Where disclosure is required, disclose exactly as required (tools,
  prompts or summaries, affected parts, testing) or stop. Projects that ban AI
  contributions outright — the answer is to stop and tell the user.
- **Default posture — a mature engineer, not a labeled bot.** When the policy is
  silent (most projects): NO unsolicited AI markers. No "generated with…",
  no AI Co-authored-by, no preamble about tooling. The human owns every line and
  takes full responsibility (Linus's bar: quality + understanding + ownership —
  he opposes "vibe coding", not assistance, and shipped an LLM-assisted patch
  himself); a competent human using assistance is the community norm. Volunteered
  AI labels are themselves noise maintainers dislike.
- Two hard lines that never bend: if a project's current policy requires
  disclosure, disclose; if a maintainer asks directly whether AI was involved,
  answer honestly. Misrepresenting authorship when asked is the one thing that
  turns normal assistance into a ban.
- **Bug/security reports must be "security informed"** (curl's term): the submitter
  must actually understand the issue they report. An AI-suggested vulnerability the
  human cannot explain — reproducer, impact, affected path — is not reported. This is
  the exact failure mode that flooded curl: reports about code the submitter never
  read. The Explain-Back check applies to upstream REPORTS, not just patches.

## Truth in testing

- Never fabricate test results, benchmarks, or "verified on" claims. The evidence
  manifest exists so results come from executed commands.
- Disclose limitations: what was not tested, environments not covered, levels recorded
  SKIPPED/UNAVAILABLE in the Validation Report.
- Preserve investigation records (evidence artifacts, reproducer scripts) when they
  would help maintainers audit the claim — attach or link them per project convention.

## Authorization boundaries

- The skill may prepare drafts automatically: PR text, issue text, comments, patches.
- Publishing any of them — commenting, opening issues, pushing branches, opening PRs —
  requires explicit user authorization for that specific action (REMOTE_WRITE). The
  agent never sends anything itself (kernel's rule for assistants applies verbatim).

## Auditability

- Keep the evidence manifest with the working notes for the contribution; it is the
  difference between "trust me" and "here is the record".
- When a tool materially shaped the change (e.g., a static analyzer found the bug), say
  so — maintainers use that signal to calibrate review depth.
