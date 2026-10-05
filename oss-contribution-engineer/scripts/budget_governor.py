#!/usr/bin/env python3
"""budget_governor.py — explicit token budget accounting for a Context Pack.

Checks a Context Pack's token accounting against category budgets (soft/hard), and —
when soft budgets are crossed — emits the ordered remediation actions and the
protection list. It is pure computation over the pack JSON; it never edits the pack.

Exit codes: 0 within soft budgets, 1 soft budget crossed (actions required),
2 usage, 3 hard budget crossed (user-visible reason required).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_BUDGETS = {
    "cognition": {"soft": 4000, "hard": 8000},
    "source": {"soft": 12000, "hard": 30000},
    "test": {"soft": 4000, "hard": 10000},
    "history": {"soft": 2000, "hard": 6000},
    "spec": {"soft": 2000, "hard": 6000},
}

PROTECTED = [
    "current goal + done_when + stop conditions",
    "authority/constraints and safety rules",
    "unresolved blockers",
    "source identities (path + digest of what was actually read)",
]

ACTIONS = [
    "1. rerank remaining candidates; drop what no signal supports",
    "2. prune delivered content to spans (line ranges), not files",
    "3. externalize stable facts into the Task Cognition Receipt",
    "4. summarize with provenance (summary + artifact ref); no unproven summaries",
    "5. drop superseded observations / duplicate tool output",
    "6. request targeted expansion ONLY for the specific missing evidence",
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Token budget governor (pure check).")
    ap.add_argument("pack", help="Context Pack JSON")
    ap.add_argument("--config", help="optional budget config JSON")
    args = ap.parse_args()
    try:
        pack = json.loads(Path(args.pack).read_text())
    except (OSError, json.JSONDecodeError) as e:
        print("error: cannot read pack: %s" % e, file=sys.stderr)
        return 2
    budgets = dict(DEFAULT_BUDGETS)
    if args.config:
        try:
            user = json.loads(Path(args.config).read_text())
            for k, v in user.items():
                budgets.setdefault(k, {}).update(v if isinstance(v, dict) else {"soft": v, "hard": v})
        except (OSError, json.JSONDecodeError) as e:
            print("error: cannot read config: %s" % e, file=sys.stderr)
            return 2

    ta = pack.get("token_accounting", {})
    over_soft, over_hard = [], []
    print("Token budget status (estimates, chars/4):")
    for cat, lim in budgets.items():
        used = ta.get("%s_used_est" % cat)
        if used is None:
            continue
        status = "ok"
        if used > lim["hard"]:
            status = "HARD EXCEEDED"
            over_hard.append(cat)
        elif used > lim["soft"]:
            status = "over soft"
            over_soft.append(cat)
        print("  %-10s %6d / soft %5d / hard %5d  %s" % (cat, used, lim["soft"], lim["hard"], status))

    if not (over_soft or over_hard):
        print("Within budgets. Continue; expansions still need recorded reasons.")
        return 0

    if over_soft:
        print("\nSoft budget crossed for: %s" % ", ".join(over_soft))
        print("Do not simply keep reading. Ordered actions:")
        for a in ACTIONS:
            print("  " + a)
    if over_hard:
        print("\nHARD budget crossed for: %s" % ", ".join(over_hard))
        print("A user-visible reason is required before continuing; silent truncation is an anti-pattern.")
        return 3
    print("\nProtected (never drop to save tokens):")
    for p in PROTECTED:
        print("  - " + p)
    return 1


# --------------------------------------------------------------------- governing
# V5: a real bounded repack loop — pack → audit → prune → repack → ACCEPT/BLOCKED.
# Pruning drops delivered source spans from the end (least provenance first, then
# last delivered) until within the soft budget. Hard-budget crossings and protected
# items are never silently resolved: BLOCKED requires a human decision.

GOV_SOFT = {"source": 12000, "test": 4000, "cognition": 4000,
            "history": 2000, "spec": 2000}
DIRECT_FAMILIES = {"lexical", "symbol", "test", "history", "cognition", "path"}


def _span_priority(index: int, span: dict) -> tuple:
    """Lower sorts first (pruned first). Spans whose evidence lacks a direct
    family (structural-only) prune before direct-evidence spans; within a class,
    later-delivered prunes before earlier (index descending)."""
    ev = span.get("evidence") or []
    has_direct = any(e.get("family") in DIRECT_FAMILIES for e in ev)
    return (0 if has_direct else 1, index)


def govern_pack(pack: dict, max_iterations: int = 12) -> dict:
    """Bounded repack loop. Returns {decision, iterations, actions, audit}.
    ACCEPT only when every category is within its soft budget; BLOCKED when
    pruning cannot get there (human decision required)."""
    actions: list[str] = []
    iterations = 0
    for _ in range(max_iterations):
        iterations += 1
        ta = pack.get("token_accounting", {})
        over = [c for c in GOV_SOFT
                if ta.get("%s_used_est" % c, 0) > GOV_SOFT[c]]
        if not over:
            return {"decision": "ACCEPT", "iterations": iterations,
                    "actions": actions,
                    "audit": "all categories within soft budgets"}
        if "source" in over and pack.get("source_ranges"):
            spans = pack["source_ranges"]
            order = sorted(range(len(spans)),
                           key=lambda i: _span_priority(i, spans[i]),
                           reverse=True)
            idx = order[0]
            dropped = spans.pop(idx)
            ev = dropped.get("evidence") or []
            has_direct = any(e.get("family") in DIRECT_FAMILIES for e in ev)
            b = int((dropped.get("lines", "0-0").partition("-"))[2] or 0)
            span_tokens = max(1, b * 40 // 4)
            ta["source_used_est"] = max(0, ta.get("source_used_est", 0) - span_tokens)
            pack.setdefault("excluded", []).append(
                {"path": dropped.get("path"), "symbol": dropped.get("symbol"),
                 "reason": "pruned by budget governor (span %s, %s evidence)"
                           % (dropped.get("lines"),
                              "direct" if has_direct else "structural-only")})
            if has_direct:
                actions.append("pruned DIRECT span %s:%s — report to user; "
                               "no_regret.displaced_direct updated"
                               % (dropped.get("path"), dropped.get("lines")))
                pack.setdefault("no_regret", {}).setdefault(
                    "displaced_direct", []).append(dropped.get("path"))
            else:
                actions.append("pruned structural-only span %s:%s"
                               % (dropped.get("path"), dropped.get("lines")))
        else:
            break
    ta = pack.get("token_accounting", {})
    still_over = [c for c in GOV_SOFT if ta.get("%s_used_est" % c, 0) > GOV_SOFT[c]]
    if still_over:
        return {"decision": "BLOCKED", "iterations": iterations, "actions": actions,
                "audit": "pruning exhausted; still over soft budget: %s — "
                         "widen the budget or cut scope with the user" % still_over}
    return {"decision": "ACCEPT", "iterations": iterations, "actions": actions,
            "audit": "within soft budgets after %d iteration(s)" % iterations}


if __name__ == "__main__":
    raise SystemExit(main())
