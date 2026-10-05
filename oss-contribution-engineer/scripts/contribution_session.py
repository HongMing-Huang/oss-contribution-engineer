#!/usr/bin/env python3
"""contribution_session.py — the V5 runtime spine: one session, one legal next step.

Composes the existing scripts (goal_compiler, evidence_manifest, validation_report,
upstream_state) instead of reimplementing them. The session file
(<repo>/.oss-contrib-evidence/session.json) is the machine-readable source of
workflow state: which state exists, which evidence exists, which operation is legal
next. Illegal transitions exit non-zero with the missing items.

Gates read ONLY machine artifacts — session JSON, evidence manifest entries, goal
contract JSON, captured upstream PR JSON. A markdown report can never advance state.

States (linear):
DISCOVER → RECON → CANDIDATE → DEDUPLICATE → PROVE → RED → PATCH → GREEN →
REGRESSION → CONTRIBUTOR_UNDERSTANDING → REVIEW → PR_READY → IN_REVIEW

Commands
--------
  init        create the session (requires a Goal Contract; captures base SHA)
  status      show state, evidence, blockers, legal next states
  set-authority   grant worktree_edit/remote_write — REQUIRES --evidence-ref artifact
  record      attach machine artifacts: recon/dedupe/walkthrough/scope-audit/plan/pack/receipt
  set-classification  record triage classification (DEDUPLICATE gate)
  set-understanding   record explain-back status (UNDERSTOOD requires --confirmed-by)
  advance     --to STATE: run the gate checks, commit the transition
  upstream    --pr-json FILE: classify captured PR state (closed != merged)
  reconstruct print the working state after context loss

Exit codes: 0 ok, 1 gate refused / illegal, 2 usage, 3 missing session/input.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evidence_manifest import load_entries  # reuse: witnessed evidence
from validation_report import build_report  # reuse: staleness/FAIL audit

EVIDENCE_DIR = ".oss-contrib-evidence"
SESSION_FILE = "session.json"

STATES = ["DISCOVER", "RECON", "CANDIDATE", "DEDUPLICATE", "PROVE", "RED", "PATCH",
          "GREEN", "REGRESSION", "CONTRIBUTOR_UNDERSTANDING", "REVIEW", "PR_READY",
          "IN_REVIEW"]

CLASSIFICATIONS = {"AVAILABLE", "CLAIMED", "PR_EXISTS", "DESIGN_BLOCKED",
                   "NEEDS_MAINTAINER_DECISION", "INVALID", "STALE", "TOO_LARGE",
                   "TOO_TRIVIAL", "GOOD_CANDIDATE"}

# triage classifications that END the run without a patch (V2: no-patch is success)
STOPPING = {"CLAIMED", "PR_EXISTS", "DESIGN_BLOCKED", "NEEDS_MAINTAINER_DECISION",
            "INVALID", "STALE", "TOO_LARGE", "TOO_TRIVIAL"}

UNDERSTANDING = {"UNDERSTOOD", "DEFERRED", "INCOMPLETE"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def session_path(repo: Path) -> Path:
    return repo / EVIDENCE_DIR / SESSION_FILE


def load_session(repo: Path) -> dict:
    p = session_path(repo)
    if not p.exists():
        print("error: no session at %s — run 'init' first" % p, file=sys.stderr)
        raise SystemExit(3)
    return json.loads(p.read_text())


def save_session(repo: Path, session: dict) -> None:
    p = session_path(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(session, indent=2, sort_keys=True) + "\n")


def git_head(repo: Path) -> str | None:
    p = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                       capture_output=True, text=True, shell=False)
    return p.stdout.strip() if p.returncode == 0 else None


# ------------------------------------------------------------------ gate checks

def manifest_entries(repo: Path) -> list[dict]:
    """Evidence entries, or [] when nothing was recorded yet. A missing manifest is
    missing evidence — never a crash."""
    try:
        return load_entries(repo)
    except SystemExit:
        return []


def check_reproduction(repo: Path, s: dict) -> list[str]:
    missing = []
    repro = [e for e in manifest_entries(repo) if e.get("kind") == "execution"
             and any(w in e.get("purpose", "").lower()
                     for w in ("reproduc", "actual behavior", "prove the bug"))]
    if not repro:
        missing.append("reproduction evidence: no witnessed execution whose purpose "
                       "records the reproducer (evidence_manifest record)")
    return missing


def check_red(repo: Path, s: dict) -> list[str]:
    missing = []
    red = [e for e in manifest_entries(repo) if e.get("expected_failure") is True
           and e.get("status") == "PASS"]
    if not red:
        missing.append("RED witness: no --expect-fail execution recorded as PASS "
                       "(regression test failing on unmodified upstream)")
    return missing


def check_green_fresh(repo: Path, s: dict) -> list[str]:
    missing = []
    head = git_head(repo)
    green = [e for e in manifest_entries(repo)
             if "green" in e.get("purpose", "").lower()
             and e.get("kind") == "execution" and e.get("status") == "PASS"]
    if not green:
        missing.append("GREEN witness: no passing execution recorded for GREEN")
        return missing
    if not any(e.get("head_bound") for e in green):
        missing.append("GREEN witness must be recorded with --head-bound "
                       "(bound to the HEAD that produced it)")
        return missing
    stale = [e for e in green if e.get("git_head") and head and e["git_head"] != head]
    if stale and len(stale) == len(green):
        missing.append("GREEN evidence is STALE: recorded at HEAD %s, current HEAD is "
                       "%s — re-run after the review-driven change"
                       % (stale[0].get("git_head", "?")[:12], (head or "?")[:12]))
    return missing


def check_validation_current(repo: Path, s: dict) -> list[str]:
    missing = []
    head = git_head(repo)
    entries = manifest_entries(repo)
    if not entries:
        missing.append("validation: evidence manifest is empty")
        return missing
    report = build_report(entries, head=head)
    if report["summary"]["failed"]:
        missing.append("validation: %d command(s) FAIL in the manifest"
                       % report["summary"]["failed"])
    stale = report["summary"].get("stale", 0)
    if stale:
        missing.append("validation: %d head-bound record(s) are STALE for current HEAD"
                       % stale)
    if report["summary"]["not_executed"]:
        missing.append("validation: %d planned level(s) not executed — record "
                       "record-skip with a reason or run them"
                       % report["summary"]["not_executed"])
    return missing


def check_scope_audit(repo, s: dict) -> list[str]:
    sa = s.get("scope_audit") or {}
    if not sa.get("conclusion"):
        return ["scope audit: not recorded (run diff_scope_check.py and 'record "
                "--kind scope-audit --conclusion WITHIN_SCOPE|ACKNOWLEDGED')"]
    if sa.get("conclusion") not in ("WITHIN_SCOPE", "ACKNOWLEDGED"):
        return ["scope audit: conclusion %s is unresolved — fix drift or explicitly "
                "ACKNOWLEDGE with a reason" % sa["conclusion"]]
    return []


def check_understanding(repo, s: dict) -> list[str]:
    u = s.get("understanding") or {}
    if not u.get("status"):
        return ["contributor understanding: status not recorded "
                "(set-understanding; UNDERSTOOD requires --confirmed-by <human>)"]
    if u["status"] not in UNDERSTANDING:
        return ["contributor understanding: status must be one of %s" % sorted(UNDERSTANDING)]
    if u["status"] == "UNDERSTOOD" and not u.get("confirmed_by"):
        return ["contributor understanding: UNDERSTOOD requires --confirmed-by "
                "(the agent never confirms for the human)"]
    return []


# gate table: STATE -> (prerequisite evidence checks, authority requirements)
def gate_requirements(state: str) -> dict:
    return {
        "RECON": {
            "checks": [
                ("goal contract", lambda repo, s: [] if s.get("goal", {}).get("digest")
                 and s.get("goal", {}).get("path") and Path(s["goal"]["path"]).exists()
                 else ["goal contract missing or file absent"]),
                ("base SHA", lambda repo, s: [] if s.get("base_sha")
                 else ["base SHA not captured"]),
            ],
            "authority": [],
        },
        "CANDIDATE": {
            "checks": [
                ("recon artifacts", lambda repo, s: [] if (s.get("artifacts") or {}).get("recon")
                 else ["recon artifacts not recorded (record --kind recon --file ...)"]),
            ],
            "authority": [],
        },
        "DEDUPLICATE": {
            "checks": [
                ("dedupe artifacts", lambda repo, s: [] if (s.get("artifacts") or {}).get("dedupe")
                 else ["duplicate-work evidence not recorded"]),
            ],
            "authority": [],
        },
        "PROVE": {
            "checks": [
                ("classification", lambda repo, s: [] if s.get("classification")
                 else ["triage classification not recorded (set-classification)"]),
            ],
            "authority": [],
        },
        "RED": {
            "checks": [("reproduction", reproduction_gate)],
            "authority": [],
        },
        "PATCH": {
            "checks": [("red witness", red_gate)],
            "authority": [("worktree_edit",
                           "editing production code requires WORKTREE_EDIT granted "
                           "via set-authority with an evidence ref")],
        },
        "GREEN": {
            "checks": [
                ("patch intent", lambda repo, s: [] if (s.get("artifacts") or {}).get("patch_intent")
                 else ["PATCH INTENT not recorded (record --kind patch-intent --file plan)"]),
            ],
            "authority": [],
        },
        "REGRESSION": {
            "checks": [("green witness fresh", green_gate)],
            "authority": [],
        },
        "CONTRIBUTOR_UNDERSTANDING": {
            "checks": [
                ("full validation current", check_validation_current),
            ],
            "authority": [],
        },
        "REVIEW": {
            "checks": [("understanding recorded", understanding_gate)],
            "authority": [],
        },
        "PR_READY": {
            "checks": [("validation current", validation_current_gate),
                       ("scope audit", scope_audit_gate),
                       ("understanding recorded", understanding_gate)],
            "authority": [],
        },
        "IN_REVIEW": {
            "checks": [
                ("scope audit at PR time", check_scope_audit),
                ("upstream identity", lambda repo, s: [] if (s.get("upstream") or {}).get("pr_identity")
                 else ["upstream PR identity not captured (upstream --pr-json FILE)"]),
            ],
            "authority": [("remote_write",
                           "publishing requires REMOTE_WRITE granted via set-authority "
                           "with an evidence ref (explicit per-action authorization)")],
        },
    }.get(state, {"checks": [], "authority": []})


def reproduction_gate(repo, s):
    return check_reproduction(repo, s)


def red_gate(repo, s):
    return check_red(repo, s)


def green_gate(repo, s):
    return check_green_fresh(repo, s)


def validation_current_gate(repo, s):
    return check_validation_current(repo, s)


def scope_audit_gate(repo, s):
    return check_scope_audit(repo, s)


def understanding_gate(repo, s):
    return check_understanding(repo, s)


# ------------------------------------------------------------------ commands

def cmd_init(repo: Path, args) -> int:
    if session_path(repo).exists() and not args.fresh:
        print("error: session exists (%s); use --fresh" % session_path(repo), file=sys.stderr)
        return 2
    goal_path = None
    if args.goal:
        gp = Path(args.goal)
        goal_path = gp if gp.is_absolute() else (repo / gp).resolve()
    digest = None
    if goal_path and goal_path.exists():
        contract = json.loads(goal_path.read_text())
        digest = contract.get("digest")
    if not digest:
        print("error: --goal must point to an existing Goal Contract JSON "
              "(goal_compiler.py compile)", file=sys.stderr)
        return 2
    session = {
        "session_version": 1,
        "task_id": args.task_id,
        "repository": args.repository or repo.name,
        "base_sha": git_head(repo),
        "state": "DISCOVER",
        "goal": {"digest": digest, "path": str(goal_path)},
        "authority": {"read": True, "worktree_edit": False, "remote_write": False,
                      "grants": []},
        "context": {"plan": None, "pack": None, "receipt": None},
        "artifacts": {},
        "classification": None,
        "understanding": {"status": None, "confirmed_by": None},
        "scope_audit": {},
        "upstream": {},
        "blockers": [],
        "history": [{"at": now(), "event": "init", "state": "DISCOVER"}],
    }
    save_session(repo, session)
    print("session initialized: %s (state DISCOVER, base %s)"
          % (session_path(repo), (session["base_sha"] or "?")[:12]))
    return 0


def cmd_status(repo: Path, args=None) -> int:
    s = load_session(repo)
    nxt = STATES[STATES.index(s["state"]) + 1] if s["state"] != "IN_REVIEW" else None
    print("state: %s  (task %s, base %s)" % (s["state"], s["task_id"],
                                             (s.get("base_sha") or "?")[:12]))
    print("authority: worktree_edit=%s remote_write=%s" % (
        s["authority"]["worktree_edit"], s["authority"]["remote_write"]))
    if nxt:
        req = gate_requirements(nxt)
        missing = []
        for _, fn in req["checks"]:
            missing.extend(fn(repo, s))
        for auth, why in req["authority"]:
            if not s["authority"].get(auth):
                missing.append("authority %s not granted: %s" % (auth, why))
        print("next legal: %s" % nxt)
        if missing:
            print("gate gaps:")
            for m in missing:
                print("  - %s" % m)
        else:
            print("gate gaps: none — advance is legal")
    else:
        print("terminal state; upstream outcome: %s"
              % (s.get("upstream") or {}).get("outcome", "not captured"))
    if s.get("classification") in STOPPING:
        print("NOTE: classification %s is a stopping outcome — no patch expected"
              % s["classification"])
    return 0


def cmd_advance(repo: Path, args) -> int:
    s = load_session(repo)
    target = args.to
    if target not in STATES:
        print("error: unknown state %s" % target, file=sys.stderr)
        return 2
    cur = STATES.index(s["state"])
    if STATES.index(target) != cur + 1:
        print("GATE REFUSED: %s → %s is not the next state (states are linear; "
              "current %s)" % (s["state"], target, s["state"]), file=sys.stderr)
        return 1
    # a stopping classification ends the run — no patch-side state is reachable
    if s.get("classification") in STOPPING and STATES.index(target) > STATES.index("PROVE"):
        s["blockers"] = ["classification %s is a stopping outcome (duplicate, "
                         "invalid, design-blocked, ...) — the contribution ends here "
                         "with the recorded evidence; patching would compete or farm"
                         % s["classification"]]
        save_session(repo, s)
        print("GATE REFUSED: %s" % s["blockers"][0], file=sys.stderr)
        return 1
    req = gate_requirements(target)
    missing = []
    for _, fn in req["checks"]:
        missing.extend(fn(repo, s))
    for auth, why in req["authority"]:
        if not s["authority"].get(auth):
            missing.append("authority %s not granted: %s" % (auth, why))
    if missing:
        print("GATE REFUSED: cannot advance to %s" % target, file=sys.stderr)
        for m in missing:
            print("  - %s" % m, file=sys.stderr)
        s["blockers"] = missing
        save_session(repo, s)
        return 1
    s["blockers"] = []
    s["history"].append({"at": now(), "event": "advance", "from": s["state"],
                         "to": target})
    s["state"] = target
    save_session(repo, s)
    print("advanced: %s → %s" % (s["history"][-1]["from"], target))
    return 0


def cmd_set_authority(repo: Path, args) -> int:
    s = load_session(repo)
    if not args.evidence_ref:
        print("error: granting authority requires --evidence-ref (an artifact id or "
              "path recording the user's explicit authorization)", file=sys.stderr)
        return 2
    if args.grant not in ("worktree_edit", "remote_write"):
        print("error: --grant must be worktree_edit or remote_write", file=sys.stderr)
        return 2
    if not args.by_user:
        print("error: --by-user is required (authorization must be attributed to an "
              "explicit user statement, never inferred)", file=sys.stderr)
        return 2
    s["authority"][args.grant] = True
    s["authority"]["grants"].append({"grant": args.grant, "evidence_ref": args.evidence_ref,
                                     "by_user": args.by_user, "at": now()})
    s["history"].append({"at": now(), "event": "grant", "grant": args.grant,
                         "evidence_ref": args.evidence_ref})
    save_session(repo, s)
    print("authority granted: %s (evidence %s)" % (args.grant, args.evidence_ref))
    return 0


def cmd_record(repo: Path, args) -> int:
    s = load_session(repo)
    kind = args.kind
    if kind not in ("recon", "dedupe", "walkthrough", "scope-audit", "patch-intent",
                    "plan", "pack", "receipt"):
        print("error: --kind must be recon|dedupe|walkthrough|scope-audit|"
              "patch-intent|plan|pack|receipt", file=sys.stderr)
        return 2
    if kind == "scope-audit":
        if args.conclusion not in ("WITHIN_SCOPE", "ACKNOWLEDGED", "SCOPE_FINDINGS"):
            print("error: --conclusion must be WITHIN_SCOPE|ACKNOWLEDGED|SCOPE_FINDINGS",
                  file=sys.stderr)
            return 2
        s["scope_audit"] = {"conclusion": args.conclusion,
                            "reason": args.reason or "",
                            "at": now()}
    else:
        files = [f for f in (args.file or []) if Path(f).exists()]
        if args.file and not files:
            print("error: none of the --file paths exist", file=sys.stderr)
            return 2
        key = {"recon": "recon", "dedupe": "dedupe", "walkthrough": "walkthrough",
               "patch-intent": "patch_intent"}.get(kind, kind)
        s["artifacts"].setdefault(key, []).extend(files or [])
        if kind == "plan":
            s["context"]["plan"] = files[0] if files else s["context"]["plan"]
        if kind == "pack":
            s["context"]["pack"] = files[0] if files else s["context"]["pack"]
        if kind == "receipt":
            s["context"]["receipt"] = files[0] if files else s["context"]["receipt"]
    s["history"].append({"at": now(), "event": "record", "kind": kind})
    save_session(repo, s)
    print("recorded: %s" % kind)
    return 0


def cmd_set_classification(repo: Path, args) -> int:
    s = load_session(repo)
    if args.classification not in CLASSIFICATIONS:
        print("error: classification must be one of %s" % sorted(CLASSIFICATIONS),
              file=sys.stderr)
        return 2
    s["classification"] = args.classification
    s["history"].append({"at": now(), "event": "classification",
                         "value": args.classification})
    save_session(repo, s)
    print("classification: %s%s" % (args.classification,
                                    " (stopping outcome — no patch expected)"
                                    if args.classification in STOPPING else ""))
    return 0


def cmd_set_understanding(repo: Path, args) -> int:
    s = load_session(repo)
    if args.status not in UNDERSTANDING:
        print("error: --status must be one of %s" % sorted(UNDERSTANDING), file=sys.stderr)
        return 2
    if args.status == "UNDERSTOOD" and not args.confirmed_by:
        print("error: UNDERSTOOD requires --confirmed-by <human>: the agent never "
              "confirms understanding on the human's behalf", file=sys.stderr)
        return 2
    s["understanding"] = {"status": args.status, "confirmed_by": args.confirmed_by,
                          "at": now()}
    s["history"].append({"at": now(), "event": "understanding", "status": args.status})
    save_session(repo, s)
    print("understanding: %s%s" % (args.status,
                                   " (confirmed by %s)" % args.confirmed_by if args.confirmed_by else ""))
    return 0


def cmd_upstream(repo: Path, args) -> int:
    s = load_session(repo)
    p = Path(args.pr_json)
    if not p.exists():
        print("error: %s does not exist (capture PR/reviews/timeline JSON via the "
              "commands from upstream_state.py commands)", file=sys.stderr)
        return 3
    try:
        from upstream_state import classify, load_json  # reuse existing classifier
        data = load_json(p)
        pr, reviews, timeline = data if isinstance(data, list) and len(data) == 3 \
            else (data.get("pr"), data.get("reviews", []), data.get("timeline", []))
        outcome, _facts, _reason = classify(pr, reviews, timeline)
    except Exception as e:
        print("error: could not classify upstream state: %s" % e, file=sys.stderr)
        return 3
    identity = {"repo": s.get("repository"), "number": (pr or {}).get("number")}
    s["upstream"] = {"pr_identity": identity, "outcome": outcome,
                     "source_file": str(p), "at": now()}
    s["authority"]["remote_write"] = True  # a captured PR implies publication happened;
    s["authority"]["grants"].append({"grant": "remote_write",
                                     "evidence_ref": str(p), "by_user": "upstream-capture",
                                     "at": now()})
    s["history"].append({"at": now(), "event": "upstream", "outcome": outcome})
    save_session(repo, s)
    print("upstream outcome: %s (pr #%s)" % (outcome, identity["number"]))
    if outcome != "MERGED":
        print("NOTE: %s is NOT a merged contribution — never reported as success"
              % outcome)
    return 0


def cmd_reconstruct(repo: Path, args=None) -> int:
    s = load_session(repo)
    print("RESULT       RECONSTRUCTED (session %s, task %s)" % (
        (s.get("base_sha") or "?")[:12], s["task_id"]))
    print("STATE        %s | base %s | goal %s" % (
        s["state"], (s.get("base_sha") or "?")[:12], (s["goal"].get("digest") or "?")[:12]))
    if s.get("blockers"):
        for b in s["blockers"]:
            print("BLOCKER      %s" % b)
    print("NEXT         run 'status' for gate gaps, then the legal next operation")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Contribution session runtime (V5 spine).")
    ap.add_argument("repo", nargs="?", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init")
    p.add_argument("--task-id", required=True)
    p.add_argument("--repository")
    p.add_argument("--goal", required=True, help="Goal Contract JSON")
    p.add_argument("--fresh", action="store_true")
    p.set_defaults(func=lambda r, a: cmd_init(r, a))

    p = sub.add_parser("status")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("advance")
    p.add_argument("--to", required=True)
    p.set_defaults(func=cmd_advance)

    p = sub.add_parser("set-authority")
    p.add_argument("--grant", required=True)
    p.add_argument("--evidence-ref", required=True)
    p.add_argument("--by-user", required=True)
    p.set_defaults(func=cmd_set_authority)

    p = sub.add_parser("record")
    p.add_argument("--kind", required=True)
    p.add_argument("--file", action="append")
    p.add_argument("--conclusion")
    p.add_argument("--reason")
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("set-classification")
    p.add_argument("--classification", required=True)
    p.set_defaults(func=cmd_set_classification)

    p = sub.add_parser("set-understanding")
    p.add_argument("--status", required=True)
    p.add_argument("--confirmed-by")
    p.set_defaults(func=cmd_set_understanding)

    p = sub.add_parser("upstream")
    p.add_argument("--pr-json", required=True)
    p.set_defaults(func=cmd_upstream)

    p = sub.add_parser("reconstruct")
    p.set_defaults(func=cmd_reconstruct)

    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print("error: %s is not a directory" % repo, file=sys.stderr)
        return 3
    return args.func(repo, args)


if __name__ == "__main__":
    raise SystemExit(main())
