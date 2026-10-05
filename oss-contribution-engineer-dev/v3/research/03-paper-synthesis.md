# Paper Synthesis (research output 3)

Paraphrased synthesis; links inline. Grouped by what each line of work contributes to
V3's design decisions.

## 1. Retrieval generation iteration — RepoCoder (Zhang et al., arXiv 2303.12570)

Iterate retrieve-then-generate: embed query + previous generation per line-chunk, fetch
top-k, regenerate. Contributions: unified repository symbol chunking; demonstration that
**naive one-shot top-k chunk retrieval is far below iterated retrieval** (EM convergence
in ~2 rounds). V3 takeaway: retrieval is a loop with an early-exit condition, not one
call — maps to our radius expansion with "every expansion must have a reason".

## 2. Interface-centric agency — SWE-agent (Yang et al., NeurIPS 2024, arXiv 2405.15793)

Agent-Computer Interface design (bounded file viewer, search, edit-guarded-by-linter)
moves SWE-bench resolve rates substantially; ablations show interface choices dominate.
V3 takeaway: our Context Pack and protocol formats are *interfaces*; keep outputs small,
structural, machine-checkable (Goal Card, FOUND, PATCH INTENT, RESULT blocks).

## 3. No-agent pipelines have a precision/cost niche — Agentless (Xia et al., arXiv 2407.01489)

Hierarchical localization (structure→file→element) + repair + validation without an
agent loop; cheap and competitive. LocAgent's follow-up shows the ceiling: Agentless is
worst-in-class once hops beyond mentioned symbols are needed. V3 takeaway: deterministic
pipelines are the right *fallback backend*; agentic exploration is the right *expansion*
step when evidence is insufficient.

## 4. Structure-aware search and tests — AutoCodeRover (Zhang et al., arXiv 2404.05427)

AST-aware searches (class/method/related) beat plain code search; spectrum-based fault
localization uses failing/passing tests as signal. V3 takeaway: test relationships are a
retrieval signal family (tests→source), and task classifiers that know the test status
route differently (bug_hunt vs code2test).

## 5. Graph-guided localization — LocAgent (Chen et al., ACL 2025, arXiv 2503.09089)

Heterogeneous directed graph (directory/import/inheritance/invocation), topology
features (PageRank, degrees), agent tools search_entity/explore_graph/retrieve_graph;
strict top-k "all gold in top-k" metric; Loc-Bench adds task-type diversity
(bug/feature/security/performance) and contamination hygiene. Findings used directly:
- Agent-based > retrieval-based at every granularity; embedding rankers fail at
  function level *even when the function is named in the query*.
- Difficulty correlates with graph distance between mentioned and patched entities —
  motivating bounded multi-hop expansion with distance penalties.
V3: graph is one signal family + expansion mechanism, never the sole authority.

## 6. Graph-DB interfaces — CodexGraph (Xie et al., arXiv 2408.03989)

Offline extractor → Neo4j; agent issues schema-constrained queries. Flexible but
infrastructure-heavy. V3 chooses *bounded in-process expansion* (no DB dependency,
stdlib-only constraint) with the same schema discipline.

## 7. Plug-in repository graph — RepoGraph (Ouyang et al., arXiv 2410.14684)

Tree-sitter graph (import/inherit/invoke) exposed as a step-level API to existing
agents; consistent relative gains plugged into Aider/Agentless/OpenHands on SWE-bench
Lite. V3: graph expansion should be callable *mid-task*, not only at plan time.

## 8. Priority-scheduled localization — OrcaLoca (Yu et al., ICML 2025, arXiv 2502.00350)

Delta decomposition + priority scheduling + candidate pruning + impact integration for
SWE-bench Lite localization. V3's expansion queue is exactly this shape: candidates in a
priority queue, pruned by relevance/impact before any LLM read.

## 9. Selective retrieval and its calibration wall — Agent Retrieval Bench (arXiv 2607.24882)

Relevance = "what the agent needs next" over frozen base commits; 4 workflow tasks +
abstention subset. Load-bearing results for V3:
- **No retrieval family dominates**; per-task winners differ sharply → route by task
  type, fuse signals (RRF improves MRR/Recall@20 over every single family).
- **Abstention calibration is unsolved**: thresholds tuned with counterfactual
  wrong-repo controls collapse on natural no-gold cases (lexical 0.499→0.294). Therefore
  V3 supports NO_RELEVANT_LOCAL_CONTEXT *structurally* but must not pretend scores are
  calibrated probabilities; abstention factors are reported, defaults conservative.
- Logged agents miss all gold files on 27–35% → static retrieval + interactive
  exploration are complementary; seeds reduce exploration cost (seed pilot: higher F1,
  less post-seed exploration).
- BCY@B (budgeted context yield) is the right "gold under budget" metric — adopted.

## 10. Exploration evaluation — SWE-Explore (Zhang et al., arXiv 2606.07297)

Line-level ground truth from successful trajectories (core/optional, consensus+audit);
fixed line budget; metrics context_efficiency (r=0.95 with downstream resolve) and
first_useful_hit (r=0.928); **threshold effect: missing 25–50% of core context collapses
repair, moderate noise barely hurts**. V3: pack for recall of candidate evidence,
precision of *presentation*; line spans matter more than whole files; "useful lines /
delivered lines" adopted.

## 11. Agents as long-context processors — Cao et al. (arXiv 2603.20432)

Off-the-shelf coding agents with file-system tools beat dedicated long-context methods
on long-document QA/reasoning: long-context reasoning becomes *environment interaction*
(chunk, search, index, extract). V3's core principle ("never load the repository; obtain
minimum sufficient verifiable context through bounded operations") is the engineering
form of this finding — plus AOCI when a persistent whole-system view already exists.

## 12. Context compression as state management (2026 wave)

- **SWE-Pruner** (arXiv 2601.16746): goal-hint-conditioned line-level pruning middleware;
  23–54% token cut with equal/better success; syntax-preserving granularity matters.
- **SWE-Pruner Pro** (arXiv 2607.18213): the backbone's own representations already
  encode line importance — pruning signal can come from the agent itself.
- **AutoCompact** (arXiv 2610.02163): compaction = three decisions (when / what to keep
  / how to continue); judge-corrected trajectories; +9.2% on SWE-bench Verified. Length-
  triggered compaction mid-stage is a failure mode.
- **AttnCompress** (arXiv 2609.08318): structure-aware segmentation (PPL spikes) +
  rolling re-evaluation; stale exploration is the compressible bulk.
V3's compaction policy adopts the three-decision framing, the preserve-list (goal,
done_when, constraints, authority, decisions, evidence, source identities, next action),
and the discard-list (superseded hypotheses, duplicate tool output, verbose output
already represented by receipts).

## What we deliberately do NOT adopt

- Whole-repo packing (Repomix) — anti-pattern except tiny repos.
- Embedding-only retrieval (needs model deps; ARB shows per-task losers; and our
  portability constraint forbids model dependencies) — supported as an *optional*
  external signal via backend interface, never authoritative.
- Unbounded BFS over code graphs — LocAgent/OrcaLoca pruning lessons: priority queue,
  depth caps, distance penalties, token costs.
- Rebuilding a whole-repo semantic index when an aligned AOCI index exists (AOCI's
  own governance rule, which we inherit).
- Calibrated abstention scores (ARB negative result) — abstention is reported with
  factors and human-readable reasons, not a pseudo-probability.
