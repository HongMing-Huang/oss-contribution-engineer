#!/usr/bin/env python3
"""v8_report.py — merge a bench JSONL into the ledger table (append-only)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", required=True)
    ap.add_argument("--ledger", default=str(Path(__file__).parent / "EXPERIMENT-LEDGER.md"))
    ap.add_argument("--round-name", required=True)
    args = ap.parse_args()
    rows = [json.loads(l) for l in Path(args.jsonl).read_text().splitlines() if l.strip()]
    lines = ["", "### %s" % args.round_name, "",
             "| task | arm | file_recall | span_recall | span_prec | ctx_tokens | ops | lat_ms | backend |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["task_id"], r["arm"], r.get("gold_file_recall"),
            r.get("gold_span_recall"), r.get("span_precision"),
            r.get("context_tokens"), r.get("ops"), r.get("latency_ms"),
            r.get("backend") or "-"))
    text = Path(args.ledger).read_text()
    marker = "(merged automatically from the JSONL by `v8_report.py`)"
    text = text.replace(marker, marker + "\n".join([""] + lines))
    Path(args.ledger).write_text(text)
    print("ledger updated: %d rows → %s" % (len(rows), args.ledger))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
