# External Backend Grounding (V6 Phase 0, extended V7)

Verified 2026-10-06 against live upstream sources. Research levels:
PAPER_VERIFIED < REPO_VERIFIED < IMPLEMENTATION_VERIFIED < MECHANISM_REPRODUCED < INTEGRATED.
A system is never labeled "researched" below without its implementation entry points.

Integration status summary: **AOCI runtime client = INTEGRATED** (against our
contract-conformant service; official binary not bundled) · **symbol backend =
INTEGRATED** (stdlib python-ast first implementation; Serena adapter present,
dormant until configured) · **V7 adds deterministic cores of four more systems**
(see §V7 at the bottom: LocAgent four-edge graph, RepoGraph artifact pattern,
CoSIL two-stage skeleton, AutoCodeRover search API — all MECHANISM_REPRODUCED
over CPython ast, no downloads, no new parser) · SWE-agent ACI and OpenHands
condenser remain **NOT integrated** (not applicable to this skill's shape); the
ledger (CAPABILITIES.json) records every status explicitly.

## 1. AOCI (AOCI-CODE)

- **Repository:** https://github.com/aoci-spec/aoci-code (Go, FSL-1.1-MIT; canonical
  self-declared in `internal/machinecontract/capabilities.go`).
- **Sources inspected:** `internal/mcptools/server.go`, `tools_read.go`,
  `overview_delivery_v1.go`, `overview_attestation_v1.go`, `cognition.go`,
  `internal/baseline/detect.go`, `spec/public/aoci-mcp-runtime-v1.txt`,
  `aoci-overview-delivery-v1.txt`, `aoci-cognition-volumes-v1.txt`,
  `aoci-object-fras-v2.txt`, `textassets/en-US/contracts/mcp/*`
  (commit `3604ce4`, 2026-10-06). Paper arXiv 2605.02421.
- **Mechanism verified:** stdio MCP server, `serverInfo.name="aoci-code"`; nine
  pinned tools whose sorted-LF surface digest (trailing newline) is
  `b4a56cb6…98176e`; `aoci_rules` → `aoci_overview` chunked whole-index delivery
  (`cursor="start"` → `next_cursor`, `completed`/`continuation_required`,
  per-chunk `chunk_sha256`/`index_sha256`, final-chunk attestation challenge:
  `challenge_ordinals`/`challenge_digest`, ≥80% pass, F graded with Jaccard ≥ 0.6,
  `host_delivery_confirmation` as second proof half); identity =
  length-framed composite `index_sha256` + `refresh_generation`;
  `aoci_search` (keyword/tag_filter, ≤30) and `aoci_get_entries` (paths/dir,
  stale/unbaselined via `.aoci/baseline.json` SHA-256 binding). Whole-index-
  before-search is a CONTRACTUAL prohibition, not server-enforced.
- **Level:** upstream IMPLEMENTATION_VERIFIED; our conformance service
  MECHANISM_REPRODUCED; client `scripts/aoci_runtime.py` + router receipt
  consumption INTEGRATED.
- **Reuse:** the runtime contract and lifecycle duties (surface pinning, cursor
  chain, attestation, receipt identity/drift gating, explicit fallback).
- **Not reproduced:** the Go implementation, authoring/write pipeline
  (maintain/update/remove batches, CAS/Ledger), FRAS authoring itself
  ("model owns meaning"), and we do NOT claim conformance service = official
  runtime — `serverInfo.name` stays "aoci-conformance".

## 2. Aider RepoMap

- **Repository:** https://github.com/Aider-AI/aider (canonical; paul-gauthier/aider
  resolves here).
- **Sources inspected:** `aider/repomap.py` — `get_repo_map`, `get_tags_raw`
  (tree-sitter `.scm` captures + Pygments ref backfill), `get_ranked_tags`
  (NetworkX MultiDiGraph + personalized `nx.pagerank`), binary-search map sizing
  vs token budget.
- **Level:** REPO_VERIFIED. **NOT integrated.**
- **Reuse:** the personalization idea (query/chat-mentioned identifiers weighted up).
- **Not reproduced:** tree-sitter defs/refs semantics, 30+-language `.scm` corpus,
  SQLite mtime cache. Our `graph_pagerank_prior` is a **lightweight structural
  PageRank over import/test file edges** — the ledger now says exactly that; it is
  NOT "RepoMap".

## 3. Serena

