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
import hashlib
import json
import re
import subprocess
import sys
import uuid
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

# V5.2 upstream review substates (lifecycle, capable of loops). The main
# contribution phase stays linear; the upstream phase is a substate on the session.
UPSTREAM_SUBSTATES = {"NONE", "WAITING_FOR_REVIEW", "CHANGES_REQUESTED",
                      "READY_FOR_REREVIEW", "MERGED", "CLOSED_NOT_MERGED",
                      "SUPERSEDED", "WITHDRAWN", "DROPPED_OR_STALE"}


def repository_identity(repo: Path) -> str:
    """Deterministic repository identity: prefer the canonical origin slug
    (owner/repo from the remote URL); fall back to a local fingerprint
    ('local-' + first 12 hex of sha256(realpath)) for repositories without a
    remote. Both forms are stable across filesystem moves for the remote case."""
    p = subprocess.run(["git", "-C", str(repo), "remote", "get-url", "origin"],
                       capture_output=True, text=True, shell=False)
    if p.returncode == 0:
        url = p.stdout.strip()
        m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", url)
        if m:
            return m.group(1)
    root = subprocess.run(["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
                          capture_output=True, text=True, shell=False)
    fingerprint = hashlib.sha256(
        str(Path(root.stdout.strip() or str(repo)).resolve()).encode()).hexdigest()[:12]
    return "local-" + fingerprint

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
    """Return (production_paths, test_paths) changed between base_sha and the
    ACTUAL worktree state — V5.2 hole G: base..HEAD commits alone miss staged,
    unstaged and untracked production edits. Covered surfaces:
      - committed changes   (git diff --name-only base..HEAD)
      - staged + unstaged   (git diff --name-only HEAD)
      - untracked files     (git ls-files --others --exclude-standard)

    Runtime bookkeeping (the evidence/session directory, the goal contract, and
    recorded workflow artifacts) is not product code and is excluded."""
    p = subprocess.run(["git", "-C", str(repo), "diff", "--name-only",
                        base_sha + "..HEAD"],
                       capture_output=True, text=True, shell=False)
    if p.returncode != 0:
        return [], []
    committed = p.stdout.splitlines()
    p = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", "HEAD"],
                       capture_output=True, text=True, shell=False)
    working = p.stdout.splitlines() if p.returncode == 0 else []
    p = subprocess.run(["git", "-C", str(repo), "ls-files", "--others",
                        "--exclude-standard"],
                       capture_output=True, text=True, shell=False)
    untracked = p.stdout.splitlines() if p.returncode == 0 else []
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
    seen = set()
    for f in committed + working + untracked:
        f = f.strip()
        if not f or f in seen:
            continue
        seen.add(f)
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
    # the regression test itself must be identified and linked, AND carry
    # test-file identity (V5.2 hole F: without it the RED proof cannot be
    # bound to GREEN — the test used for RED is unprovable)
    if not any(e.get("regression_id") for e in bound):
        missing.append("RED binding: RED_REGRESSION witness lacks --regression-id "
                       "(needed to bind GREEN to the same test)")
    if not any(e.get("test_identity") for e in bound):
        # V5.2 hole F: without test-file identity the RED proof cannot be bound
        # to GREEN — which test was used for RED is unprovable
        missing.append("RED binding: RED_REGRESSION witness lacks --test-file "
                       "identity (the GREEN proof must be bound to the same test; "
                       "a regression proof without test identity is not strongly "
                       "bound)")
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
        # V5.2 (goal item 10): history vs current active evidence. A FAIL is
        # superseded when a later PASS of the same evidence_type exists (the same
        # validation requirement rerun); historical failures stay visible in the
        # report but only ACTIVE failures block.
        executions = [e for e in entries if e.get("kind") == "execution"]
        active_fails = 0
        for e in executions:
            if e.get("status") != "FAIL":
                continue
            superseded = any(
                later.get("status") == "PASS"
                and later.get("evidence_type") == e.get("evidence_type")
                and later.get("id", 0) > e.get("id", 0)
                for later in executions)
            if not superseded:
                active_fails += 1
        if active_fails:
            missing.append("validation: %d command(s) FAIL with no later passing "
                           "rerun of the same validation requirement" % active_fails)
    stale = report["summary"].get("stale", 0)
    if stale:
        missing.append("validation: %d head-bound record(s) are STALE for current HEAD"
                       % stale)
    # V5.2 review loop: revalidation debt after an accepted review change
    if s.get("review_revalidation_required"):
        since = s.get("review_revalidation_since") or ""
        fresh = [e for e in entries
                 if e.get("kind") == "execution" and e.get("status") == "PASS"
                 and e.get("head_bound") and e.get("timestamp", "") > since]
        if not fresh:
            missing.append("revalidation: review change accepted at %s — RED -> "
                           "GREEN -> validation must be re-run and re-recorded "
                           "before publication" % since[:19])
    if report["summary"]["not_executed"]:
        missing.append("validation: %d planned level(s) not executed — record "
                       "record-skip with a reason or run them"
                       % report["summary"]["not_executed"])
    if s.get("review_revalidation_required") and not missing:
        s["review_revalidation_required"] = False
        s["history"].append({"at": now(), "event": "revalidation-complete"})
        save_session(repo, s)
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
                "'record --kind scope-audit --file <json> ...)']"]
    artifact = sa.get("artifact")
    if not artifact:
        return ["scope audit: no structured artifact recorded (the conclusion must "
                "cite a SCOPE_AUDIT artifact)"]
    problems = validate_artifact(Path(artifact), "SCOPE_AUDIT")
    if problems:
        return problems
    # V5.2: the ARTIFACT is authoritative for the machine finding. The recorded
    # conclusion must agree with it (no relabelling); a human ACKNOWLEDGED
    # decision is modelled separately, never overwriting the finding.
    data = json.loads(Path(artifact).read_text())
    if data.get("conclusion") != sa["conclusion"]:
        return ["scope audit: recorded conclusion %r disagrees with the artifact's "
                "authoritative conclusion %r — the machine finding cannot be "
                "relabelled" % (sa["conclusion"], data.get("conclusion"))]
    session_repo_id = s.get("repository_id") or repository_identity(repo)
    if data.get("repository_id") != session_repo_id:
        return ["scope audit: artifact belongs to repository %r, not this session (%r)"
                % (data.get("repository_id"), session_repo_id)]
    if sa["conclusion"] == "SCOPE_FINDINGS":
        ack = sa.get("acknowledgement") or {}
        if not ack.get("acknowledged"):
            return ["scope audit: SCOPE_FINDINGS unresolved — fix the drift, or "
                    "record the separate human decision with 'acknowledge-scope-finding "
                    "--reason ... --by-user ...' (finding and acknowledgement are "
                    "preserved separately)"]
        if not ack.get("by_user"):
            return ["scope audit: acknowledgement requires --by-user (human decision)"]
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
                ("rules read", check_rules_read),
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
                ("OPEN_PR receipt bound to this upstream", check_open_pr_receipt),
            ],
            "authority": [],
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
    problems = validate_artifact(Path(files[-1]), expected_type)
    if problems:
        return problems
    # V5.2 binding: integrity (digest) is not applicability. The artifact must
    # belong to THIS session — repository identity and, for base-bound artifact
    # types, the exact base revision.
    data = json.loads(Path(files[-1]).read_text())
    session_repo_id = s.get("repository_id") or repository_identity(repo)
    if data.get("repository_id") != session_repo_id:
        return ["artifact %s belongs to repository %r, not this session (%r) — "
                "wrong-repository replay rejected"
                % (files[-1], data.get("repository_id"), session_repo_id)]
    if expected_type in ("REPOSITORY_RECON", "DUPLICATE_WORK_EVIDENCE"):
        if data.get("base_sha") != s.get("base_sha"):
            return ["artifact %s was generated at base %s but this session's base "
                    "is %s — wrong-revision replay rejected; regenerate at the "
                    "current base" % (files[-1], (data.get("base_sha") or "?")[:12],
                                      (s.get("base_sha") or "?")[:12])]
    if data.get("task_id") and data["task_id"] != s.get("task_id"):
        return ["artifact %s belongs to task %r, not this session (%r)"
                % (files[-1], data["task_id"], s.get("task_id"))]
    if data.get("goal_digest") and data["goal_digest"] != (s.get("goal") or {}).get("digest"):
        return ["artifact %s was produced under goal %s but this session's goal is "
                "%s" % (files[-1], data["goal_digest"],
                        (s.get("goal") or {}).get("digest"))]
    return []


