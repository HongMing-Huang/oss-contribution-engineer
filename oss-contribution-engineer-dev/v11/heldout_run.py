#!/usr/bin/env python3
"""heldout_run.py — run session investigate on a held-out task and score file
recall against the frozen gold. Appends a raw result row to runs/.

Usage: heldout_run.py <task_id> <tag>   (tag: baseline|after)
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS_ROOT = HERE.parents[1]
SKILL = (SKILLS_ROOT / "oss-contribution-engineer" / "scripts").resolve()
S = SKILL / "contribution_session.py"
G = SKILL / "goal_compiler.py"

tasks = {t["task_id"]: t for t in json.loads((HERE / "heldout-tasks.json").read_text())}
task = tasks[sys.argv[1]]
tag = sys.argv[2]
R = Path(task["worktree"]).resolve()
if not str(R).startswith(str(HERE)):
    print("refusing worktree outside v11 dir", file=sys.stderr)
    sys.exit(2)


def py(*a):
    return subprocess.run(["/usr/bin/env", "python3", *a],
                          capture_output=True, text=True, shell=False)


g = py(str(G), str(R), "compile", "--task-id", task["task_id"] + "-" + tag,
       "--intent", "Investigate: " + task["query"],
       "--done-when", "run: true", "--repository", task["repo_slug"])
assert g.returncode == 0, g.stderr
contract = sorted((R / ".oss-contrib-evidence" / "goals").glob("*.json"))[-1]
r = py(str(S), str(R), "init", "--task-id", task["task_id"] + "-" + tag,
       "--goal", str(contract), "--fresh")
assert r.returncode == 0, r.stderr
r = py(str(S), str(R), "investigate", "--task-text", task["query"],
       "--task-type", task["task_type"])
ok = r.returncode == 0
st = json.loads((R / ".oss-contrib-evidence" / "investigation.json").read_text())
gold = set(task["gold_prod_files"])
cands = st.get("candidate_files") or []
roots = [c["path"] for c in st.get("candidate_root_causes") or []]
hits = [f for f in cands if f in gold]
row = {"task_id": task["task_id"], "tag": tag, "ok": ok,
       "gold": sorted(gold), "candidate_files": cands[:10],
       "file_recall": round(len(hits) / len(gold), 3),
       "gold_rank": (cands.index(hits[0]) + 1) if hits else None,
       "root_cause_hits": len([f for f in roots if f in gold]),
       "backends_selected": (st.get("context", {}).get("backends") or {}).get("selected"),
       "latency_ms": sum((st.get("context", {}).get("stage_ms") or {}).values())}
out = HERE / "runs" / "heldout-results.jsonl"
out.parent.mkdir(exist_ok=True)
with out.open("a") as fh:
    fh.write(json.dumps(row) + "\n")
print(json.dumps(row, indent=2))