- **Repository:** https://github.com/oraios/serena (GPL-3.0-or-later).
- **Sources inspected:** `src/serena/tools/symbol_tools.py` (`FindSymbolTool`,
  `FindReferencingSymbolsTool`, `GetSymbolsOverviewTool`, …),
  `src/serena/ls_manager.py`.
- **Level:** REPO_VERIFIED. **Adapter present, dormant** (`SERENA_MCP_COMMAND`
  config path in `scripts/symbol_backend.py`); not runnable here (no downloads),
  so the running backend is python-ast — recorded honestly in every result row.
- **Reuse:** the tool progression overview → find_symbol → find_referencing_symbols.
- **Not reproduced:** the multi-language LSP matrix; GPL code is not copied.

## 4. LocAgent

- **Repository:** https://github.com/gersteinlab/LocAgent (ACL 2025, arXiv 2503.09089).
- **Sources inspected:** `dependency_graph/build_graph.py` — `CodeAnalyzer(ast.NodeVisitor)`,
  `build_graph` → MultiDiGraph, node types directory/file/class/function, edge
  types contains/imports/inherits/invokes. **Correction:** the implementation uses
  Python's `ast`, not tree-sitter (earlier claim corrected).
- **Level:** REPO_VERIFIED. **NOT integrated.**
- **Reuse:** the four-edge taxonomy as a design reference for future symbol edges.
- **Not reproduced:** the graph build/traversal stack; matplotlib visualization.

## 5. RepoGraph

- **Repository:** https://github.com/ozyyshr/RepoGraph (ICLR 2025, arXiv 2410.14684).
- **Sources inspected:** `repograph/construct_graph.py` — `CodeGraph`,
  tree-sitter tags → MultiDiGraph → `graph.pkl` + `tags.json`; header states it is
  adapted from Aider RepoMap/Agentless/grep-ast.
- **Level:** REPO_VERIFIED. **NOT integrated.**
- **Reuse:** index/build decoupled from inference (artifact sidecar pattern —
  mirrored by our spans/session artifacts).
- **Not reproduced:** source-rewriting heuristics and `exec()`-based import probing.

## 6. CoSIL

- **Repository:** https://github.com/ZhonghaoJiang/CoSIL (ASE 2025, arXiv 2503.22424).
- **Sources inspected:** `CoSIL/fl/CoSIL.py` — two-stage `file_localize` →
  `_localize_with_native_tools` → `localize_line`; `prune_tool_result` relevance
  sub-agent; **explicit `exit` tool** as the termination path; token-budget guard.
- **Level:** REPO_VERIFIED. **NOT implemented** (explicitly out of scope this goal;
  ideas recorded in research synthesis §13 only).
- **Reuse:** explicit exit signal; prune-before-main-context (future goals).
- **Not reproduced:** the iterative exploration loop; benchmark scaffolding.

## 7. Agentless

- **Repository:** https://github.com/OpenAutoCoder/Agentless.
- **Sources inspected:** repo tree — `agentless/fl/FL.py`, `agentless/repair/repair.py`,
  `agentless/repair/rerank.py`, `agentless/test/*`, `get_repo_structure/`.
- **Level:** REPO_VERIFIED. **NOT integrated** (hierarchical-funnel thinking is
  cited in research only).
- **Reuse:** funnel + candidate reranking principle.
- **Not reproduced:** the pipeline; Python/pytest hard-coding; precomputed
  repo-structure dumps.

## 8. AutoCodeRover

- **Repository:** https://github.com/nus-apr/auto-code-rover (ISSTA 2024).
- **Sources inspected:** `app/main.py`, `app/search/search_manage.py`
  (`SearchManager`, reflective dispatch), `app/search/search_utils.py`
  (per-file AST index), `app/agents/agent_search.py` (SBFL via `config.enable_sbfl`).
- **Level:** REPO_VERIFIED. **NOT integrated** (no spectrum-based localization here).
- **Reuse:** closed reflective tool-dispatch surface.
- **Not reproduced:** Docker/experiment infra; SBFL.

## 9. SWE-agent

- **Repository:** https://github.com/SWE-agent/SWE-agent (NeurIPS 2024 ACI paper).
- **Sources inspected:** `config/default.yaml` (tool bundles), `tools/windowed/*`
  (bounded viewer: open/goto/scroll), `tools/windowed_edit_linting/bin/edit`
  (lint-guarded edit), `tools/search/`.
