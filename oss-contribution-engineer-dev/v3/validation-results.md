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

## 4. Retrieval evaluation — executed (real numbers; ablation)

click (4 tasks) and fd (4 tasks), gold verified by grep/reproduction before use:

| Repo | Arm | MRR | Recall@5 | BCY@8k |
|---|---|---|---|---|
| click | hybrid | 0.300 | 0.625 | 0.375 |
| click | lexical+path | **0.590** | 0.625 | 0.375 |
| click | symbol+test | 0.250 | 0.250 | 0.250 |
| fd | hybrid | **0.458** | 0.625 | 0.250 |
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
  the eval's embedding arm therefore does not run here.
