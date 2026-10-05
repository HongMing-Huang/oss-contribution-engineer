#!/usr/bin/env python3
"""build_arb_slice.py — freeze a small, diverse Agent Retrieval Bench slice.

Reads downloaded ARB v0_1 JSONL files, selects a fixed sample set across languages
(Python/Rust/Go/TS) and workflows, converts to our task schema, and emits a manifest
with base commits for reproduction. Gold = root_cause_files (+related_tests only for
code2test, where tests ARE the gold). Frozen: IDs and base commits recorded.

The slice is deliberately small (harness stability first) and is NOT a benchmark
claim — it is a second opinion beyond our click/fd seeds.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# fixed selection: id-prefix -> included; chosen for language + workflow diversity
PREFERRED = {
    "code2test": ["clap-rs/clap", "fastapi/fastapi"],          # Rust, Python
    "comment2context": ["gin-gonic/gin", "vitejs/vite"],       # Go, TS
    "trace2code": ["huggingface/diffusers", "huggingface/transformers"],  # Python (only 2 exist)
}


def query_text(task: str, q: dict) -> str:
    if task == "code2test":
        return " ".join(filter(None, [q.get("pr_title", ""), q.get("pr_body", "")[:400],
                                      "changed: " + q.get("changed_file", "")]))
    if task == "comment2context":
        return " ".join(filter(None, [q.get("pr_title", ""), q.get("review_comment", ""),
                                      "file: " + q.get("path", ""),
                                      "hunk: " + (q.get("diff_hunk_context") or "")[-300:]]))
    if task == "trace2code":
        return " ".join(filter(None, [q.get("pr_title", ""),
                                      "trace: " + (q.get("raw_signal") or "")[:400],
                                      "paths: " + " ".join(q.get("trace_paths", []))]))
    return json.dumps(q)[:400]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="/tmp/arb")
    ap.add_argument("--out", required=True, help="output tasks JSONL")
    args = ap.parse_args()
    src = Path(args.src)
    tasks = []
    manifest = {"source": "eyuansu62/agent-retrieval-bench v0_1", "frozen": [],
                "notes": ["edit2ripple absent from v0_1 public release — recorded, not "
                          "simulated; only 3 of 4 workflows covered by this slice",
                          "gold follows ARB: root_cause_files (+related_tests for "
                          "code2test); supporting/negative files are distractors, not gold"]}
    for task, repos in PREFERRED.items():
        path = src / ("%s.jsonl" % task)
        if not path.exists():
            continue
        picked: dict[str, dict] = {}
        for line in path.read_text().splitlines():
            s = json.loads(line)
            repo = s["repo"]
            if repo in repos and repo not in picked:
                picked[repo] = s
        for repo, s in picked.items():
            gold = s["gold"]
            if task == "code2test":
                gold_files = sorted(set(gold.get("related_tests", [])))
            else:
                gold_files = sorted(set(gold.get("root_cause_files", [])))
            if not gold_files:
                continue
            given = []
            if task == "comment2context":
                given = [s["query"].get("path")] if s["query"].get("path") else []
            tasks.append({
                "id": "arb-" + s["id"][:10],
                "task_type": task,
                "query": query_text(task, s["query"]),
                "anchor_files": [s["query"].get("changed_file") or s["query"].get("path") or ""]
                if (s["query"].get("changed_file") or s["query"].get("path")) else [],
                "given_files": given,
                "gold_files": gold_files,
                "meta": {"repo": repo, "base_commit": s["base_commit"],
                         "confidence": s["metadata"].get("confidence")},
            })
            manifest["frozen"].append({"id": tasks[-1]["id"], "repo": repo,
                                       "base_commit": s["base_commit"], "task": task})
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(t) + "\n" for t in tasks))
    Path(str(out) + ".manifest.json").write_text(json.dumps(manifest, indent=2))
    print("frozen slice: %d tasks -> %s" % (len(tasks), out))
    for t in tasks:
        print("  %-22s %-28s %s" % (t["task_type"], t["meta"]["repo"], t["id"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
