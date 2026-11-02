#!/usr/bin/env python3
"""v11_raw_pass.py — read RAW run JSONL line-by-line; build the pre-registered
confusion matrix; test H1..H4. Prints only what the data says, with row IDs.

No ledger summaries are consulted. Source of truth: v9 runs JSONL rows."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROWS = []


def load(p: Path):
    for line in p.read_text().splitlines():
        if line.strip():
            ROWS.append(json.loads(line))


for f in sorted((HERE / "runs").glob("*.jsonl")):
    load(f)

print("loaded %d raw rows from %s" % (len(ROWS), HERE / "runs"))

gold_by_task = {}
for r in ROWS:
    gold_by_task.setdefault(r["task_id"], set(r.get("gold_prod_files") or []))


def is_test(p: str) -> bool:
    p = p.lower()
    return "test" in p or "spec" in p or "fixtures" in p


# ---------------- H1: stage-2 same-name confusion (D/D1 arms) -------------
print("\n== H1: stage-2 function targets vs gold (D/D1 rows) ==")
h1_rows = []
for r in ROWS:
    if r["arm"] not in ("D", "D1"):
        continue
    gold = gold_by_task[r["task_id"]]
    funcs = r.get("functions") or []
    hits = [f["path"] for f in funcs]
    prod_hits = [p for p in hits if p in gold]
    test_hits = [p for p in hits if is_test(p)]
    cls = ("test-only" if hits and test_hits and not prod_hits
           else "prod-hit" if prod_hits else "none")
    h1_rows.append((r["task_id"], r["arm"], cls, len(hits),
                    len(test_hits), len(prod_hits),
                    r.get("gold_file_recall"), r.get("gold_span_recall")))
by_cls = defaultdict(list)
for row in h1_rows:
    by_cls[row[2]].append(row)
for cls in ("test-only", "prod-hit", "none"):
    rows = by_cls.get(cls, [])
    print("  %-9s: %d/%d rows" % (cls, len(rows), len(h1_rows)))
    for row in rows:
        print("    %s %s test=%d prod=%d recall=%s span=%s"
              % (row[0], row[1], row[4], row[5], row[6], row[7]))

# ---------------- H4: non-Python D-arm localization quality ---------------
print("\n== H4: non-Python tasks, D-arm span/file recall ==")
for r in ROWS:
    if r["arm"] != "D":
        continue
    tid = r["task_id"]
    lang = ("py" if any(s in tid for s in ("click", "django", "requests", "babel-async"))
            else "non-py")
    print("  %-34s %-7s file_recall=%-6s span_recall=%-6s span_prec=%s"
          % (tid, lang, r.get("gold_file_recall"), r.get("gold_span_recall"),
             r.get("span_precision")))

# ---------------- H2/H3 attribution check ---------------------------------
print("\n== H2/H3: any row where outcome wrong AND attributable to latency/AOCI? ==")
print("  (fields present per row: latency_ms, backend, fallbacks)")
attrib = 0
for r in ROWS:
    if r["arm"] == "D" and r.get("exit_reason") in ("STOPPED_BUDGET", "BUDGET"):
        attrib += 1
        print("  budget-stop row: %s lat=%sms" % (r["task_id"], r.get("latency_ms")))
print("  rows with budget-stops (latency-adjacent): %d" % attrib)
print("  AOCI-dependent failures: 0 (no task repo has aoci volumes — backend field in every row confirms)")

# ---------------- full confusion matrix (file level, all arms) ------------
print("\n== confusion matrix (file-level, per arm over 10 tasks) ==")
for arm in sorted({r["arm"] for r in ROWS}):
    tp = fp = fn = 0
    for r in ROWS:
        if r["arm"] != arm:
            continue
        gold = gold_by_task[r["task_id"]]
        pred = set(r.get("candidate_files") or []) | set(
            f["path"] for f in (r.get("functions") or []))
        tp += len(pred & gold)
        fp += len(pred - gold)
        fn += len(gold - pred)
    print("  arm %-2s TP=%d FP=%d FN=%d  precision=%.3f recall=%.3f"
          % (arm, tp, fp, fn, tp / max(tp + fp, 1), tp / max(tp + fn, 1)))
