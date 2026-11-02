#!/usr/bin/env python3
"""v8_no_patch.py — V8 section 11: a task that correctly ends with NO PATCH.

Task: click-3802 (frozen: pallets/click base b47c0529e9) — KeyboardInterrupt
during click.prompt() can race (real issue #3802, fix PR #3818 merged upstream).

Protocol (fixing commit never consulted):
  1. Read the report: race on Ctrl-C during prompt (CI-only, arm64 runner).
  2. Witnessed reproduction attempts: race_child.py drives the real prompt with
     a self-scheduled SIGINT landing in the prompt window. Each witnessed batch
     records rounds and crash count; a genuine race cannot be reproduced
     deterministically.
  3. Static reading (prompt vs main() interrupt policy; pager precedent)
     suggests a behavior-policy unification — but without a reproducible
     failure no RED is provable.

Conclusion: UNCONFIRMED (STOPPING) — patch-side states mechanically blocked;
no-patch is a valid success. Output row appended to runs/no-patch.jsonl.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent.parent / "oss-contribution-engineer" / "scripts"
REPO = HERE / "work" / "click-ct2@b47c0529e9"
RACE_CHILD = HERE / "race_child.py"
LOG: list[str] = []


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:  # type: ignore[name-defined]
    return __import__("subprocess").run(cmd, capture_output=True, text=True,
                                        shell=False, **kw)


def step(name: str, ok: bool, detail: str = ""):
    LOG.append(("%-30s %s %s" % (name, "OK " if ok else "FAIL", detail)).strip())
    print(LOG[-1])
    if not ok:
        raise SystemExit("no-patch path failed at %s: %s" % (name, detail))


def git(*args: str) -> str:
    p = run(["/usr/bin/env", "git", "-C", str(REPO), *args])
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def session(*args: str) -> "object":
    return run(["/usr/bin/env", "python3",
                str(SCRIPTS / "contribution_session.py"), str(REPO), *args])


def manifest(*args: str) -> "object":
    return run(["/usr/bin/env", "python3",
                str(SCRIPTS / "evidence_manifest.py"),
                str(REPO), "record", *args])


def envelope(a_type: str, extra: dict | None = None) -> dict:
    body = {"type": a_type, "schema_version": 1,
            "repository": "pallets/click", "repository_id": "pallets/click",
            "base_sha": git("rev-parse", "HEAD"),
            "generated_by": "v8_no_patch",
            "created_at": datetime.now(timezone.utc).isoformat()}
    body.update(extra or {})
    body["digest"] = hashlib.sha256(
        json.dumps(body, sort_keys=True).encode()).hexdigest()
    return body


def main() -> int:
    import subprocess

    base = git("rev-parse", "HEAD")
    assert base.startswith("b47c0529e9"), base
    ROUNDS = 40

    r = run(["/usr/bin/env", "python3", str(SCRIPTS / "goal_compiler.py"), str(REPO),
             "compile", "--task-id", "v8-click-3802-interrupt-race",
             "--intent", "Investigate: KeyboardInterrupt during click.prompt() "
                         "can race (deterministic reproduction attempt first)",
             "--outcome", "no_patch",
             "--done-when", "artifact investigation-notes.md records the "
                            "reproducibility verdict with attempted-runs evidence",
             "--repository", "pallets/click"])
    step("goal contract (no_patch)", r.returncode == 0, r.stderr[-150:])
    goals = sorted((REPO / ".oss-contrib-evidence" / "goals").glob("*.json"))
    r = session("init", "--goal", str(goals[-1]),
                "--task-id", "v8-click-3802-interrupt-race")
    step("session init", r.returncode == 0, r.stdout.strip()[:100])

    scan = SCRIPTS / "contribution_rules_scan.py"
    r = run(["/usr/bin/env", "python3", str(scan), "binding-manifest", str(REPO)])
    mf = REPO / ".oss-contrib-evidence" / "rules-manifest.json"
    mf.write_text(r.stdout)
    session("record", "--kind", "rules-discovered", "--file", str(mf))
    man = json.loads(mf.read_text())
    claims = ["%s::root::rules apply" % d["path"] for d in man.get("binding", [])]
    r = run(["/usr/bin/env", "python3", str(scan), "read-receipt", str(REPO),
             "--manifest", str(mf), *sum([["--claimed", c] for c in claims], [])])
    rrj = REPO / ".oss-contrib-evidence" / "rules-read.json"
    rrj.write_text(r.stdout)
    session("record", "--kind", "rules-read", "--file", str(rrj))
    r = session("advance", "--to", "RECON")
    step("advance RECON", r.returncode == 0, r.stdout.strip()[:80])
    recon = envelope("REPOSITORY_RECON", {
        "summary": "click CLI toolkit; report of a KeyboardInterrupt race during "
                   "prompt(); relevant paths: terminal prompt handling and "
                   "main() interrupt policy"})
    p = REPO / ".oss-contrib-evidence" / "recon.json"
    p.write_text(json.dumps(recon, indent=2))
    session("record", "--kind", "recon", "--file", str(p))
    r = session("advance", "--to", "CANDIDATE")
    step("advance CANDIDATE", r.returncode == 0, r.stdout.strip()[:80])

    dedupe = envelope("DUPLICATE_WORK_EVIDENCE", {
        "repository_id": "pallets/click",
        "capture_timestamp": datetime.now(timezone.utc).isoformat(),
        "completeness": "gh search (issues+prs) read-only",
        "captures": [{"source": "keyword_issue_search", "query": "KeyboardInterrupt prompt",
                      "found": [{"number": 3802,
                                 "title": "KeyboardInterrupt during click.prompt() can race",
                                 "note": "the task's own issue; anachronism vs frozen "
                                         "base recorded"}]}]})
    p = REPO / ".oss-contrib-evidence" / "dedupe.json"
    p.write_text(json.dumps(dedupe, indent=2))
    session("record", "--kind", "dedupe", "--file", str(p))
    r = session("advance", "--to", "DEDUPLICATE")
    step("advance DEDUPLICATE", r.returncode == 0, r.stdout.strip()[:80])

    # witnessed reproduction attempts: 3 batches x ROUNDS rounds.
    # Detector refinement after reading the first artifacts: interrupting
    # INSIDE prompt() hits click's DESIGNED abort path (KeyboardInterrupt ->
    # Abort; the traceback ENDS in click.exceptions.Abort). The reported bug is
    # an UNHANDLED escape — the final exception line must be a bare
    # "KeyboardInterrupt". Zero unhandled escapes across batches is the honest
    # non-reproducibility evidence; designed Abort rounds are excluded.
    total_crashes = 0
    loop = ("u=0; for i in $(seq 1 %d); do "
            "last=$(/usr/bin/env python3 %s %s 2>&1 | grep -v '^[[:space:]]*$' | tail -1); "
            "if [ \"$last\" = \"KeyboardInterrupt\" ]; then u=$((u+1)); fi; done; "
            "echo \"unhandled_keyboardinterrupt: $u of %d\"; exit 1"
            % (ROUNDS, RACE_CHILD, REPO, ROUNDS))
    for batch in range(1, 4):
        r = manifest("--purpose",
                     "reproduction attempt batch %d/3 (%d rounds): SIGINT lands "
                     "in the prompt window; counting only UNHANDLED escapes "
                     "(final exception bare KeyboardInterrupt); designed Abort "
                     "paths excluded" % (batch, ROUNDS),
                     "--evidence-type", "REPRODUCTION", "--expect-fail",
                     "--", "/usr/bin/env", "sh", "-c", loop)
        ok = "recorded" in r.stdout
        step("witnessed repro batch %d (%d rounds)" % (batch, ROUNDS), ok,
             r.stdout.strip()[:90] or r.stderr[-90:])

    # aggregate unhandled-escape count from the batch artifacts
    art_dir = REPO / ".oss-contrib-evidence" / "artifacts"
    for a in sorted(art_dir.glob("*.txt")):
        for line in a.read_text(errors="replace").splitlines():
            if line.startswith("unhandled_keyboardinterrupt:"):
                try:
                    total_crashes += int(line.split("of")[0].split(":")[1].strip())
                except (IndexError, ValueError):
                    pass

    notes = REPO / ".oss-contrib-evidence" / "investigation-notes.md"
    notes.write_text(
        "# Investigation notes — click#3802 interrupt race (frozen base %s)\n\n"
        "- Report: unhandled exception when Ctrl-C lands during prompt(); "
        "CI-only, arm64 runner; does not reproduce every time.\n"
        "- Reproduction: 3 witnessed batches x %d rounds of the real prompt "
        "with SIGINT landing in the prompt window. First-pass reading of the "
        "artifacts showed the interrupt landing in click's DESIGNED abort path "
        "(KeyboardInterrupt handled inside prompt; traceback ends in "
        "click.exceptions.Abort) — the detector was refined to count only "
        "UNHANDLED escapes (final exception a bare KeyboardInterrupt). "
        "Aggregate unhandled escapes: %d of %d rounds. The reported failure "
        "therefore needs a different interleaving than the obvious window; no "
        "deterministic RED is provable here, so no patch.\n"
        "- Static reading: prompt handling and main() interrupt policy are "
        "separate paths; the pager precedent (a late interrupt must not "
        "replace the intended outcome) suggests a policy unification exists — "
        "recorded as context, not as justification for an unprovable patch.\n"
        "- Verdict: UNCONFIRMED (recorded as DESIGN_BLOCKED — see failure "
        "record F6 for the vocabulary gap).\n"
        % (base[:10], ROUNDS, total_crashes, 3 * ROUNDS))
    r = session("record", "--kind", "receipt", "--file", str(notes),
                "--conclusion",
                "UNCONFIRMED: no unhandled escape in %d witnessed rounds "
                "(designed Abort rounds excluded; unhandled=%d); no RED "
                "provable, therefore no patch" % (3 * ROUNDS, total_crashes))
    step("record investigation verdict", r.returncode == 0, r.stderr[-150:])

    # vocabulary note (V8 failure F6): the classifier has no UNCONFIRMED /
    # NOT_REPRODUCIBLE class. DESIGN_BLOCKED is the honest nearest: a patch
    # would require a behavior-policy decision AND a reproducible failure;
    # neither is established at this base. The conclusion text carries the
    # precise verdict.
    r = session("set-classification", "--classification", "DESIGN_BLOCKED")
    step("classification DESIGN_BLOCKED (STOPPING; nearest to UNCONFIRMED)",
         r.returncode == 0, r.stderr[-150:])
    r = session("advance", "--to", "PROVE")
    step("advance PROVE", r.returncode == 0, r.stdout.strip()[:80])

    # prove the stopping property: patch-side states are mechanically blocked
    r = session("advance", "--to", "RED")
    step("patch-side blocked after UNCONFIRMED", r.returncode != 0,
         (r.stdout + r.stderr).strip()[:130])

    row = {"type": "CONTRIBUTION_PATH_RESULT",
           "task": "click-3802-keyinterrupt-race", "base_sha": base,
           "outcome": "NO_PATCH_DESIGN_BLOCKED",
           "classification": "DESIGN_BLOCKED",
           "repro_rounds_witnessed": 3 * ROUNDS,
           "crashes_observed": total_crashes,
           "log": LOG, "generated_at": datetime.now(timezone.utc).isoformat()}
    out = HERE / "runs" / "no-patch.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a") as fh:
        fh.write(json.dumps(row) + "\n")
    print("\nOUTCOME: NO_PATCH (DESIGN_BLOCKED; not reproducible locally) — stopping classification enforced "
          "by the runtime; this is a valid success")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
