# V3 Validation Results

All executions really run on 2026-10-05 (macOS arm64, Python 3.14). Provenance rule
unchanged: nothing here without a recorded execution. Complements
`../validation-results.md` (V2) and `references/retrieval-evaluation.md` (methods).

## 1. Static conformance

- `python3 -m py_compile`: all **12** scripts OK (6 V2 + 6 V3).
- SKILL.md frontmatter: name matches directory, description **1013/1024** chars
  (trimmed from 1171 after adding large-codebase triggers — the spec cap caught a real
  overrun), body **404 lines** (<500).
- Frontmatter uses only spec fields; `metadata.context_law` carries the acquisition law.

## 2. Goal Compiler — executed

- `compile` on fd (fd#1919 investigation task): Goal Card rendered (GOAL/DONE/SCOPE/
  UNKNOWN/NEXT/AUTH), contract persisted to `.oss-contrib-evidence/goals/` with
  digest `b36dbf2a6dfe…`; authority compiled as read-only.
- **Observability gate**: contract with zero observable done_when rejected (exit 1)
  with sharpening guidance — "make it better" cannot become a task.
- `hypotheses` records kept separate from the immutable contract.

## 3. Retrieval Router — executed on real clones

- fd, trace2code query ("exclude … first search path … build_overrides"): `src/walk.rs`
  retrieved (lexical #1); hybrid fusion orders sibling `src/dir_entry.rs` first —
  per-signal provenance makes the disagreement visible. Backend detected
  NATIVE_PROJECT_MEMORY (goals present, no aoci volumes).
- fd, code2test query: `tests/tests.rs` ranked #1 (test-relations + path) ✓.
- click, issue2code ("write_usage breaks options at a hyphen"):
  `src/click/formatting.py` retrieved into top-5 (gold verified at line 158).
- Bugs found while testing, fixed, and recorded: repository-root directory skipped by
  the walker (`.` treated as hidden — nothing scanned); unbound `age` variable on
  shallow clones (git log with no sha line); walrus-in-comprehension SyntaxError.

## 4. Retrieval evaluation — first run (real numbers; historical)

> **Historical note**: this was the three-arm run BEFORE the `repomap` signal family
> existed. Its "hybrid" arm therefore differs from § 7's hybrid (which includes
> repomap and shifts numbers: click hybrid 0.300→0.411, fd 0.458→0.438, fd BCY
> 0.250→0.000). § 7 is the current five-arm matrix; this section is kept as the
> routing-policy record of what changed when the structural prior was added.

click (4 tasks) and fd (4 tasks), gold verified by grep/reproduction before use:

| Repo | Arm | MRR | Recall@5 | BCY@8k |
|---|---|---|---|---|
| click | hybrid (pre-repomap) | 0.300 | 0.625 | 0.375 |
| click | lexical+path | **0.590** | 0.625 | 0.375 |
| click | symbol+test | 0.250 | 0.250 | 0.250 |
| fd | hybrid (pre-repomap) | **0.458** | 0.625 | 0.250 |
| fd | lexical+path | 0.265 | 0.625 | 0.250 |

Per-task-type (hybrid): code2test Recall@5 = **1.0 on both repos**; fd trace2code
Recall@5 = 1.0, BCY@8k = 1.0; **failures recorded, not tuned away**: click
comment2context = 0.0 (docs dominate lexical for that query) and fd issue2code = 0.0
(CHANGELOG.md outranks walk.rs lexically).

**"More context makes it worse" case (mandated record):** rank_depth=20 whole-file
delivery averages ~100k estimated delivered tokens per task against a 12k source
soft-budget — while the Context Pack delivers the same decisive spans in 280–3k tokens.
Whole-file delivery is the anti-pattern the metrics exposed.

Defects found by the metrics, then fixed: (a) whole-file budget charging while
delivering only spans (dir_entry.rs, ~10.8k est. tokens, starved the gold walk.rs
span — pack now charges span size; source usage dropped to 280 est. tokens); (b) BCY
starvation behind an oversized single file (fd CHANGELOG ≈ 8.7k est. tokens > budget —
packer now skips files that cannot fit even alone; fd trace2code BCY@8k went 0 → 1.0).

## 5. Planner / Governor / Receipt chain — executed end-to-end on fd

`route → plan (R1 tiers + allocation) → pack (spans with digests + why) → governor
(within budgets) → receipt open/record-read/verify/close/reconstruct`. Verified:

- Pack spans bound to sha256 at read time; digest `ecce7c8330ee…`.
- Receipt binds base SHA `ce97e473ebae` + goal digest + backend identity; `verify`
  reports CURRENT/CHANGED/DELETED; **drift detection exercised**: after modifying a
  recorded file, `verify` flagged CHANGED and exited 1 ("re-read before any edit or
  claim").
- `reconstruct` emits the RECONSTRUCTED block from persistent state (post-compaction
  protocol), including unresolved question and next action.

## 6. Honest limitations

- Task sets are small seeds (8 tasks, 2 repos) built from real investigated cases —
  demonstration-grade, not benchmark-grade; scaling methodology documented in
  references/retrieval-evaluation.md.
- Abstention is reported with factors only; no calibration is claimed (ARB negative
  result).
- AOCI_NATIVE path validated for detection/parsing/alignment *logic* against the
  documented FRAS format, not against a live AOCI-managed repository (none available
  locally); the alignment check degrades honestly to `unverified` when baseline digests
  are absent.
- Embedding / Language-Server signals remain pluggable stubs (no model deps by design);
  the eval's embedding arm therefore does not run here — recorded as
  **UNAVAILABLE (documented)**, per the ablation requirement, alongside the four
  runnable arms.

## 7. Five-arm ablation matrix (RepoMap arm added; 2026-10-05)

`retrieval_router.py` gained a `repomap` signal family: PageRank (power iteration,
stdlib) over the file graph — importer→imported edges plus production→tests edges —
with query personalization (symbol hits ×3, top-10 lexical ×2, path hits ×1) playing
Aider's chat-file multiplier role. `Corpus` now parses imports for all files (previously
test files only — a prerequisite for the graph). Results (`--top-k 5,10`, BCY@8k,
saved under `v3/eval/results/`):

