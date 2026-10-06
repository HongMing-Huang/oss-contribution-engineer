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

REMOTE_ACTIONS = {"OPEN_ISSUE", "COMMENT_ISSUE", "PUSH_BRANCH", "OPEN_PR",
                  "UPDATE_PR", "REPLY_REVIEW", "REQUEST_REREVIEW"}

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


PROD_EXCLUDES_HINT = "production = non-test paths"


def production_changes_since(repo: Path, base_sha: str) -> tuple[list[str], list[str]]:
    """Return (production_paths, test_paths) changed between base_sha and HEAD.

    Runtime bookkeeping (the evidence/session directory, the goal contract, and
    recorded workflow artifacts) is not product code and is excluded."""
    p = subprocess.run(["git", "-C", str(repo), "diff", "--name-only",
                        base_sha + "..HEAD"],
                       capture_output=True, text=True, shell=False)
    if p.returncode != 0:
        return [], []
    s = load_session(repo) if session_path(repo).exists() else {}
    bookkeeping = {".oss-contrib-evidence", ".github", ".git"}
    goal_path = (s.get("goal") or {}).get("path")
    artifact_paths = set()
    for files in (s.get("artifacts") or {}).values():
        artifact_paths.update(files)

    def rel(p: str) -> str | None:
        """Normalize a recorded (possibly absolute) path to repo-relative."""
        pp = Path(p)
        try:
            return pp.resolve().relative_to(repo).as_posix()
        except (ValueError, OSError):
            return pp.as_posix() if not pp.is_absolute() else None

    goal_rel = rel(goal_path) if goal_path else None
    artifact_rels = {rel(a) for a in artifact_paths if rel(a)}
    prod, tests = [], []
    for f in p.stdout.splitlines():
        f = f.strip()
        if not f:
            continue
        first = f.split("/")[0]
        if first in bookkeeping or f.startswith(".oss-contrib-evidence/"):
            continue
        if goal_rel and f == goal_rel:
            continue
        if f in artifact_rels:
            continue
        if is_test_path(f):
            tests.append(f)
        else:
            prod.append(f)
    return prod, tests


def is_test_path(path: str) -> bool:
    low = path.lower()
    return ("/test" in low or "/tests/" in low or low.startswith("tests/")
            or low.endswith(("_test.py", ".test.js", "_test.go", "_test.rs"))
            or "/__tests__/" in low or "conftest" in low)


def check_reproduction(repo: Path, s: dict) -> list[str]:
    missing = []
    repro = [e for e in manifest_entries(repo)
             if e.get("evidence_type") == "REPRODUCTION" and e.get("status") == "PASS"]
    if not repro:
        missing.append("reproduction evidence: no REPRODUCTION-typed witnessed "
                       "execution (evidence_manifest record --evidence-type REPRODUCTION)")
    return missing


def check_red(repo: Path, s: dict) -> list[str]:
    """RED requires a typed RED_REGRESSION witness that PASSED, bound to the
    pre-patch production state (session base SHA)."""
    missing = []
    base = s.get("base_sha")
    reds = [e for e in manifest_entries(repo)
            if e.get("evidence_type") == "RED_REGRESSION"
            and e.get("status") == "PASS" and e.get("expected_failure") is True]
    if not reds:
        missing.append("RED witness: no RED_REGRESSION-typed execution recorded as "
                       "PASS (--expect-fail --evidence-type RED_REGRESSION)")
        return missing
    if not base:
        missing.append("RED binding: session has no base SHA")
        return missing
    bound = [e for e in reds if e.get("git_head") == base]
    if not bound:
        missing.append("RED binding: RED_REGRESSION witness was recorded at HEAD %s "
                       "but the session base is %s — RED must run on the pre-patch "
                       "production state"
                       % ((reds[-1].get("git_head") or "?")[:12], base[:12]))
        return missing
    # the regression test itself must be identified and linked
    if not any(e.get("regression_id") for e in bound):
        missing.append("RED binding: RED_REGRESSION witness lacks --regression-id "
                       "(needed to bind GREEN to the same test)")
    return missing


