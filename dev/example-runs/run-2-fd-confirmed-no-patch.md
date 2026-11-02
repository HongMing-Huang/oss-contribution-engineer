# Example Run 2 — sharkdp/fd: Investigation Only, CONFIRMED bug, still NO patch

Real run, 2026-10-03. Local clone `/tmp/oss-repos/fd` (shallow `main`,
HEAD `ce97e473ebaec49697c07daa50a7bc2b32f713d2`), built locally with cargo → `fd 10.5.0`.
Modes exercised: Repository Recon (1) → Issue Triage (2) → Investigation Only (4).
**No file in the repository was modified; nothing was published.**

## Repository Contribution Profile (abbreviated)

| Field | Value | Source |
|-------|-------|--------|
| project | fd, a simple, fast and user-friendly alternative to `find` | README |
| language | Rust (24 files) | repo_audit.py |
| build/test | cargo (`cargo test`), Makefile targets | Cargo.toml, Makefile |
| quality gates | rustfmt, clippy, CodeQL | repo_audit.py |
| docs | CONTRIBUTING.md, SECURITY.md, CHANGELOG.md | repo_audit.py |
| **AI policy (explicit)** | don't open generative-AI PRs unless you have reviewed and understood them yourself; you are responsible for license/patent compliance of generated code | CONTRIBUTING.md L15–21 |
| PR process | **open a ticket first**; code must compile and pass tests | CONTRIBUTING.md L10, L18 |
| history note | shallow clone limits git history — unshallow before history-based investigation | recon caveat |

The explicit AI policy is a textbook local-rules-override: stricter than the skill's
default (offer disclosure), so it binds.

## Target: sharkdp/fd#1919 — `--exclude` quirk with multiple `--search-path` (open, 5 comments)

### Dedupe/triage signals
- Maintainer **tmccombs already diagnosed the root cause** in comments, with a code link
  to `src/walk.rs` (first search path used as the override base).
- The fix is framed as an **unresolved design decision** (three non-ideal options; the
  maintainer rejects the thorough one as too large; no consensus).
- A candidate implementation exists: **PR #2000** (prefixes relative `--exclude` globs
  with `**/` when multiple roots are used), CI green.

### Investigation Only (verification against current main)

1. Code trace on HEAD `ce97e473`: `src/walk.rs` `build_overrides()` —
   `let first_path = &paths[0];` … `OverrideBuilder::new(first_path)` — all
   `--exclude` patterns are anchored to the **first search path only**. Diagnosis still
   accurate on current main (not already fixed).
2. Reproducer (adapted from the issue), run against the freshly built binary and
   witnessed in the evidence manifest (`.oss-contrib-evidence/artifacts/002/003`):

   ```
   fd --type file --search-path test --search-path test2 --exclude ghi/def
   → test2/ghi/def/myfile2.txt leaks            (defect)
   fd --type file --search-path test --search-path test2 --exclude ghi
   → only abc/def hits, correct                 (control)
   ```

   Matches the reporter's 10.4.2 output exactly; behavior identical on 10.5.0/main.

### Investigation Report conclusion: **CONFIRMED**

Expected: `--exclude 'ghi/def'` applies under every search root (reporter expectation,
maintainer-endorsed diagnosis). Observed: leaks under non-first roots. Root cause:
single-anchor `OverrideBuilder` in `build_overrides`. Evidence: code site + two witnessed
command artifacts. (The *behavioral* expectation ultimately needs a maintainer ruling —
see below.)

## Decision: **NO PATCH** — the gate that stops is not the Proof Gate

The bug is real, reproduced, and maintainer-acknowledged — yet the skill must not patch
it, for two independent reasons:

1. **NEEDS_MAINTAINER_DECISION**: the maintainer has laid out design options and none is
   chosen ("I agree none of these options sound ideal"). Implementing any of them would
   be answering a design question the maintainer explicitly left open. Per
   SKILL.md hard rule and maintainer-etiquette, features/semantics under active design
   discussion stop before implementation.
2. **PR_EXISTS**: PR #2000 is an open candidate implementation. Competing is forbidden
   absent an explicit maintainer invitation.

This is the second distinct no-patch shape: run 1 stopped at the DEDUPLICATE gate
before reproducing; run 2 reproduced successfully and *still* stops — because
"confirmed bug" ≠ "authorized to patch". Any contribution here would be a reply to the
open design thread (REMOTE_WRITE → requires explicit user authorization) or nothing.

## Gate outcome

`PROVE` gate passed (CONFIRMED with witnessed evidence) → classification
`NEEDS_MAINTAINER_DECISION` + `PR_EXISTS` → **stop before RED/PATCH**. No production
file touched; binary build + evidence artifacts are the only writes (outside the repo
tree except `.oss-contrib-evidence/`).