def green_gate(repo, s):
    return check_green_fresh(repo, s)


def validation_current_gate(repo, s):
    return check_validation_current(repo, s)


def scope_audit_gate(repo, s):
    return check_scope_audit(repo, s)


def understanding_gate(repo, s):
    return check_understanding(repo, s)


def check_rules_read(repo, s) -> list[str]:
    """V5.3: RULES_DISCOVERED (the scan) is not proof of reading. The runtime
    discovers binding docs itself (auto-scan); when any exist, a RULES_READ
    receipt covering every binding path with a digest matching the CURRENT
    file is required before CANDIDATE. If the repo has no binding docs, the
    gate passes (nothing to read). Nested/subsystem rules override broader
    defaults where applicable."""
    from contribution_rules_scan import binding_manifest as _scan_binding
    manifest = _scan_binding(repo, max_depth=4)
    binding = manifest.get("binding") or []
    if not binding:
        return []  # no binding rules discovered — nothing to read
    read_files = (s.get("artifacts") or {}).get("rules_read") or []
    if not read_files:
        return ["RULES_DISCOVERED without RULES_READ: %d binding document(s) "
                "(%s) discovered but not proven fully read — read them "
                "completely and record a read-receipt (contribution_rules_scan.py "
                "read-receipt)" % (len(binding),
                                   ", ".join(b["path"] for b in binding))]
    problems = validate_artifact(Path(read_files[-1]), "RULES_READ")
    if problems:
        return problems
    receipt = json.loads(Path(read_files[-1]).read_text())
    covered = {c["path"]: c for c in receipt.get("covered", [])}
    import hashlib as _h
    missing = []
    for b in binding:
        c = covered.get(b["path"])
        current = _h.sha256((repo / b["path"]).read_bytes()).hexdigest() \
            if (repo / b["path"]).exists() else None
        if not c:
            missing.append("binding doc %s not proven read" % b["path"])
        elif c["digest"] != current:
            missing.append("%s changed after it was read — re-read and "
                           "re-record" % b["path"])
    if receipt.get("uncovered"):
        missing.append("receipt leaves %d binding doc(s) uncovered: %s"
                       % (len(receipt["uncovered"]),
                          ", ".join(u["path"] for u in receipt["uncovered"])))
    return missing