def check_production_untouched(repo: Path, s: dict) -> list[str]:
    """RED → PATCH: production code must be unmodified since base (test-only
    changes are allowed)."""
    base = s.get("base_sha")
    if not base:
        return ["pre-patch check: session has no base SHA"]
    prod, tests = production_changes_since(repo, base)
    if prod:
        return ["pre-patch check: production file(s) already modified since base %s "
                "before a verified RED→PATCH transition: %s — RED must be recorded "
                "on the unmodified production state (test-only edits are allowed)"
                % (base[:12], ", ".join(prod[:5]))]
    return []


def check_green_fresh(repo: Path, s: dict) -> list[str]:
    missing = []
    head = git_head(repo)
    green = [e for e in manifest_entries(repo)
             if e.get("evidence_type") == "GREEN_REGRESSION"
             and e.get("kind") == "execution" and e.get("status") == "PASS"]
    if not green:
        missing.append("GREEN witness: no GREEN_REGRESSION-typed passing execution "
                       "(--evidence-type GREEN_REGRESSION)")
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
    # RED↔GREEN identity: GREEN must carry the same regression_id as the RED proof
    reds = [e for e in manifest_entries(repo)
            if e.get("evidence_type") == "RED_REGRESSION"
            and e.get("status") == "PASS" and e.get("expected_failure") is True]
    red_ids = {e.get("regression_id") for e in reds if e.get("regression_id")}
    if red_ids and not any(e.get("regression_id") in red_ids for e in green):
        missing.append("RED↔GREEN binding: GREEN_REGRESSION witness carries no "
                       "regression_id matching the RED proof (%s) — the same "
                       "regression test must pass after the fix"
                       % ", ".join(sorted(red_ids)))
        return missing
    # test identity: the regression test that proved RED must be unchanged at GREEN.
    # Comparing GREEN's own identity against the RED proof's identity catches a
    # weakened/rewritten test (a changed file digest = invalidated RED proof).
    red_by_id = {e.get("regression_id"): e for e in reds if e.get("regression_id")}
    import hashlib as _h
    for e in green:
        rid = e.get("regression_id")
        red = red_by_id.get(rid) if rid else None
        if not red:
            continue
        red_ident = {i["path"]: i["digest"] for i in red.get("test_identity") or []}
        if not red_ident:
            continue
        green_ident = {i["path"]: i["digest"] for i in e.get("test_identity") or []}
        for path, digest in red_ident.items():
            got = green_ident.get(path)
            if got is None:
                missing.append("RED↔GREEN binding: GREEN witness does not cover "
                               "regression test %s from the RED proof" % path)
                return missing
            if got != digest:
                missing.append("RED↔GREEN binding: regression test %s changed after "
                               "RED (digest %s… → %s…) — the RED proof is "
                               "invalidated; re-record RED and GREEN"
                               % (path, digest[:12], got[:12]))
                return missing
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


ARTIFACT_REQUIRED = {"type", "schema_version", "repository", "generated_by",
                     "created_at", "digest"}


def validate_artifact(path: Path, expected_type: str) -> list[str]:
    """Structured artifact validation: type/schema_version/repository/generated_by/
    created_at/digest must exist and digest must match the payload body. A bare {}
    can never pass."""
    if not path.exists():
        return ["artifact %s does not exist" % path]
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return ["artifact %s is not readable JSON: %s" % (path, e)]
    if not isinstance(data, dict):
        return ["artifact %s is not a JSON object" % path]
    absent = [k for k in ARTIFACT_REQUIRED if k not in data]
    if absent:
        return ["artifact %s is not a structured artifact: missing field(s) %s — "
                "produce it with the script's --json output (empty or ad-hoc files "
                "are not evidence)" % (path.name, ", ".join(absent))]
    if data["type"] != expected_type:
        return ["artifact %s has type %s, expected %s" % (path.name, data["type"],
                                                          expected_type)]
    body = {k: v for k, v in data.items() if k != "digest"}
    import hashlib as _h
    if _h.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() != data["digest"]:
        return ["artifact %s digest mismatch — file was modified after generation"
                % path.name]
    return []


