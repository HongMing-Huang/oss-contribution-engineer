#!/usr/bin/env python3
"""goal_compiler.py — Goal Intelligence: normalize a task into a Goal Contract.

The Goal Compiler separates WHAT THE USER WANTS from what the agent guesses will
satisfy it. An implementation hypothesis is never the goal. Output: a digest-stable
Goal Contract (JSON) plus a compact Goal Card (GOAL/DONE/SCOPE/UNKNOWN/NEXT).

The contract distinguishes user intent from agent guesses: scope/likely_domains/
unknowns are marked as guesses; done_when items are marked observable or not, and a
contract with no observable acceptance evidence is rejected unless explicitly allowed.

Subcommands
-----------
  compile   build a contract from flags and emit the Goal Card
  card      re-render the Goal Card from a stored contract
  verify    recompute a contract's digest and check integrity
  hypotheses  attach an implementation hypothesis record (kept OUT of the contract)

Exit codes: 0 ok, 1 contract rejected (no observable done_when), 2 usage,
3 integrity failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

OBSERVABLE_PREFIXES = ("run:", "test ", "test:", "artifact ", "maintainer ", "output ")
CONTRACT_VERSION = 1


def canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def digest_of(obj: dict) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def classify_done_when(item: str) -> dict:
    how = ""
    observable = False
    for pref in OBSERVABLE_PREFIXES:
        if item.lower().startswith(pref):
            observable = True
            how = pref.rstrip(": ").strip()
            break
    if not observable:
        # heuristic: an explicit command or test reference inside the criterion
        if re.search(r"`[^`]+`", item) and re.search(
            r"pytest|unittest|npm (run )?test|cargo test|go test|make |exit 0|tox|grep|\.py|\.rs|\.go|\.js", item, re.I
        ):
            observable = True
            how = "embedded command/test reference"
    return {"criterion": item, "observable": observable, "how_observed": how or "UNVERIFIABLE"}


def build_contract(args) -> dict:
    dw = [classify_done_when(x) for x in (args.done_when or [])]
    contract = {
        "contract_version": CONTRACT_VERSION,
        "task_id": args.task_id,
        "created": datetime.now(timezone.utc).isoformat(),
        "intent": args.intent,
        "outcome": args.outcome or "",
        "why": args.why or "unstated",
        "done_when": dw,
        "repository": args.repository,
        "likely_domains": [d.strip() for d in (args.domains or "").split(",") if d.strip()],
        "scope": [{"path": s.strip(), "status": "guess"} for s in (args.scope or [])],
        "explicit_non_goals": list(args.non_goals or []),
        "constraints": list(args.constraints or []),
        "repository_rules": list(args.repo_rules or []),
        "authority": {
            "read": True,
            "worktree_edit": "worktree_edit" in (args.authority or "").split(","),
            "remote_write": False,  # never inferred; granted later per action
        },
        "unknowns": list(args.unknowns or []),
        "stop_conditions": list(args.stop_conditions or []),
        "notes": "scope/likely_domains/unknowns are agent guesses, not user intent; "
                 "hypotheses live outside this contract",
    }
    contract["digest"] = digest_of({k: v for k, v in contract.items()})
    return contract


def goal_card(contract: dict) -> str:
    lines = [
        "GOAL  " + contract["intent"],
        "DONE  " + ("; ".join(
            d["criterion"] + (" [" + d["how_observed"] + "]" if d["observable"] else " [UNVERIFIABLE]")
            for d in contract["done_when"]) or "—"),
        "SCOPE " + (", ".join(contract["likely_domains"]) or "unspecified")
        + (" | guesses: " + ", ".join(s["path"] for s in contract["scope"]) if contract["scope"] else ""),
        "UNKNOWN " + ("; ".join(contract["unknowns"]) or "none recorded"),
        "NEXT  " + ("compile context plan via retrieval_router.py route"
                    if contract["authority"]["read"] else "obtain read authority"),
    ]
    auth = contract["authority"]
    lines.append("AUTH  read=%s worktree_edit=%s remote_write=%s" % (
        auth["read"], auth["worktree_edit"], auth["remote_write"]))
    return "\n".join(lines)


def out_dir(args) -> Path:
    d = Path(args.out or (Path(args.repo or ".") / ".oss-contrib-evidence" / "goals"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def cmd_compile(args) -> int:
    if not args.intent:
        print("error: --intent is required (what the user wants, in their terms)", file=sys.stderr)
        return 2
    contract = build_contract(args)
    if not contract["done_when"]:
        print("error: at least one --done-when is required", file=sys.stderr)
        return 2
    if not any(d["observable"] for d in contract["done_when"]) and not args.allow_unobservable:
        print("error: no done_when item is observable acceptance evidence. Add items like "
              "--done-when 'run: python3 -m pytest -q' or use --allow-unobservable.",
              file=sys.stderr)
        return 1
    path = out_dir(args) / ("%s-%s.json" % (contract["digest"][:12], contract["task_id"] or "task"))
    path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(goal_card(contract))
    print("contract: %s (digest %s…)" % (path, contract["digest"][:12]))
    return 0


def load_contract(path: Path) -> dict:
    contract = json.loads(path.read_text())
    body = {k: v for k, v in contract.items() if k != "digest"}
    if digest_of(body) != contract.get("digest"):
        print("error: contract digest mismatch — file was modified after compilation",
              file=sys.stderr)
        raise SystemExit(3)
    return contract


def cmd_card(args) -> int:
    contract = load_contract(Path(args.file))
    print(goal_card(contract))
    return 0


def cmd_verify(args) -> int:
    contract = load_contract(Path(args.file))
    print("digest OK: %s… (%s done_when items, %d observable)" % (
        contract["digest"][:12], len(contract["done_when"]),
        sum(1 for d in contract["done_when"] if d["observable"])))
    return 0


def cmd_hypotheses(args) -> int:
    # Hypotheses are the agent's implementation guesses; they are recorded SEPARATELY
    # so they can change freely without touching the immutable contract.
    d = out_dir(args)
    hyp_file = d / "hypotheses.jsonl"
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "task_id": args.task_id or "",
        "hypothesis": args.hypothesis,
        "status": args.status,
    }
    with hyp_file.open("a") as f:
        f.write(json.dumps(rec, sort_keys=True) + "\n")
    print("hypothesis recorded (%s): %s" % (args.status, args.hypothesis))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Goal Compiler: task → Goal Contract + Goal Card.")
    ap.add_argument("repo", nargs="?", default=".", help="repository root (default: .)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--out", help="output dir (default <repo>/.oss-contrib-evidence/goals)")

    p_c = sub.add_parser("compile")
    common(p_c)
    p_c.add_argument("--task-id")
    p_c.add_argument("--intent", required=True)
    p_c.add_argument("--outcome")
    p_c.add_argument("--why")
    p_c.add_argument("--done-when", action="append",
                     help="observable acceptance criterion, e.g. 'run: python3 -m pytest -q'")
    p_c.add_argument("--repository")
    p_c.add_argument("--domains", help="comma-separated likely L1 subsystems (guesses)")
    p_c.add_argument("--scope", action="append", help="candidate paths (guesses)")
    p_c.add_argument("--non-goals", action="append")
    p_c.add_argument("--constraints", action="append")
    p_c.add_argument("--repo-rules", action="append")
    p_c.add_argument("--authority", default="read", help="comma set: read,worktree_edit")
    p_c.add_argument("--unknowns", action="append")
    p_c.add_argument("--stop-conditions", action="append")
    p_c.add_argument("--allow-unobservable", action="store_true")
    p_c.set_defaults(func=cmd_compile)

    p_card = sub.add_parser("card")
    common(p_card)
    p_card.add_argument("file")
    p_card.set_defaults(func=cmd_card)

    p_v = sub.add_parser("verify")
    common(p_v)
    p_v.add_argument("file")
    p_v.set_defaults(func=cmd_verify)

    p_h = sub.add_parser("hypotheses")
    common(p_h)
    p_h.add_argument("--hypothesis", required=True)
    p_h.add_argument("--status", default="proposed",
                     choices=["proposed", "supported", "falsified", "superseded"])
    p_h.add_argument("--task-id")
    p_h.set_defaults(func=cmd_hypotheses)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