| Repo | Arm | MRR | Recall@5 | BCY@8k |
|---|---|---|---|---|
| click | lexical only | **0.625** | **0.875** | **0.875** |
| click | RepoMap only | 0.252 | 0.750 | 0.250 |
| click | symbol+test only | 0.250 | 0.250 | 0.250 |
| click | hybrid | 0.411 | 0.625 | 0.625 |
| fd | lexical only | 0.390 | 0.625 | **0.250** |
| fd | RepoMap only | 0.400 | 0.625 | 0.000 |
| fd | symbol+test only | 0.333 | 0.625 | 0.000 |
| fd | hybrid | **0.438** | 0.625 | 0.000 |
| both | embedding only | UNAVAILABLE (documented; pluggable arm, no model dependency) | | |

Findings: lexical wins click outright; hybrid wins fd MRR. The RepoMap arm surfaced the
import hub (`tests/testenv/mod.rs` #1 on fd) — and **adding it to the fd hybrid
regressed BCY@8k to 0.000**: hub files pack before gold under greedy first-fit packing.
Recorded as a measurable RepoMap hub risk and a routing-policy lesson (hub penalty for
trace2code-style tasks), deliberately not tuned away post-hoc.

## 8. End-to-end comparison — with vs without V3 context acquisition

Protocol per references/retrieval-evaluation.md, reusing V2 evaluation scenarios.
Two tasks, two arms each. **What was re-executed on 2026-10-05**: all V3-arm
acquisition steps (goal compile, route, plan, pack, governor, receipt) on both tasks,
and the V2-arm naive acquisition on Task B (grep + whole-file token accounting). **What
is reused, not re-run**: Task A's patch-phase rows (RED→GREEN, suite, scope audit) cite
the witnessed evidence recorded during the 2026-10-03 drill
(`../validation-results.md` § 3) — the patch gates are arm-independent (both arms run
the same V2 machinery after acquisition), so re-running the identical commands twice
would reproduce identical artifacts; the rows are marked "identical (same gates)" on
that basis, not on fresh dual execution. Arm "V2 path" = V2 acquisition (recon +
whole-file reads, no router/pack/receipt). Arm "V3 path" = goal_compiler →
retrieval_router → context_planner (plan+pack) → budget_governor → cognition_receipt,
then identical V2 gates.

### Task A — fixture patch task (divide-fixture; V2 eval scenario 3 reused)

| Dimension | V2 path | V3 path |
|---|---|---|
| Root-cause accuracy | correct (calc.py:divide) — after reading all 4 files | correct — router ranked calc.py #1, pack span `divide 5-8` |
| Regression-test quality | RED gate earlier caught a dead test; final test discriminating | identical (same test, same gates) |
| Patch scope | 2 files (+1/−1 prod, +9 test), WITHIN_SCOPE | identical diff |
| Patch correctness | GREEN + full suite PASS (witnessed) | identical |
| Validation success | INCOMPLETE (integration UNAVAILABLE, visible) | identical |
| Maintainer-quality review | adversarial checklist run; PR draft sections covered | identical + receipt/pack provenance attached |
| Context cost | whole files (fixture too small to differentiate) | **pack = 80 est. tokens** (2 spans) |

Interpretation (honest): on a tiny fixture the patch dimensions are identical — both
arms pass the same V2 gates, and V3 claims no patch-quality magic. V3's measurable
differences are process artifacts (goal contract, pack provenance, receipt) and scale
(see Task B).

### Task B — real-repo acquisition task (click, "locate write_usage hyphen breaking", READ_ONLY)

Gold: `src/click/formatting.py`, `def write_usage` at line 158 (grep-verified).

| Metric | V2 path (naive grep → whole-file reads) | V3 path (route → pack) |
|---|---|---|
| Exploration steps | 2 (grep; read both hit files whole) | 4 (compile, route, plan, pack) |
| Est. tokens delivered | **40,745** (formatting.py 2,611 + core.py 38,134 — core.py entirely unnecessary for the defect span) | **460** (one span) |
| Gold file reached | yes | yes (router rank #2; test file #1) |
| Gold span covered | yes, but only because the whole file was read | **yes — exactly `write_usage 158-203`** |
| Noise delivered | 38k tokens of unrelated core.py | none (excluded candidates listed) |
| Source identity binding | none | sha256 digest per span + receipt |

**Ratio: ~89× less delivered context with precise gold-span coverage.**

### Defects found by the E2E run (fixed; the reason this comparison is required)

1. Head-only span scan: the packer sampled only the first three file-top symbols, so
   `write_usage` (line 158) could never be packed → full-file symbol scan with
   name-preference selection now.
2. Separator-order tokenization: "usage-line" was stripped to "usageline" before
   splitting, making it unmatchable against "write_usage" → split on separators first.
3. RepoMap hub regression on fd BCY (see § 7) — recorded, not patched away.

### Conclusion

Better context ≠ more context. The V3 path matched every V2 patch-quality dimension
(identical gates) while cutting delivered context by ~89× on a real repository and
making gold-span coverage, provenance, and drift binding structural. The one measured
cost: the RepoMap prior needs task-aware hub penalties — an open routing-policy item,
recorded with data.