def check_scope_audit(repo, s: dict) -> list[str]:
    sa = s.get("scope_audit") or {}
    if not sa.get("conclusion"):
        return ["scope audit: not recorded (run diff_scope_check.py --json and "
                "'record --kind scope-audit --file <json> --conclusion ...)']"]
    if sa.get("conclusion") not in ("WITHIN_SCOPE", "ACKNOWLEDGED"):
        return ["scope audit: conclusion %s is unresolved — fix drift or explicitly "
                "ACKNOWLEDGE with a reason" % sa["conclusion"]]
    artifact = sa.get("artifact")
    if not artifact:
        return ["scope audit: no structured artifact recorded (the conclusion must "
                "cite a SCOPE_AUDIT artifact)"]
    return validate_artifact(Path(artifact), "SCOPE_AUDIT")


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


def check_understanding_confirmed(repo, s: dict) -> list[str]:
    """Upstream submission readiness: DEFERRED/INCOMPLETE may allow drafting and
    local inspection, but publication requires explicit human confirmation."""
    missing = check_understanding(repo, s)
    if missing:
        return missing
    u = s["understanding"]
    if u["status"] != "UNDERSTOOD":
        return ["publication readiness: understanding status is %s — the doctrine "
                "'never submit anything the human cannot personally explain and "
                "defend' requires UNDERSTOOD (confirmed by the human) before "
                "IN_REVIEW; DEFERRED/INCOMPLETE may only allow PR draft inspection"
                % u["status"]]
    return []


def has_consumed_remote_action(s: dict, action: str) -> bool:
    for g in (s.get("authority") or {}).get("actions", []):
        if g.get("action") == action and g.get("consumed_at"):
            return True
    return False


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
                ("recon artifact", lambda repo, s: artifact_gate(repo, s, "recon",
                                                                 "REPOSITORY_RECON")),
            ],
            "authority": [],
        },
        "DEDUPLICATE": {
            "checks": [
                ("dedupe artifact", lambda repo, s: artifact_gate(repo, s, "dedupe",
                                                                  "DUPLICATE_WORK_EVIDENCE")),
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
            "checks": [("red witness", red_gate),
                       ("pre-patch production untouched", pre_patch_gate)],
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
            "checks": [("green witness fresh + RED-bound", green_gate)],
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
                ("publication understanding", check_understanding_confirmed),
            ],
            "authority": [("remote_action OPEN_PR",
                           "publishing requires an action-scoped OPEN_PR grant "
                           "(set-authority --grant remote --action OPEN_PR --target ...)")],
        },
    }.get(state, {"checks": [], "authority": []})


def reproduction_gate(repo, s):
    return check_reproduction(repo, s)


def red_gate(repo, s):
    return check_red(repo, s)


def pre_patch_gate(repo, s):
    return check_production_untouched(repo, s)


def artifact_gate(repo, s, key, expected_type):
    files = (s.get("artifacts") or {}).get(key) or []
    if not files:
        return ["%s artifact not recorded (record --kind %s --file <script --json "
                "output>)" % (key, key)]
    return validate_artifact(Path(files[-1]), expected_type)


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
        "authority": {"read": True, "worktree_edit": False,
                      "grants": [], "actions": []},
        "context": {"plan": None, "pack": None, "receipt": None},
        "artifacts": {},
        "classification": None,
        "understanding": {"status": None, "confirmed_by": None},
        "scope_audit": {},
        "upstream": {"observed": False},
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
    print("authority: worktree_edit=%s remote_actions=%s" % (
        s["authority"]["worktree_edit"],
        [g["action"] for g in s["authority"].get("actions", []) if not g.get("consumed_at")]))
    if nxt:
        req = gate_requirements(nxt)
        missing = []
        for _, fn in req["checks"]:
            missing.extend(fn(repo, s))
        for auth, why in req["authority"]:
            if auth.startswith("remote_action "):
                action = auth.split(" ", 1)[1]
                if not has_pending_remote_action(s, action):
                    missing.append("authority %s not granted: %s" % (auth, why))
            elif not s["authority"].get(auth):
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
        if auth.startswith("remote_action "):
            action = auth.split(" ", 1)[1]
            if not has_pending_remote_action(s, action):
                missing.append("authority %s not granted: %s" % (auth, why))
        elif not s["authority"].get(auth):
            missing.append("authority %s not granted: %s" % (auth, why))
    if missing:
        print("GATE REFUSED: cannot advance to %s" % target, file=sys.stderr)
        for m in missing:
            print("  - %s" % m, file=sys.stderr)
        s["blockers"] = missing
        save_session(repo, s)
        return 1
    s["blockers"] = []
    # consume one-shot remote action grants used by this transition
    if target == "IN_REVIEW":
        for g in s["authority"].get("actions", []):
            if g.get("action") == "OPEN_PR" and not g.get("consumed_at"):
                g["consumed_at"] = now()
    s["history"].append({"at": now(), "event": "advance", "from": s["state"],
                         "to": target})
    s["state"] = target
    save_session(repo, s)
    print("advanced: %s → %s" % (s["history"][-1]["from"], target))
    return 0


