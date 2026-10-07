#!/usr/bin/env python3
"""v9_freeze_tasks.py — V9 §1: freeze benchmark tasks from PRE-FIX source material.

Every task's prompt text is captured VERBATIM from information published before
the fixing patch:
  - level=ISSUE: the linked issue's title + body (found via "fixes #N" in the
    PR body, or explicit issue number)
  - level=PR_TITLE: when no issue exists — the PR title only (the PR body is
    EXCLUDED because fixers describe their own fix there)

Recorded per task: source_url, source_timestamp, captured raw text, capture
digest (sha256), fix commit, base commit (merge^1). A leakage check then
verifies the task query contains nothing beyond the captured source: any token
of the query that does not occur in the raw source text is a freeze bug.

The manually authored V8 task summaries are RETIRED (leakage risk: e.g. the old
click-3865 summary named the function and the 'vs.'/'e.g.' mechanism — facts
from the fixing diff).

Usage: python3 v9_freeze_tasks.py [--with-new-blind]  (writes v9_tasks.json)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE / "work"

# (task_id, repo_slug, pr_number, issue_number|None, merge_sha, task_type)
SPECS = [
    ("v9-click-3802-interrupt-race", "pallets/click", 3818, 3802,
     "00f257bb8e714064bea16425007543bbc0800445", "stack_trace"),
    ("v9-click-3805-sentinel-copy", "pallets/click", 3805, None,
     "4295457ddc7b5ca9a733d59ca40d9651b02b9b1d", "bug_report"),
    ("v9-click-3865-short-help", "pallets/click", 3865, None,
     "70689853e39c30e36eb0d83d586cc914a74db9d3", "behavior_regression"),
    ("v9-django-37377-jsonfield-in", "django/django", 22051, 37377,
     "fabce94374e166e80e2643db8b85d1e3442427bf", "bug_report"),
    ("v9-vite-safemodulepaths", "vitejs/vite", 23656, None,
     "c3e06f92e969952466b4e2f5801e85e1e00cd905", "security_regression"),
    ("v9-clap-zsh-escape", "clap-rs/clap", 6526, None,
     "34430008f695f43d37364ce47cce5156febb1c52", "bug_report"),
    ("v9-gin-4818-getvalue-panic", "gin-gonic/gin", 4819, 4818,
     "3b08cd7235bd5ad2f055aa9e38135f111f6c5926", "stack_trace"),
    ("v9-babel-asynciterator-throw", "babel/babel", 18283, None,
     "3cf71caa7b060d211a84bd79a41e733374745322", "behavior_regression"),
]

NEW_BLIND = [
    ("v9-requests-encode-files", "psf/requests", 7502, None,
     None, "bug_report"),
    ("v9-cobra-completions-osargs", "spf13/cobra", 2356, None,
     None, "behavior_regression"),
]

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def gh_json(*args: str) -> dict:
    p = subprocess.run(["/usr/bin/env", "gh", *args],
                       capture_output=True, text=True, shell=False)
    if p.returncode != 0:
        raise SystemExit("gh %s failed: %s" % (args[0], p.stderr[:200]))
    return json.loads(p.stdout)


def gh_text(*args: str) -> str:
    p = subprocess.run(["/usr/bin/env", "gh", *args],
                       capture_output=True, text=True, shell=False)
    return p.stdout if p.returncode == 0 else ""


def git(repo: Path, *args: str) -> str:
    p = subprocess.run(["/usr/bin/env", "git", "-C", str(repo), *args],
                       capture_output=True, text=True, shell=False)
    if p.returncode != 0:
        raise SystemExit("git %s failed: %s" % (args[0], p.stderr[:200]))
    return p.stdout


def detect_issue(repo_slug: str, pr: int) -> int | None:
    body = gh_json("pr", "view", str(pr), "--repo", repo_slug,
                   "--json", "body").get("body") or ""
    m = re.search(r"[fF]ix(?:e[sd]|ing)?\s+#(\d+)", body) or \
        re.search(r"[cC]lose[sd]?\s+#(\d+)", body)
    return int(m.group(1)) if m else None


FETCH_HOST_ALLOWLIST = {"code.djangoproject.com"}


def fetch_allowed_https(url: str, timeout: int = 30) -> str:
    """SSRF-bounded fetch: https only, host allowlist, resolved IP must be
    public unicast, redirects rejected."""
    import ipaddress
    import socket
    import urllib.request
    from urllib.parse import urlsplit

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in FETCH_HOST_ALLOWLIST:
        raise ValueError("fetch rejected: scheme/host not allowed")
    for info in socket.getaddrinfo(parts.hostname, 443, proto=socket.IPPROTO_TCP):
        ip_str = str(ipaddress.ip_address(info[4][0]))
        if ip_str.lower().startswith("::ffff:"):
            # mapped-v4, including this proxy's non-standard ::ffff:0:x:y form:
            # the last two 16-bit groups always carry the IPv4 address
            groups = ip_str.split(":")[-2:]
            v4 = (int(groups[0], 16) << 16) | int(groups[1], 16)
            ip = ipaddress.ip_address(v4)
        else:
            ip = ipaddress.ip_address(ip_str)
        if ip in ipaddress.ip_network("198.18.0.0/15"):
            # 198.18.0.0/15 (benchmark-reserved) is this host's TUN proxy
            # fake-IP pool: every DNS answer here looks like this. Allowed
            # explicitly because the real egress is the tunnel; all other
            # private/reserved ranges stay rejected.
            continue
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            raise ValueError("fetch rejected: %s resolves to %s" % (parts.hostname, ip))
    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(url, headers={"User-Agent": "v9-freeze"})
    with opener.open(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise ValueError("fetch rejected: status %s" % resp.status)
        return resp.read().decode("utf-8", "replace")


    try:
        return capture_source_inner(slug, pr, issue)
    except Exception as exc:
        # honest degradation: fall back to PR_TITLE and record why
        d = gh_json("pr", "view", str(pr), "--repo", slug,
                    "--json", "title,url,createdAt")
        return {"level": "PR_TITLE",
                "source_url": d.get("url", ""),
                "source_timestamp": d.get("createdAt", ""),
                "raw_text": "TITLE: %s\n" % d.get("title", ""),
                "fallback_reason": str(exc)[:200]}


def capture_source(repo_slug: str, pr: int, issue: int | None) -> dict:
    try:
        return capture_source_inner(repo_slug, pr, issue)
    except Exception as exc:
        # honest degradation: fall back to PR_TITLE and record why
        d = gh_json("pr", "view", str(pr), "--repo", repo_slug,
                    "--json", "title,url,createdAt")
        return {"level": "PR_TITLE",
                "source_url": d.get("url", ""),
                "source_timestamp": d.get("createdAt", ""),
                "raw_text": "TITLE: %s\n" % d.get("title", ""),
                "fallback_reason": str(exc)[:200]}


def capture_source_inner(repo_slug: str, pr: int, issue: int | None) -> dict:
    """Capture the pre-fix source text verbatim (level ISSUE preferred)."""
    if repo_slug == "django/django" and issue:
        # django runs Trac, not GitHub issues; the ticket page has a plain-text
        # rendering (public, https, allowlisted host, SSRF-bounded fetch)
        url = "https://code.djangoproject.com/ticket/%d?format=txt" % issue
        raw = fetch_allowed_https(url)
        m = re.search(r"^\s*Summary:\s*(.+)$", raw, re.M)
        title = (m.group(1).strip() if m else "ticket %d" % issue)
        return {"level": "ISSUE", "source_url": url.split("?")[0],
                "source_timestamp": "", "raw_text": "TITLE: %s\n\n%s" % (title, raw)}
    if issue:
        d = gh_json("issue", "view", str(issue), "--repo", repo_slug,
                    "--json", "title,body,url,createdAt")
        raw = "TITLE: %s\n\n%s" % (d.get("title", ""), d.get("body") or "")
        return {"level": "ISSUE", "source_url": d.get("url", ""),
                "source_timestamp": d.get("createdAt", ""),
                "raw_text": raw}
    d = gh_json("pr", "view", str(pr), "--repo", repo_slug,
                "--json", "title,url,createdAt")
    raw = "TITLE: %s\n" % d.get("title", "")
    return {"level": "PR_TITLE", "source_url": d.get("url", ""),
            "source_timestamp": d.get("createdAt", ""),
            "raw_text": raw}


def gold(repo: Path, merge: str) -> tuple[list[str], list[str], dict]:
    base_rev = merge + "^1"
    names = [ln.strip() for ln in git(repo, "diff", "--name-only", base_rev,
                                      merge).splitlines() if ln.strip()]
    prod = [n for n in names if n.endswith(
        (".py", ".go", ".rs", ".ts", ".js", ".mjs", ".cjs", ".tsx", ".jsx"))
        and not any(h in n.lower() for h in ("test", "spec", "fixtures"))]
    spans: dict[str, list[list[int]]] = {}
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
    tests = [n for n in names if n not in prod]
    return prod, tests, spans


def leakage_check(task_text: str, raw_text: str) -> dict:
    """The task text must be a verbatim subset of the captured source.

    Any query token that does not occur in the raw source is a freeze bug —
    it means a human (or an LLM) added knowledge the source did not contain.
    Additionally records which fix-diff-added identifiers appear in the source
    itself (legitimate blind hints the issue already disclosed)."""
    task_tokens = set(TOKEN_RE.findall(task_text))
    source_tokens = set(TOKEN_RE.findall(raw_text))
    non_source = sorted(t for t in task_tokens if t not in source_tokens)
    return {"task_tokens_not_in_source": non_source,
            "leak_free": not non_source}


def diff_added_identifiers(repo: Path, merge: str) -> set[str]:
    base_rev = merge + "^1"
    diff = git(repo, "diff", base_rev, merge, "--unified=0")
    toks: set[str] = set()
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            toks.update(TOKEN_RE.findall(line))
    return toks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-new-blind", action="store_true")
    ap.add_argument("--out", default=str(HERE / "v9_tasks.json"))
    args = ap.parse_args()
    specs = list(SPECS) + (NEW_BLIND if args.with_new_blind else [])
    tasks, frozen = [], 0
    for tid, slug, pr, issue, merge, ttype in specs:
        name = slug.split("/")[1]
        repo = WORK / name
        if not repo.exists():
            print("SKIP %s — clone missing" % tid, file=sys.stderr)
            continue
        prd = gh_json("pr", "view", str(pr), "--repo", slug,
                      "--json", "mergeCommit")
        merge = (prd.get("mergeCommit") or {}).get("oid") or merge
        if issue is None and tid.startswith("v9-"):
            issue = detect_issue(slug, pr)
        src = capture_source(slug, pr, issue)
        # query = the source title VERBATIM; body excerpt = raw body head VERBATIM
        raw_title = src["raw_text"].split("\n", 1)[0].replace("TITLE: ", "", 1)
        raw_body = src["raw_text"].split("\n\n", 1)[1] if "\n\n" in src["raw_text"] else ""
        body_head = raw_body[:600]
        if len(raw_body) > 600 and not raw_body[600:].startswith((" ", "\n", "\r", ".", ",", ")", "]")):
            # cut at a word boundary so the excerpt never contains a truncated
            # token (which would falsely fail the leak check)
            body_head = body_head.rsplit(maxsplit=1)[0] if " " in body_head else body_head
        base = git(repo, "rev-parse", merge + "^1").strip()
        prod, tests, spans = gold(repo, merge)
        task = {
            "task_id": tid, "repo_slug": slug, "repo_dir": str(repo),
            "pr_number": pr, "issue_number": issue, "merge_sha": merge,
            "base_sha": base, "task_type": ttype,
            "source_level": src["level"],
            "source_url": src["source_url"],
            "source_timestamp": src["source_timestamp"],
            "raw_text": src["raw_text"],
            "capture_digest": hashlib.sha256(src["raw_text"].encode()).hexdigest(),
            "query": raw_title,
            "body_excerpt": body_head,
            "gold_prod_files": prod, "gold_test_files": tests,
            "gold_spans": spans,
            "worktree": str(WORK / ("%s@%s" % (name, base[:10]))),
        }
        leak = leakage_check(task["query"] + " " + task["body_excerpt"],
                             src["raw_text"])
        task["freeze_leak_check"] = leak
        if merge:
            added = diff_added_identifiers(repo, merge)
            src_tokens = set(TOKEN_RE.findall(src["raw_text"]))
            task["issue_disclosed_fix_identifiers"] = sorted(
                t for t in (added & src_tokens) if len(t) >= 4)[:24]
        tasks.append(task)
        frozen += 1
        print("frozen %-34s level=%-8s leak_free=%s disclosed_hints=%d" % (
            tid, src["level"], leak["leak_free"],
            len(task.get("issue_disclosed_fix_identifiers", []))))
        if not leak["leak_free"]:
            print("  !! non-source tokens: %s" % leak["task_tokens_not_in_source"])
    Path(args.out).write_text(json.dumps(tasks, indent=2))
    print("tasks: %d → %s (%d leak-free)" % (
        len(tasks), args.out, sum(1 for t in tasks
                                  if t["freeze_leak_check"]["leak_free"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