def check_open_pr_receipt(repo, s):
    """V5.2 remote causality: IN_REVIEW requires a performed-action RECEIPT
    (grant -> action -> resulting identity), not a bare grant. The receipt's
    target repository must match the captured upstream identity (authorization
    is bound to action AND target)."""
    receipts = [r for r in s["authority"].get("receipts", [])
                if r.get("action") == "OPEN_PR"]
    if not receipts:
        return ["no OPEN_PR action receipt — publishing requires an explicit "
                "authorization (set-authority --grant remote --action OPEN_PR) "
                "and the performed action must be receipted "
                "(record-remote-action --grant-id ...)"]
    identity = (s.get("upstream") or {}).get("pr_identity") or {}
    upstream_repo = (identity.get("repo") or "").lower()
    for r in reversed(receipts):  # latest receipt wins
        target_repo = (r.get("target") or "").split("#")[0].lower()
        if upstream_repo and target_repo and target_repo != upstream_repo:
            return ["OPEN_PR receipt target %r does not match the captured "
                    "upstream identity %r — authorization is bound to both the "
                    "action and the target" % (r.get("target"), upstream_repo)]
        if identity.get("number") is not None and r.get("resulting_identity") \
                and not str(r["resulting_identity"]).endswith("#%s" % identity["number"]):
            continue  # resulting number differs; check other receipts
        return []
    return ["OPEN_PR receipt does not cover the captured upstream PR "
            "#%s" % identity.get("number")]


# ------------------------------------------------------------------ commands

