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
    rd = retrieval.get("routing_decision", {})
    plan = {
        "plan_version": 2,
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
        "structural_quota": {
            "max_share": rd.get("structural_max_share", 0.0),
            "note": "structural-only candidates (repomap/graph, no direct evidence) "
                    "may consume at most this share of packed files; direct evidence "
                    "packs first — the no-regret guard",
        },
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


def goal_query_tokens(goal: dict, anchor_symbols: list[str]) -> set[str]:
    qtokens: set[str] = set()
    for raw in (goal.get("intent", "") + " " + " ".join(goal.get("likely_domains", []))
                + " " + " ".join(anchor_symbols)).lower().split():
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
    return qtokens


def build_pack(repo: Path, goal: dict, plan: dict, anchor_symbols: list[str] | None = None,
               anchor_lines: dict[str, list[int]] | None = None) -> tuple[dict, list[dict]]:
    """PACK phase (independent of RETRIEVE): choose what enters context under budget.

    Ordering rules: direct-evidence candidates pack before structural-only ones
    (no-regret guard continued from the router); structural-only candidates may fill
    at most structural_quota.max_share of the packed files. Returns (pack, read_files).
    """
    anchor_symbols = anchor_symbols or []
    anchor_lines = anchor_lines or {}
    qtokens = goal_query_tokens(goal, anchor_symbols)
    src_budget = plan["token_allocation"]["source"]
    test_budget = plan["token_allocation"]["test"]

    # direct-first ordering (stable within class by router rank)
    r1 = plan.get("radius_1", [])
    direct = [c for c in r1 if c.get("evidence_class", "direct") == "direct"]
    structural = [c for c in r1 if c.get("evidence_class") == "structural"]
    max_structural_files = -1 if plan.get("structural_quota", {}).get("max_share", 0) >= 1.0 \
        else int(len(r1) * plan.get("structural_quota", {}).get("max_share", 0.0))
    ordered = direct + structural

    source_ranges, test_ranges = [], []
    used_src = used_test = 0
    read_files = []
    structural_packed = 0
    displaced_direct: list[str] = []
    for cand in ordered:
        path = cand["path"]
        is_structural_only = cand.get("evidence_class") == "structural"
        if is_structural_only and max_structural_files >= 0 \
                and structural_packed >= max_structural_files:
            plan.setdefault("excluded_candidates", []).append(
                {"path": path, "reason": "structural quota exhausted (max_share %s)"
                 % plan.get("structural_quota", {}).get("max_share")})
            continue
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
                                    "evidence": cand.get("evidence", []),
                                    "digest": digest})
                used_test += est
                if is_structural_only:
                    structural_packed += 1
                continue
            plan.setdefault("excluded_candidates", []).append(
                {"path": path, "reason": "test budget exhausted"})
            continue
        if used_src < src_budget:
            all_spans = symbol_spans(text)
            path_lines = anchor_lines.get(path, [])
            matched = [(n, a, b2) for (n, a, b2) in all_spans
                       if any(t and t in n.lower() for t in qtokens)
                       or n in anchor_symbols
                       or any(a <= ln <= b2 for ln in path_lines)]
            chosen = matched or all_spans
            delivered = []
            for (name, a, b2) in chosen[:3]:
                span_tokens = max(1, (b2 - a + 1) * 40 // 4)
                if used_src + span_tokens > src_budget:
                    continue
                used_src += span_tokens
                why = "symbol span for %s — %s" % (name, cand.get("tier_reason", "router candidate"))
                delivered.append({"path": path, "symbol": name, "lines": "%d-%d" % (a, b2),
                                  "why": why, "evidence": cand.get("evidence", []),
                                  "digest": digest})
            source_ranges.extend(delivered)
            if delivered:
                if is_structural_only:
                    structural_packed += 1
            elif cand.get("evidence_class", "direct") == "direct":
                displaced_direct.append(path)
                plan.setdefault("excluded_candidates", []).append(
                    {"path": path, "reason": "no span fits remaining source budget"})
        else:
            if cand.get("evidence_class", "direct") == "direct":
                displaced_direct.append(path)
            plan.setdefault("excluded_candidates", []).append(
                {"path": path, "reason": "source budget exhausted (soft %d tokens)" % src_budget})

    pack = {
        "pack_version": 2,
        "goal_digest": goal.get("digest"),
        "task_type": plan.get("task_type"),
        "no_regret": {
            "direct_first": True,
            "structural_quota": plan.get("structural_quota", {}),
            "displaced_direct": displaced_direct,
            "note": "displaced_direct = direct-evidence candidates that lost their "
                    "budget slot; non-empty means the no-regret guarantee is under "
                    "budget pressure and the agent must widen budget or cut scope",
        },
        "cognition": {"backend": plan.get("backend"),
                      "claims": [{"object": p, "claim": "see backend entry",
                                  "binding": {"path": p}}
                                 for p in [s.get("path") for s in goal.get("scope", [])]]},
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
        "provenance": {"goal_digest": goal.get("digest"),
                       "anchors": {"symbols": anchor_symbols,
                                   "lines": anchor_lines},
                       "generated": datetime.now(timezone.utc).isoformat(),
                       "read_files": read_files},
    }
    body = {k: v for k, v in pack.items() if k != "pack_digest"}
    pack["pack_digest"] = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return pack, read_files


def cmd_pack(repo: Path, goal_path: str, plan_path: str, anchor_symbols: list[str],
             anchor_lines: dict[str, list[int]]) -> int:
    goal = load_json(goal_path)
    plan = load_json(plan_path)
    pack, _ = build_pack(repo, goal, plan, anchor_symbols, anchor_lines)
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
    p_pack.add_argument("--anchor-symbols", default="",
                        help="comma-separated symbol names from trace frames / issue text")
    p_pack.add_argument("--anchor-lines", default="",
                        help="path:line pairs, comma-separated (e.g. src/x.rs:331,src/y.py:42)")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print("error: %s is not a directory" % repo, file=sys.stderr)
        return 3
    if args.cmd == "plan":
        return cmd_plan(repo, args.goal, args.retrieval, args.top_r1)
    anchor_lines: dict[str, list[int]] = {}
    for pair in args.anchor_lines.split(","):
        if ":" in pair:
            f, _, ln = pair.rpartition(":")
            try:
                anchor_lines.setdefault(f.strip(), []).append(int(ln))
            except ValueError:
                pass
    return cmd_pack(repo, args.goal, args.plan,
                    [s.strip() for s in args.anchor_symbols.split(",") if s.strip()],
                    anchor_lines)


if __name__ == "__main__":
    raise SystemExit(main())