def has_pending_remote_action(s: dict, action: str) -> bool:
    for g in (s.get("authority") or {}).get("actions", []):
        if g.get("action") == action and not g.get("consumed_at"):
            return True
    return False


def cmd_set_authority(repo: Path, args) -> int:
    s = load_session(repo)
    if not args.evidence_ref:
        print("error: granting authority requires --evidence-ref (an artifact id or "
              "path recording the user's explicit authorization)", file=sys.stderr)
        return 2
    if not args.by_user:
        print("error: --by-user is required (authorization must be attributed to an "
              "explicit user statement, never inferred)", file=sys.stderr)
        return 2
    if args.grant == "worktree_edit":
        s["authority"]["worktree_edit"] = True
        s["authority"]["grants"].append({"grant": "worktree_edit",
                                         "evidence_ref": args.evidence_ref,
                                         "by_user": args.by_user, "at": now()})
    elif args.grant == "remote":
        # action-scoped, one-shot remote authorization (V5.1): a session-wide
        # remote_write flag can never be granted again
        if args.action not in REMOTE_ACTIONS:
            print("error: --action must be one of %s" % sorted(REMOTE_ACTIONS),
                  file=sys.stderr)
            return 2
        if not args.target:
            print("error: --target is required for a remote action grant "
                  "(e.g. OWNER/REPO#123 or OWNER/REPO)", file=sys.stderr)
            return 2
        s["authority"]["actions"].append({
            "action": args.action, "target": args.target,
            "authorized_by": args.by_user, "evidence_ref": args.evidence_ref,
            "created_at": now(), "consumed_at": None,
        })
    else:
        print("error: --grant must be worktree_edit or remote", file=sys.stderr)
        return 2
    s["history"].append({"at": now(), "event": "grant", "grant": args.grant,
                         "action": getattr(args, "action", None),
                         "target": getattr(args, "target", None),
                         "evidence_ref": args.evidence_ref})
    save_session(repo, s)
    print("authority granted: %s%s (evidence %s)" % (
        args.grant, (" " + args.action + " -> " + args.target) if args.grant == "remote" else "",
        args.evidence_ref))
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
        files = [f for f in (args.file or []) if Path(f).exists()]
        s["scope_audit"] = {"conclusion": args.conclusion,
                            "artifact": files[0] if files else None,
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
    # V5.1: capturing an existing PR is UPSTREAM_OBSERVED — it proves publication
    # happened previously and grants NOTHING. The next comment/push/PR update needs
    # its own action-scoped grant (set-authority --grant remote --action ...).
    s["upstream"] = {"observed": True, "pr_identity": identity, "outcome": outcome,
                     "source_file": str(p), "at": now()}
    s["history"].append({"at": now(), "event": "upstream-observed", "outcome": outcome})
    save_session(repo, s)
    print("upstream OBSERVED: %s (pr #%s) — this grants no remote authorization"
          % (outcome, identity["number"]))
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
    p.add_argument("--grant", required=True, help="worktree_edit | remote (action-scoped)")
    p.add_argument("--action", help="for --grant remote: %s" % "OPEN_ISSUE|COMMENT_ISSUE|PUSH_BRANCH|OPEN_PR|UPDATE_PR|REPLY_REVIEW|REQUEST_REREVIEW")
    p.add_argument("--target", help="for --grant remote: OWNER/REPO or OWNER/REPO#123")
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