def cmd_init(repo: Path, args) -> int:
    if session_path(repo).exists() and not args.fresh:
        print("error: session exists (%s); use --fresh" % session_path(repo), file=sys.stderr)
        return 2
    goal_path = None
    if args.goal:
        gp = Path(args.goal)
        goal_path = gp if gp.is_absolute() else (repo / gp).resolve()
    contract = None
    if goal_path and goal_path.exists():
        # V5.2: verified loading — the digest is RECOMPUTED from the body, so a
        # tampered contract with a retained digest field is rejected here.
        from goal_compiler import load_contract  # reuse verified loader
        try:
            contract = load_contract(goal_path)
        except json.JSONDecodeError as e:
            print("error: goal contract is not valid JSON: %s" % e, file=sys.stderr)
            return 2
        except SystemExit:
            print("error: goal contract digest verification failed", file=sys.stderr)
            return 2
    if not contract or not contract.get("digest"):
        print("error: --goal must point to an existing verified Goal Contract JSON "
              "(goal_compiler.py compile)", file=sys.stderr)
        return 2
    repo_id = repository_identity(repo)
    if contract.get("repository") and repo_id != contract["repository"] \
            and contract["repository"] != repo.name:
        print("GATE REFUSED: goal contract was compiled for repository %s but this "
              "session's repository identity is %s"
              % (contract["repository"], repo_id), file=sys.stderr)
        return 1
    session = {
        "session_version": 2,
        "task_id": args.task_id or contract.get("task_id") or "task",
        "repository": repo_id,
        "repository_id": repo_id,
        "base_sha": git_head(repo),
        "state": "DISCOVER",
        "goal": {"digest": contract["digest"], "path": str(goal_path)},
        "authority": {"read": True, "worktree_edit": False,
                      "grants": [], "actions": [], "receipts": []},
        "context": {"plan": None, "pack": None, "receipt": None},
        "artifacts": {},
        "classification": None,
        "classification_evidence": None,
        "understanding": {"status": None, "confirmed_by": None},
        "scope_audit": {},
        "upstream": {"observed": False, "substate": "NONE"},
        "review_revalidation_required": False,
        "blockers": [],
        "history": [{"at": now(), "event": "init", "state": "DISCOVER"}],
    }
    save_session(repo, session)
    print("session initialized: %s (state DISCOVER, repo %s, base %s)"
          % (session_path(repo), repo_id, (session["base_sha"] or "?")[:12]))
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
            "grant_id": uuid.uuid4().hex[:12],
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
                    "plan", "pack", "receipt", "rules-discovered", "rules-read"):
        print("error: --kind must be recon|dedupe|walkthrough|scope-audit|"
              "patch-intent|plan|pack|receipt|rules-discovered|rules-read",
              file=sys.stderr)
        return 2
    if kind in ("rules-discovered", "rules-read"):
        files = [f for f in (args.file or []) if Path(f).exists()]
        if not files:
            print("error: %s requires --file (the structured artifact)"
                  % kind, file=sys.stderr)
            return 2
        expected = "RULES_DISCOVERED" if kind == "rules-discovered" else "RULES_READ"
        problems = validate_artifact(Path(files[0]), expected)
        if problems:
            for pr in problems:
                print("error: %s" % pr, file=sys.stderr)
            return 2
        key = {"rules-discovered": "rules_discovered",
               "rules-read": "rules_read"}[kind]
        s["artifacts"].setdefault(key, []).extend(files)
        s["history"].append({"at": now(), "event": "record", "kind": kind})
        save_session(repo, s)
        print("recorded: %s" % kind)
        return 0
    if kind == "scope-audit":
        files = [f for f in (args.file or []) if Path(f).exists()]
        if not files:
            print("error: scope-audit requires --file (the SCOPE_AUDIT artifact; "
                  "an unsupported --conclusion claim is not evidence)", file=sys.stderr)
            return 2
        artifact_path = files[0]
        problems = validate_artifact(Path(artifact_path), "SCOPE_AUDIT")
        if problems:
            for pr in problems:
                print("error: %s" % pr, file=sys.stderr)
            return 2
        data = json.loads(Path(artifact_path).read_text())
        derived = data.get("conclusion")
        if args.conclusion and args.conclusion != derived:
            # V5.2 (hole D): the artifact is authoritative; relabelling refused
            print("GATE REFUSED: recorded conclusion %r disagrees with the "
                  "artifact's authoritative conclusion %r — the machine finding "
                  "cannot be relabelled; fix the drift or use "
                  "'acknowledge-scope-finding' for the human decision"
                  % (args.conclusion, derived), file=sys.stderr)
            return 1
        s["scope_audit"] = {"conclusion": derived,
                            "artifact": artifact_path,
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
    # V5.2: GOOD_CANDIDATE must cite the dedupe evidence bundle the judgment used
    # (provenance, not judgment — the runtime still does not decide quality).
    evidence_bundle = None
    if args.classification == "GOOD_CANDIDATE":
        bundles = (s.get("artifacts") or {}).get("dedupe") or []
        if not bundles:
            print("error: GOOD_CANDIDATE requires recorded dedupe evidence "
                  "(record --kind dedupe --file <bundle>) — the classification "
                  "must record which evidence the judgment was based on",
                  file=sys.stderr)
            return 1
        evidence_bundle = bundles[-1]
    s["classification"] = args.classification
    s["classification_evidence"] = {"bundle": evidence_bundle, "at": now()}
    s["history"].append({"at": now(), "event": "classification",
                         "value": args.classification,
                         "evidence_bundle": evidence_bundle})
    save_session(repo, s)
    print("classification: %s%s%s" % (
        args.classification,
        " (based on dedupe bundle %s)" % evidence_bundle if evidence_bundle else "",
        " (stopping outcome — no patch expected)"
        if args.classification in STOPPING else ""))
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
    identity = {"repo": s.get("repository_id") or s.get("repository"),
                "number": (pr or {}).get("number")}
    # V5.1/V5.2: capturing an existing PR is UPSTREAM_OBSERVED — it proves
    # publication happened previously and grants NOTHING. Remote causality runs
    # grant -> performed action receipt -> observation; never the reverse.
    substate = outcome if outcome in UPSTREAM_SUBSTATES else "NONE"
    s["upstream"] = {"observed": True, "pr_identity": identity, "outcome": outcome,
                     "substate": substate, "source_file": str(p), "at": now()}
    s["history"].append({"at": now(), "event": "upstream-observed", "outcome": outcome,
                         "substate": substate})
    save_session(repo, s)
    print("upstream OBSERVED: %s (pr #%s, substate %s) — this grants no remote "
          "authorization" % (outcome, identity["number"], substate))
    if outcome != "MERGED":
        print("NOTE: %s is NOT a merged contribution — never reported as success"
              % outcome)
    return 0


def cmd_record_remote_action(repo: Path, args) -> int:
    """V5.2 remote causality: a performed remote action produces a RECEIPT bound
    to a prior grant. Authorization that merely coexists with an already-observed
    upstream object does not legitimize it — an OPEN_PR grant recorded after the
    upstream capture is refused (authorization must precede observation)."""
    s = load_session(repo)
    grant = None
    for g in s["authority"].get("actions", []):
        if g.get("grant_id") == args.grant_id:
            grant = g
            break
    if not grant:
        print("error: no grant with id %s" % args.grant_id, file=sys.stderr)
        return 2
    if grant.get("consumed_at"):
        print("error: grant %s already consumed at %s (one-shot grants)"
              % (args.grant_id, grant["consumed_at"]), file=sys.stderr)
        return 1
    if grant["action"] == "OPEN_PR" and (s.get("upstream") or {}).get("observed"):
        print("GATE REFUSED: upstream was already observed before this grant — a "
              "post-hoc authorization cannot legitimize an already-observed remote "
              "action", file=sys.stderr)
        return 1
    grant["consumed_at"] = now()
    receipt = {
        "grant_id": grant["grant_id"], "action": grant["action"],
        "target": grant["target"], "performed_at": now(),
        "resulting_identity": args.resulting or None,
        "recorded_by": args.by_user,
    }
    s["authority"]["receipts"].append(receipt)
    s["history"].append({"at": now(), "event": "remote-action",
                         "action": grant["action"], "target": grant["target"]})
    save_session(repo, s)
    print("remote action receipt recorded: %s -> %s (grant %s)"
          % (grant["action"], args.resulting or grant["target"], grant["grant_id"]))
    return 0


def cmd_accept_review_change(repo: Path, args) -> int:
    """Review-driven revision loop: a captured CHANGES_REQUESTED substate with an
    accepted change re-enters PATCH. Prior validation is invalidated (revalidation
    debt) until RED -> GREEN -> validation run at the new state."""
    s = load_session(repo)
    if (s.get("upstream") or {}).get("substate") != "CHANGES_REQUESTED":
        print("GATE REFUSED: accept-review-change requires the captured upstream "
              "substate CHANGES_REQUESTED (run 'upstream --pr-json' on the captured "
              "review state first)", file=sys.stderr)
        return 1
    if not s["authority"].get("worktree_edit"):
        print("GATE REFUSED: re-entering PATCH requires worktree_edit authority",
              file=sys.stderr)
        return 1
    if not args.reason:
        print("error: --reason is required (what was accepted and why)", file=sys.stderr)
        return 2
    s["review_revalidation_required"] = True
    s["review_revalidation_since"] = now()
    s["state"] = "PATCH"
    s["history"].append({"at": now(), "event": "accept-review-change",
                         "reason": args.reason, "by_user": args.by_user,
                         "reentered": "PATCH"})
    save_session(repo, s)
    print("review change accepted: re-entered PATCH; prior validation is "
          "invalidated until RED -> GREEN -> validation complete")
    return 0


def cmd_acknowledge_scope_finding(repo: Path, args) -> int:
    """V5.2: the human decision on SCOPE_FINDINGS is recorded SEPARATELY — the
    machine finding is preserved, never overwritten by the acknowledgement."""
    s = load_session(repo)
    sa = s.get("scope_audit") or {}
    if sa.get("conclusion") != "SCOPE_FINDINGS":
        print("error: acknowledge-scope-finding requires a recorded SCOPE_FINDINGS "
              "(there is nothing to acknowledge)", file=sys.stderr)
        return 2
    s["scope_audit"]["acknowledgement"] = {"acknowledged": True,
                                           "by_user": args.by_user,
                                           "reason": args.reason, "at": now()}
    s["history"].append({"at": now(), "event": "scope-acknowledged",
                         "by_user": args.by_user})
    save_session(repo, s)
    print("SCOPE_FINDINGS acknowledged by %s (finding preserved separately)"
          % args.by_user)
    return 0


def cmd_request_rereview(repo: Path, args) -> int:
    """READY_FOR_REREVIEW: requires a real CHANGES_REQUESTED upstream signal,
    no revalidation debt (fresh validation), and an explicit REQUEST_REREVIEW
    authorization (consumed here, receipt recorded)."""
    s = load_session(repo)
    if (s.get("upstream") or {}).get("substate") != "CHANGES_REQUESTED":
        print("GATE REFUSED: request-rereview requires the captured upstream "
              "substate CHANGES_REQUESTED — a rereview request without a real "
              "review signal is an assertion, not evidence", file=sys.stderr)
        return 1
    # validation current is checked FIRST — a passing rerun clears the
    # revalidation debt (check_validation_current persists the cleared flag)
    missing = check_validation_current(repo, s)
    if missing:
        print("GATE REFUSED: validation is not current", file=sys.stderr)
        for m in missing:
            print("  - %s" % m, file=sys.stderr)
        return 1
    if s.get("review_revalidation_required"):
        print("GATE REFUSED: revalidation debt outstanding — run RED -> GREEN -> "
              "validation after the accepted review change first", file=sys.stderr)
        return 1
    grant = None
    for g in s["authority"].get("actions", []):
        if g.get("action") == "REQUEST_REREVIEW" and not g.get("consumed_at"):
            grant = g
            break
    if not grant:
        print("GATE REFUSED: an explicit REQUEST_REREVIEW authorization is "
              "required (set-authority --grant remote --action REQUEST_REREVIEW "
              "--target OWNER/REPO#N)", file=sys.stderr)
        return 1
    grant["consumed_at"] = now()
    s["authority"]["receipts"].append({
        "grant_id": grant["grant_id"], "action": "REQUEST_REREVIEW",
        "target": grant["target"], "performed_at": now(),
        "resulting_identity": grant["target"],
        "recorded_by": grant.get("authorized_by", "unknown"),
    })
    s["upstream"]["substate"] = "READY_FOR_REREVIEW"
    s["history"].append({"at": now(), "event": "request-rereview",
                         "target": grant["target"]})
    save_session(repo, s)
    print("READY_FOR_REREVIEW: revalidation current; rereview request authorized "
          "and receipted (grant %s)" % grant["grant_id"])
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

    p = sub.add_parser("acknowledge-scope-finding")
    p.add_argument("--reason", required=True)
    p.add_argument("--by-user", required=True)
    p.set_defaults(func=cmd_acknowledge_scope_finding)

    p = sub.add_parser("record-remote-action")
    p.add_argument("--grant-id", required=True)
    p.add_argument("--resulting", help="resulting upstream identity, e.g. OWNER/REPO#123")
    p.add_argument("--by-user", required=True)
    p.set_defaults(func=cmd_record_remote_action)

    p = sub.add_parser("accept-review-change")
    p.add_argument("--reason", required=True)
    p.add_argument("--by-user", required=True,
                   help="the human who accepted the review change")
    p.set_defaults(func=cmd_accept_review_change)

    p = sub.add_parser("request-rereview")
    p.set_defaults(func=cmd_request_rereview)

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
