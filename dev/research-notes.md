# Research Notes — `oss-contribution-engineer`

Date: 2026-10-03. This is deliverable **A** (research findings) feeding the design in
[`design.md`](design.md) (deliverables **B–F**).

## 1. The Agent Skills standard (agentskills.io)

The open Agent Skills format (originated by Anthropic, now vendor-neutral and adopted by
Claude Code, OpenAI Codex, Cursor, Gemini CLI, GitHub Copilot/VS Code, Goose, Amp, OpenCode,
and dozens more) defines a skill as **a directory with a `SKILL.md`** plus optional
`scripts/`, `references/`, `assets/` subdirectories.

Key specification facts (from https://agentskills.io/specification and the
`agentskills/agentskills` repo docs):

- **Frontmatter**: required `name` (≤64 chars, lowercase alnum + hyphens, no
  leading/trailing/consecutive hyphens, **must match the parent directory name**) and
  `description` (1–1024 chars, must state *what the skill does* **and** *when to use it*;
  this field carries the entire triggering burden).
- **Optional frontmatter**: `license`, `compatibility` (≤500 chars, environment
  requirements), `metadata` (string→string map), `allowed-tools` (space-separated,
  marked **experimental** — support varies; do not rely on it).
- **Progressive disclosure**: agents load (1) name+description at startup (~100 tokens),
  (2) the full SKILL.md body on activation (recommended <5,000 tokens; the docs say
  **keep SKILL.md under 500 lines**), (3) bundled files only when referenced.
- **Validation**: the `skills-ref` reference library has a `validate` command that checks
  frontmatter and naming rules.
- **Discovery paths**: `.agents/skills/` is the cross-client standard; each client also has
  its own directory (Claude Code `~/.claude/skills/`, Cursor `.cursor/skills/`, etc.).
  Codex scans `.agents/skills` from the cwd up to the repo root — nested per-directory
  skills are supported.

**Codex-specific notes** (https://developers.openai.com/codex/skills): the initial skill
list is capped (~2% of context or 8,000 chars) and Codex **shortens descriptions** when
over budget — so trigger keywords must be **front-loaded** in the description. Codex also
supports an optional `agents/openai.yaml` for app metadata / invocation policy; it is not
required for portability.

**Claude Code-specific notes**: Claude Code rejects `name` values containing the reserved
words `anthropic`/`claude` and XML tags in name/description; it extends the spec with
non-portable fields (`disable-model-invocation`, `argument-hint`, `model`, hooks, etc.).
Portability rule adopted: **use only the spec fields in frontmatter**; document
vendor extensions separately.

## 2. Skill-writing practice from high-quality skills

Sources examined: the local `skill-creator` skill (ZCode), the local `writing-great-skills`
reference, Anthropic's official `anthropics/skills` repo (`template/SKILL.md` is minimal:
name + description only), the Trail of Bits security-research skill collection (skills +
repo-level `AGENTS.md`), and the `awesome-claude-skills` curated lists.

Principles adopted for this skill's authoring:

1. **The description is the trigger**, not documentation: front-load leading words
   ("contribute", "open-source", "issue", "bug", "PR"), enumerate distinct trigger
   branches, and state the anti-trigger ("not for ordinary local application development").
2. **Predictability over completeness**: every run should take the same *process*. The
   state machine and fixed gate vocabulary (recon → dedupe → prove → RED → patch → GREEN →
   validation → review) exist to make the process deterministic.
