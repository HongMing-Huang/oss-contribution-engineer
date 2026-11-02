# Task Cognition Receipt Schema (research output 13)

The receipt is the persistent, digest-bound record of what an agent task actually knew
and read. Its purpose: **reconstruction after model context compaction** (and audit).
Model memory is not proof that repository cognition is still available.

## Schema (v1)

```jsonc
{
  "receipt_version": 1,
  "task_id": "...",
  "repository": "<url|slug>",
  "base_sha": "<git rev-parse HEAD at open>",          // + branch
  "goal_digest": "<sha256 of Goal Contract>",
  "cognition_backend": {"kind": "AOCI_NATIVE|NATIVE_PROJECT_MEMORY|LIGHTWEIGHT_FALLBACK",
                        "identity": "<index digest or profile digest>",
                        "aligned_state": "aligned|drifted|stale|absent"},
  "subsystems_understood": ["<L1/L2 areas touched>"],
  "sources_read": [
    {"path": "...", "read_at": "<ts>", "digest": "<sha256 of bytes read>",
     "ranges": ["120-165"], "why": "<one line>"}
  ],
  "tests_read": [ {"path": "...", "digest": "...", "why": "..."} ],
  "history_evidence": [ {"commit": "<sha>", "note": "..."} ],
  "external_contracts": [ {"ref": "...", "claim": "..."} ],
  "decisions": [ {"decision": "...", "reason": "...", "at": "<ts>"} ],
  "evidence_refs": ["<evidence-manifest artifact ids/paths>"],
  "unresolved_questions": ["..."],
  "context_pack_digest": "<sha256 | null>",
  "next_action": "<one line>",
  "closed": false, "closed_at": null,
  "digest": "<sha256 of canonical json excluding digest>"
}
```

## Operations

- `open` — at task start (requires goal digest; binds base SHA; records backend +
  alignment state).
- `record-read` — appended by the agent for every L4 read (path + digest + ranges +
  why). This is the anti-"silent context truncation" ledger: delivered vs actually-read
  becomes checkable.
- `verify` — re-hash every recorded path; output per-file CURRENT/CHANGED/DELETED vs
  the recorded digest. A CHANGED file invalidates any cached claim about it (mixing
  obsolete source with current source is a listed anti-pattern).
- `close` — finalize (unresolved questions, pack digest, next action, closed_at).
- `reconstruct` — emit the compact working-state block for post-compaction reload
  (goal digest → contract reload, sources read, decisions, unresolved, next action).

## Rules

- The receipt lives in `.oss-contrib-evidence/cognition/` beside the V2 evidence
  manifest (same tamper-evident JSONL style).
- `record-read` never writes file contents — digests only; contents stay in the
  trajectory/evidence artifacts.
- Receipts bind to base_sha; a new base (pull/rebase) opens a new receipt generation
  (old ones remain as history).
