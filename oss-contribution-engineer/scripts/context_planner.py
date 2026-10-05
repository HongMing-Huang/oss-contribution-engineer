#!/usr/bin/env python3
"""context_planner.py — Task Context Plan + bounded Context Pack generation.

plan: goal contract + router output → a Task Context Plan (radius tiers, token
allocation, exclusions, reasons) BEFORE large source regions are read.
pack: plan → a bounded Context Pack with source *ranges* (not whole files), digest
bindings, token accounting, and provenance. The pack carries pointers; the agent
still reads current source before editing anything (source verification rule).

Exit codes: 0 ok, 2 usage, 3 missing input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BUDGETS = {
    "cognition": {"soft": 4000, "hard": 8000},
    "source": {"soft": 12000, "hard": 30000},
    "test": {"soft": 4000, "hard": 10000},
    "history": {"soft": 2000, "hard": 6000},
    "spec": {"soft": 2000, "hard": 6000},
}

SYMBOL_PATTERNS = [
    re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)"),
    re.compile(r"^\s*class\s+([A-Za-z_]\w*)"),
    re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)"),
    re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)"),
    re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)"),
    re.compile(r"^\s*(?:pub\s+)?struct\s+([A-Za-z_]\w*)"),
    re.compile(r"^\s*(?:pub\s+)?trait\s+([A-Za-z_]\w*)"),
    re.compile(r"^\s*(?:public|private|protected)?\s*(?:final\s+)?class\s+([A-Za-z_]\w*)"),
]


def load_json(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except OSError as e:
        print("error: cannot read %s: %s" % (path, e), file=sys.stderr)
        raise SystemExit(3)
    except json.JSONDecodeError as e:
        print("error: %s is not valid JSON: %s" % (path, e), file=sys.stderr)
        raise SystemExit(3)


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def budgets(repo: Path) -> dict:
    cfg = repo / ".oss-contrib" / "context-budget.json"
    if cfg.exists():
        try:
            user = json.loads(cfg.read_text())
            merged = {k: dict(v) for k, v in DEFAULT_BUDGETS.items()}
            for k, v in user.items():
                merged.setdefault(k, {}).update(v if isinstance(v, dict) else {"soft": v, "hard": v})
            return merged
        except json.JSONDecodeError:
            print("warning: unreadable budget config, using defaults", file=sys.stderr)
    return {k: dict(v) for k, v in DEFAULT_BUDGETS.items()}


def cmd_plan(repo: Path, goal_path: str, retrieval_path: str, top_r1: int) -> int:
    goal = load_json(goal_path)
    retrieval = load_json(retrieval_path)
    cands = retrieval.get("candidates", [])
    r1 = [dict(c, tier_reason="router rank %d: %s" % (c["rank"], c.get("reason", "")))
          for c in cands[:top_r1]]
    r2 = [dict(c, trigger="read only if R1 evidence insufficient; reason: %s" % c.get("reason", ""))
          for c in cands[top_r1:]]
    excluded = [{"path": c["path"],
                 "reason": "below top-k after fusion; revisit only with a recorded reason"}
                for c in cands[top_k_len(cands, 30):]] if len(cands) > 30 else []
    b = budgets(repo)
    task_type = retrieval.get("task_type", goal.get("task_type", "issue2code"))
    # task priors shift allocation between categories (never protections)
    alloc = {k: v["soft"] for k, v in b.items()}
    if task_type == "trace2code":
        alloc["history"] = 4000
    if task_type in ("code2test", "edit2ripple"):
        alloc["test"] = 6000
    plan = {
        "plan_version": 1,
        "goal_digest": goal.get("digest"),
        "task_type": task_type,
        "backend": retrieval.get("backend"),
        "primary_subsystem": ", ".join(goal.get("likely_domains", [])) or "unspecified (guess)",
        "radius_1": r1,
        "radius_2": r2,
        "radius_3": [{"kind": "subsystem-architecture",
                      "trigger": "R1+R2 insufficient to establish the invariant in question"},
                     {"kind": "historical-PRs",
                      "trigger": "need origin/intent evidence (git log -p, linked PRs)"}],
        "token_allocation": alloc,
        "budgets": b,
        "excluded_candidates": excluded,
        "rules": ["do not read radius_2/3 without a recorded reason",
                  "every expansion names what R1 failed to establish",
                  "source verification before edits is unconditional"],
        "generated": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(plan, indent=2))
    return 0


def top_k_len(cands: list, cap: int) -> int:
    return min(len(cands), cap)


def symbol_spans(text: str) -> list[tuple[str, int, int]]:
    """Return ALL top-level (name, start, end) spans, in file order. Selection
    (matching vs first-N) is the caller's policy — a head-only scan missed symbols
    deeper in the file (found by the end-to-end comparison)."""
    lines = text.splitlines()
    starts = []
    for i, line in enumerate(lines):
        for pat in SYMBOL_PATTERNS:
            m = pat.match(line)
            if m:
                starts.append((m.group(1), i))
                break
    spans = []
    for j, (name, start) in enumerate(starts):
        end = starts[j + 1][1] - 1 if j + 1 < len(starts) else min(len(lines) - 1, start + 120)
        spans.append((name, start + 1, end + 1))
    return spans


def cmd_pack(repo: Path, goal_path: str, plan_path: str) -> int:
    goal = load_json(goal_path)
    plan = load_json(plan_path)
    scope_tokens = [s["path"] for s in goal.get("scope", [])]
    qtokens = set()
    for raw in (goal.get("intent", "") + " " + " ".join(goal.get("likely_domains", []))).lower().split():
        # split on separators FIRST (before stripping) so "usage-line" yields
        # usage + line; stripping first glued them into an unmatchable token
        for w in re.findall(r"[a-z0-9]+", raw):
            if len(w) >= 3:
                qtokens.add(w)
            for part in re.split(r"[_]+", w):
                if len(part) >= 3:
                    qtokens.add(part)
            for chunk in re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z][a-z]*|[a-z]+|\d+", w):
                if len(chunk) >= 3:
                    qtokens.add(chunk.lower())
    src_budget = plan["token_allocation"]["source"]
    test_budget = plan["token_allocation"]["test"]

    source_ranges, test_ranges = [], []
    used_src = used_test = 0
    read_files = []
    for cand in plan.get("radius_1", []):
        path = cand["path"]
        p = repo / path
        if not p.is_file():
            continue
        text = p.read_text(errors="replace")
        digest = sha256_file(p)
        read_files.append({"path": path, "digest": digest})
        est = len(text) // 4
        if cand.get("is_test"):
            if used_test + est <= test_budget:
                test_ranges.append({"path": path, "lines": "1-%d" % len(text.splitlines()),
                                    "why": cand.get("tier_reason", "test relation"),
                                    "digest": digest})
                used_test += est
            continue
        if used_src < src_budget:
            all_spans = symbol_spans(text)
            matched = [(n, a, b2) for (n, a, b2) in all_spans
                       if any(t and t in n.lower() for t in qtokens)]
            chosen = matched or all_spans
            delivered = []
            for (name, a, b2) in chosen[:3]:
                span_tokens = max(1, (b2 - a + 1) * 40 // 4)
                if used_src + span_tokens > src_budget:
                    continue
                used_src += span_tokens
                why = "symbol span for %s — %s" % (name, cand.get("tier_reason", "router candidate"))
                delivered.append({"path": path, "symbol": name, "lines": "%d-%d" % (a, b2),
                                  "why": why, "digest": digest})
            source_ranges.extend(delivered)
            if not delivered:
                plan.setdefault("excluded_candidates", []).append(
                    {"path": path, "reason": "no span fits remaining source budget"})
        else:
            plan.setdefault("excluded_candidates", []).append(
                {"path": path, "reason": "source budget exhausted (soft %d tokens)" % src_budget})

    pack = {
        "pack_version": 1,
        "goal_digest": goal.get("digest"),
        "task_type": plan.get("task_type"),
        "cognition": {"backend": plan.get("backend"),
                      "claims": [{"object": p, "claim": "see backend entry",
                                  "binding": {"path": p}}
                                 for p in scope_tokens]},
        "source_ranges": source_ranges,
        "structural": [],
        "tests": test_ranges,
        "history": [],
        "external_contracts": [],
        "invariants": [],
        "unresolved": list(goal.get("unknowns", [])),
        "excluded": plan.get("excluded_candidates", []),
        "token_accounting": {
            "source_used_est": used_src, "source_budget": src_budget,
            "test_used_est": used_test, "test_budget": test_budget,
            "note": "est = chars/4; estimates, labeled as estimates",
        },
        "provenance": {"plan": plan_path, "goal": goal_path,
                       "generated": datetime.now(timezone.utc).isoformat(),
                       "read_files": read_files},
    }
    body = {k: v for k, v in pack.items() if k != "pack_digest"}
    pack["pack_digest"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    print(json.dumps(pack, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Task Context Plan + Context Pack generator.")
    ap.add_argument("repo")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--goal", required=True, help="goal contract JSON")
    p_plan.add_argument("--retrieval", required=True, help="router JSON output")
    p_plan.add_argument("--top-r1", type=int, default=6)
    p_pack = sub.add_parser("pack")
    p_pack.add_argument("--goal", required=True)
    p_pack.add_argument("--plan", required=True)
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print("error: %s is not a directory" % repo, file=sys.stderr)
        return 3
    if args.cmd == "plan":
        return cmd_plan(repo, args.goal, args.retrieval, args.top_r1)
    return cmd_pack(repo, args.goal, args.plan)


if __name__ == "__main__":
    raise SystemExit(main())