3. **Checkable completion criteria** on each step (e.g., "RED output is stored as
   evidence", not "verify the test").
4. **Progressive disclosure by branch**: inline what every branch needs; push
   branch-specific material behind pointers whose *wording* decides when it loads. Here:
   SKILL.md holds modes + gates + hard rules; `references/` holds methodology detail.
5. **Single source of truth; prune no-ops**; prefer positive phrasing ("record the
   failure output" rather than "do not claim success without output"), with hard
   guardrails (never fabricate) kept because they cannot be phrased positively.
6. **Leading words** recruit existing priors cheaply: *recon*, *dedupe*, *proof gate*,
   *RED*, *GREEN*, *diff budget*, *scope audit*, *adversarial review* are used as precise
   tokens throughout.

## 3. Contribution doctrines studied (paraphrased; sources linked)

### Linux kernel
- **AI coding assistants** —
  https://raw.githubusercontent.com/torvalds/linux/master/Documentation/process/coding-assistants.rst :
  AI-assisted contributions must carry an `Assisted-by: LLM [tools]` tag; **AI agents must
  not add `Signed-off-by`** (only humans certify the DCO); the human reviews everything and
  takes full responsibility; for non-trivial bugs a reproducer is expected ("unverified
  reports happen to be invalid"); a fix must be built and verified (no new warnings);
  contributors must explicitly state **what was not done** (no build, no test, no
  reproducer); the assistant **must never send anything itself**; fix commit needs a
  `Fixes:` tag.
- **Tool-generated content** —
  https://raw.githubusercontent.com/torvalds/linux/master/Documentation/process/generated-content.rst :
  disclose which tools were used, their inputs/prompts, which parts they affected, and how
  the result was tested; **"You are expected to understand and to be able to defend
  everything you submit"**; maintainers may reject tool-generated series without detailed
  review.
- **Submitting patches** —
  https://www.kernel.org/doc/html/latest/process/submitting-patches.html :
  every patch traces to a real problem with user-visible impact; one logical change per
  patch; never move code and modify it in the same patch; describe what testing was done;
  wait ~a week before pinging; supply the base commit.
- **Stable-tree rules** —
  https://www.kernel.org/doc/html/latest/process/stable-kernel-rules.html :
  backportable fixes must be obviously correct and tested, small (≈100 lines), and already
  present in mainline.

### Git
- **SubmittingPatches** —
  https://github.com/git/git/blob/master/Documentation/SubmittingPatches :
  `Signed-off-by`/DCO mandatory; the commit message must convey *why*; bug fixes need
  regression tests; avoid tree-wide cleanup noise; base work on the right branch; reply to
  every review comment; at most one new version per series per day; security patches go to
  the private security list.

### LLVM
- **Contributing** — https://llvm.org/docs/Contributing.html :
  reproduce bugs against current trunk (assertion build) before reporting; comment on an
  issue before starting to signal claiming; small isolated patches with a unit test each;
  format only changed lines (`git clang-format`); pick reviewers from `Maintainers.md`;
  ping politely once a week; security issues use a private process.
- **Code Review Policy and Practices** — https://llvm.org/docs/CodeReview.html :
  review before landing for significant changes; approval must be explicit (no silent
  LGTM); authors respond to all feedback; reviewers may demand a split; large design
  changes need an RFC first; authors are responsible for reverting promptly.

### Google Engineering Practices
- **Small CLs** — https://google.github.io/eng-practices/review/developer/small-cls.html :
  one self-contained change per CL; ~100 lines is reasonable, ~1000 usually too much;
  reviewers may reject purely for size; tests ship with the change; never break the build
  between stacked changes; separate refactoring from bug fixes.
- **What to look for in a code review** —
  https://google.github.io/eng-practices/review/reviewer/looking-for.html :
  review order: design → functionality (including **concurrency**, which is hard to
  detect by running) → complexity (warn against solving speculative problems) → tests
  (would they fail if the code broke?) → naming → comments (why, not what) → style.
- **CL descriptions** —
  https://google.github.io/eng-practices/review/developer/cl-descriptions.html :
  imperative first line; body explains problem and why this approach; descriptions are a
  permanent, searchable record; "Fix bug" is inadequate.

### Cross-doctrine synthesis (what the skill encodes)

1. Solve **real** problems; expected behavior must come from a source (spec, docs,
   maintainer statement, sibling behavior) — not from the reader's taste.
2. **Reproduce before fix**; an unreproducible claim is marked UNCONFIRMED, not patched.
3. **Regression test first** (RED on unmodified code) for behavior fixes; tests are
   reviewed for quality, not just executed.
4. **Minimum change**: one logical change per patch; no unrelated refactoring; no
   move+modify; format only what you touched; diff budget as a heuristic with explicit
   pause when exceeded.
5. **Verification is layered** (baseline → reproducer → RED/GREEN → neighbors → package →
   static → build → integration → live) and every command's result is recorded
   (EXECUTED/PASS/FAIL/SKIPPED/UNAVAILABLE). Never claim a result that was not executed.
6. **State what was NOT tested**; distinguish static checks from behavioral correctness.
7. **Human ownership**: the contributor must be able to explain and defend the change;
   AI never signs off (DCO), never publishes without authorization; disclosure follows
   repository policy (e.g., kernel `Assisted-by`).
8. **Maintainer time**: dedupe before working (open+unassigned ≠ free); inspect linked
   PRs, comments, assignments, recent history; claim with a plan; respect ping cadences;
   no speculative reports; security issues go private.

## 4. Implications for the skill design

- Build to the **spec subset** (name, description, license, compatibility, metadata);
  no `allowed-tools` reliance; all scripts stdlib-only Python 3 so they run anywhere the
  agent has python3 + git, and none of them touch the network (data capture is done by
  the agent's own permitted tooling, keeping provenance explicit).
- SKILL.md ≤500 lines holding: philosophy, hard rules, permission model, 8 modes, the
  11-state machine with gates, both workflows, script/artifact indexes.
- Methodology detail in 11 `references/` files loaded per branch; 6 deterministic
  `scripts/` for collection (never "semantics"); 6 `assets/` report templates.
- Anti-fabrication is structural where possible: results are produced by executing
  commands (`evidence_manifest.py record`), not by writing claims.
