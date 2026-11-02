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
import hashlib
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


def main_pack_audit(pack: dict | None = None, config_path: str | None = None) -> int:
    """Audit-only mode (kept public and separate from govern)."""
    if pack is None:
        ap = argparse.ArgumentParser(description="Token budget audit.")
        ap.add_argument("pack")
        ap.add_argument("--config")
        args, _extra = ap.parse_known_args()
        try:
            pack = json.loads(Path(args.pack).read_text())
        except (OSError, json.JSONDecodeError) as e:
            print("error: cannot read pack: %s" % e, file=sys.stderr)
            return 2
        config_path = args.config
    budgets = dict(DEFAULT_BUDGETS)
    if config_path:
        try:
            user = json.loads(Path(config_path).read_text())
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
        print("Within budgets.")
        return 0
    if over_soft:
        print("Soft budget crossed for: %s" % ", ".join(over_soft))
        for a in ACTIONS:
            print("  " + a)
    if over_hard:
        print("HARD budget crossed for: %s — a user-visible reason is required." % ", ".join(over_hard))
        return 3
    return 1


# --------------------------------------------------------------------- governing

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


def _span_tokens(span: dict) -> int:
    """Actual selected span cost: (end - start + 1) lines * 40 chars / 4.
    The absolute end line was a V5 bug (over-charged late spans, under-charged
    early ones)."""
    a, _, b = span.get("lines", "0-0").partition("-")
    try:
        start = int(a or 0)
        end = int(b or a or 0)
    except ValueError:
        return 1
    return max(1, (end - start + 1) * 40 // 4)


def _recompute_accounting(pack: dict) -> dict:
    """Recompute category accounting from delivered content."""
    ta = pack.setdefault("token_accounting", {})
    src = sum(_span_tokens(s) for s in pack.get("source_ranges", []))
    test = sum(_span_tokens(t) for t in pack.get("tests", []))
    ta["source_used_est"] = src
    ta["test_used_est"] = test
    return ta


def recompute_pack_digest(pack: dict) -> str:
    """Regenerate pack_digest after any mutation. A modified Context Pack must
    never retain the digest of its previous contents."""
    body = {k: v for k, v in pack.items() if k != "pack_digest"}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    pack["pack_digest"] = digest
    return digest


def govern_pack(pack: dict, max_iterations: int = 12) -> dict:
    """Bounded repack loop: pack → audit → prune → repack → ACCEPT/BLOCKED.
    ACCEPT only when every category is within its soft budget; BLOCKED when
    pruning cannot get there (human decision required). Token accounting is
    recomputed from delivered spans each iteration and pack_digest is
    regenerated on every mutation."""
    actions: list[str] = []
    iterations = 0
    pruned_any = False
    for _ in range(max_iterations):
        iterations += 1
        ta = _recompute_accounting(pack)
        over = [c for c in GOV_SOFT
                if ta.get("%s_used_est" % c, 0) > GOV_SOFT[c]]
        if not over:
            recompute_pack_digest(pack) if pruned_any else None
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
            pruned_any = True
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
            recompute_pack_digest(pack)
        else:
            break
    _recompute_accounting(pack)
    if pruned_any:
        recompute_pack_digest(pack)
    ta = pack.get("token_accounting", {})
    still_over = [c for c in GOV_SOFT if ta.get("%s_used_est" % c, 0) > GOV_SOFT[c]]
    if still_over:
        return {"decision": "BLOCKED", "iterations": iterations, "actions": actions,
                "audit": "pruning exhausted; still over soft budget: %s — "
                         "widen the budget or cut scope with the user" % still_over}
    return {"decision": "ACCEPT", "iterations": iterations, "actions": actions,
            "audit": "within soft budgets after %d iteration(s)" % iterations}


if __name__ == "__main__":
    # V5.1: public CLI surface includes the real govern operation, so the audit
    # CLI and govern_pack() are one system, not two unrelated paths.
    import argparse as _ap
    _p = _ap.ArgumentParser(description="Budget auditor + governed repack loop.")
    _p.add_argument("mode", choices=["audit", "govern"], help="audit = report only; govern = bounded repack loop")
    _p.add_argument("pack", help="Context Pack JSON")
    _p.add_argument("--config", help="optional budget config JSON")
    _p.add_argument("--out", help="write the governed pack here (govern mode)")
    _args = _p.parse_args()
    try:
        _pack = json.loads(Path(_args.pack).read_text())
    except (OSError, json.JSONDecodeError) as e:
        print("error: cannot read pack: %s" % e, file=sys.stderr)
        raise SystemExit(2)
    if _args.mode == "audit":
        _rc = main_pack_audit(_pack, _args.config)
    else:
        _result = govern_pack(_pack)
        _recompute_accounting(_pack)
        recompute_pack_digest(_pack)
        if _args.out:
            Path(_args.out).write_text(json.dumps(_pack, indent=2, sort_keys=True) + "\n")
        print(json.dumps(_result, indent=2))
        print("pack_digest: %s" % _pack.get("pack_digest", "?")[:16])
        _rc = 0 if _result["decision"] == "ACCEPT" else (3 if _result["decision"] == "BLOCKED" else 1)
    raise SystemExit(_rc)