- **Level:** REPO_VERIFIED. **NOT integrated** — our session state machine is
  interface-discipline *inspired* by ACI, not an ACI runtime; ledger says so.
- **Reuse:** bounded views + machine-checked feedback loops (already embodied in
  evidence witnessing).
- **Not reproduced:** the shell tool surface; SWE-bench grading hooks.

## 10. OpenHands (brief)

- **Repository:** https://github.com/All-Hands-AI/OpenHands.
- **Verified:** condenser/history-compression exists and is config-driven
  (`LLMSummarizingCondenser`, `RecentEventsCondenser`); the historical
  `openhands/memory/condenser/condenser.py` path 404s on current main
  (refactored into the SDK) — current file path UNVERIFIED.
- **Level:** PAPER_VERIFIED (+ partial repo). **NOT integrated.**

## What this grounding changed in the Skill

- `scripts/mcp_stdio_client.py` — generic MCP stdio client (transport INTEGRATED).
- `scripts/aoci_runtime.py` — AOCI_RUNTIME client (INTEGRATED; lifecycle per §1).
- `scripts/aoci_conformance_server.py` — our contract-conformant service
  (MECHANISM_REPRODUCED; never claims to be the official binary).
- `scripts/symbol_backend.py` — symbol interface; python-ast INTEGRATED, Serena
  adapter dormant-until-configured.
- `scripts/retrieval_router.py` — consumes both via persisted receipts/artifacts
  with per-candidate provenance.
- `CAPABILITIES.json` v6 — renames `graph_pagerank_prior` evidence to
  "lightweight structural PageRank"; adds explicit NOT-integrated entries for
  LocAgent/RepoGraph/CoSIL/Agentless/AutoCodeRover/SWE-agent/OpenHands.

## V7 extension (2026-10-06) — deterministic cores reproduced over the real backends

The V6 goal gated these behind "only after this integration is real"; the
integration is real, so V7 reproduced four mechanisms as deterministic cores.
None of them required downloads, a new parser (CPython `ast` is stdlib), or a
new retrieval algorithm — every stage composes the V6 backends.

| Upstream | V7 deliverable | Level before → after | What is and is NOT claimed |
|---|---|---|---|
| LocAgent four-edge taxonomy | `symbol_backend.py graph/trace`: contains/imports/inherits/calls nodes+edges over CPython ast (the same parser LocAgent's build_graph.py uses), bounded distance-decayed traversal | REPO_VERIFIED → MECHANISM_REPRODUCED | call/inheritance targets are resolution=name-match (candidate edges); LocAgent's full name resolution is NOT reproduced |
| RepoGraph artifact pattern | symbol_graph.json offline build, decoupled query sidecar (graph.pkl analog) | REPO_VERIFIED → MECHANISM_REPRODUCED | no tree-sitter, no exec() probing; build/query decoupling reproduced |
| CoSIL two-stage localization | `localize_two_stage.py`: router breadth (stage 1) → symbol/graph iterative depth (stage 2) with explicit exit reasons (SUFFICIENT_EVIDENCE / BUDGET / NO_EVIDENCE) | REPO_VERIFIED → MECHANISM_REPRODUCED | deterministic skeleton only — no LLM loop, no relevance sub-agent, no dynamic graph construction |
| AutoCodeRover search API | `symbol_backend.py search`: mode=class/method/code/method-in-class, bounded rows, exact AST spans | REPO_VERIFIED → MECHANISM_REPRODUCED | closed API surface reproduced; SBFL and the agent loop NOT reproduced |
| SWE-agent ACI / OpenHands condenser | — | unchanged | remain NOT integrated (interface-compression ideas already embodied in evidence witnessing / budget governor; no ACI runtime, no condenser component exists here) |

Router consumption: `retrieval_router.py` lifts graph calls/inherits/imports
edges to file level and feeds them into bounded expansion with relation labels,
so graph-reached candidates now carry "calls/inherits <file>" provenance.

Real-run evidence: `oss-contribution-engineer-dev/runs/v6-backend-integration-runs.json`
scenario `structural_graph_and_two_stage_localization` (448 nodes / 3199 edges
over the skill's own source; trace cmd_advance bounded at BUDGET; two-stage
localization SUFFICIENT_EVIDENCE → cmd_advance at scripts/contribution_session.py
L799-848, digest-bound).
