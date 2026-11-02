#!/usr/bin/env python3
"""v8_freeze_tasks.py — freeze the V8 benchmark task set.

For each task: resolve base SHA (merge commit's first parent — the investigation
workspace is checked out there, so the fixing commit is NOT visible to any arm),
extract gold production files and gold spans (hunk line ranges on the NEW file
side) from the local blobless clone's history, and write tasks.json.

The task query is the real issue/PR title (+ a body excerpt). Gold is derived
ONLY from git metadata here, never shown to the investigation arms.

Usage: python3 v8_freeze_tasks.py --out ../tasks.json   (relative to this dir)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE / "work"

# (task_id, repo_slug, pr_number, merge_sha, task_type, query, body_excerpt)
SPECS = [
    ("click-3802-keyinterrupt-race", "pallets/click", 3818,
     "00f257bb8e714064bea16425007543bbc0800445", "bug_report",
     "KeyboardInterrupt during click.prompt() can race",
     "When a user uses Ctrl-C during click.prompt(), this may cause an unhandled "
     "exception. Seen during CI on an Ubuntu 22.04 arm github runner. This is "
     "likely to be a race that doesn't pop up every time. main() should follow "
     "the pager policy: a late interrupt must not replace the intended outcome."),
    ("click-3805-sentinel-deepcopy", "pallets/click", 3805,
     "4295457ddc7b5ca9a733d59ca40d9651b02b9b1d", "bug_report",
     "copy deepcopy and pickle of Sentinel members fail",
     "On Python 3.10 Enum has no __deepcopy__. Now that every parameter has a "
     "sentinel, copy.deepcopy() of any Option, Argument or Command fails on "
     "Python 3.10, and pickle fails on every Python version."),
    ("click-3865-short-help-abbrev", "pallets/click", 3865,
     "70689853e39c30e36eb0d83d586cc914a74db9d3", "behavior_regression",
     "short help abbreviation ends prematurely on abbreviations like vs or e.g.",
     "_make_default_short_help ends the shortened help at 'vs.' or 'e.g.' because "
     "the sentence-boundary heuristic counts these as sentence ends."),
    ("django-37377-jsonfield-in", "django/django", 22051,
     "fabce94374e166e80e2643db8b85d1e3442427bf", "bug_report",
     "JSONField __in lookup crash and incorrect results for bare Value() primitives",
     "Filtering a JSONField with __in and bare Value() primitives crashes or "
     "returns incorrect results instead of comparing the JSON values."),
    ("vite-safemodulepaths", "vitejs/vite", 23656,
     "c3e06f92e969952466b4e2f5801e85e1e00cd905", "security_regression",
     "server stores ids to safeModulePaths rather than URLs",
     "The dev server's fs-allow safeModulePaths check compares URLs where it "
     "should compare module ids, so some safe modules are rejected or unsafe "
     "paths slip through the check."),
    ("clap-zsh-escape", "clap-rs/clap", 6526,
     "34430008f695f43d37364ce47cce5156febb1c52", "bug_report",
     "clap_complete zsh completion escapes values incorrectly",
     "The generated zsh completion script does not escape argument values "
     "correctly, breaking completions for values containing special characters."),
    ("gin-4818-getvalue-panic", "gin-gonic/gin", 4819,
     "3b08cd7235bd5ad2f055aa9e38135f111f6c5926", "stack_trace",
     "Panic: slice bounds out of range in getValue with HandleMethodNotAllowed enabled",
     "With HandleMethodNotAllowed = true, gin can panic during route matching: "
     "runtime error: slice bounds out of range [:x+1] with capacity x. The tree "
     "walk must reset the skipped-nodes stack on entry."),
    ("babel-asynciterator-throw", "babel/babel", 18283,
     "3cf71caa7b060d211a84bd79a41e733374745322", "behavior_regression",
     "asyncIterator helper forwards .throw() to .return() instead of .throw()",
     "The asyncIterator helper forwards .throw() calls on a yield* delegate to "
     "the inner iterator's .return() method instead of its .throw() method when "
     "the inner iterator is a sync iterator."),
]

PROD_HINTS = (".py", ".go", ".rs", ".ts", ".js", ".mjs", ".cjs", ".tsx", ".jsx")
TEST_HINTS = ("test", "spec", "fixtures")


def git(repo: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True, shell=False)
    if p.returncode != 0:
        raise SystemExit("git %s failed in %s: %s" % (args[0], repo, p.stderr[:300]))
    return p.stdout


def is_prod(path: str) -> bool:
    return path.endswith(PROD_HINTS) and not any(h in path.lower() for h in TEST_HINTS)


def gold(repo: Path, merge: str) -> tuple[list[str], list[str], dict]:
    # diff against the FIRST parent explicitly: squash merges (1 parent) and true
    # merge commits (2 parents) both yield the PR's actual change this way,
    # whereas bare `git show <merge>` prints an empty combined diff for
    # conflict-free merges.
    base_rev = merge + "^1"
    names = [ln.strip() for ln in git(repo, "diff", "--name-only", base_rev,
                                      merge).splitlines() if ln.strip()]
    prod = [n for n in names if is_prod(n)]
    tests = [n for n in names if n not in prod]
    # gold spans: NEW-side hunk line ranges for prod files
    spans: dict[str, list[tuple[int, int]]] = {}
    diff = git(repo, "diff", "--unified=0", base_rev, merge, "--", *prod) if prod else ""
    cur = None
    for line in diff.splitlines():
        m = re.match(r"^\+\+\+ b/(.+)$", line)
        if m:
            cur = m.group(1)
            continue
        hm = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if hm and cur:
            start = int(hm.group(1))
            count = int(hm.group(2)) if hm.group(2) else 1
            spans.setdefault(cur, []).append([start, start + max(count, 1) - 1])
    return prod, tests, spans


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "tasks.json"))
    args = ap.parse_args()
    tasks = []
    for tid, slug, pr, merge, ttype, query, body in SPECS:
        repo = WORK / slug.split("/")[1]
        if not repo.exists():
            print("SKIP %s — clone missing" % tid, file=sys.stderr)
            continue
        base = git(repo, "rev-parse", merge + "^1").strip()
        prod, tests, spans = gold(repo, merge)
        short = merge[:10]
        tasks.append({
            "task_id": tid, "repo_slug": slug, "repo_dir": str(repo),
            "pr_number": pr, "merge_sha": merge, "merge_short": short,
            "base_sha": base, "task_type": ttype,
            "query": query, "body_excerpt": body,
            "gold_prod_files": prod, "gold_test_files": tests,
            "gold_spans": spans,
            "worktree": str(HERE / "work" / ("%s@%s" % (slug.split("/")[1], base[:10]))),
        })
        print("frozen %s: base=%s gold_prod=%d files, %d span groups"
              % (tid, base[:10], len(prod), len(spans)))
    Path(args.out).write_text(json.dumps(tasks, indent=2))
    print("tasks: %d → %s" % (len(tasks), args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
