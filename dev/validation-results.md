# Validation Results — scripts and skill mechanics

All executions below were really run in this workspace on 2026-10-03. This is
deliverable **7** (skill validation results). Provenance rule: nothing here is claimed
without a recorded execution or artifact.

## 1. Static conformance

| Check | Result | Evidence |
|-------|--------|----------|
| `python3 -m py_compile` all 6 scripts | OK (6/6) | shell run, 2026-10-03 |
| SKILL.md frontmatter vs agentskills.io rules: name matches directory, lowercase-hyphen, ≤64 chars; description ≤1024 chars (846), states what+when+anti-trigger; body 237→~245 lines (<500) | OK | inline Python check, 2026-10-03 |
| Frontmatter uses only spec fields (`name`, `description`, `license`, `compatibility`, `metadata`); `allowed-tools` deliberately absent (experimental per spec) | OK | manual inspection vs spec text fetched from agentskills.io/specification |

## 2. Deterministic collectors — executed against real repositories

| Script | Target | Result | Evidence |
|--------|--------|--------|----------|
| repo_audit.py | /tmp/oss-repos/click (shallow clone) | Detected Python(88), uv, pytest, GitHub Actions, pre-commit/editorconfig, CONTRIBUTING + PR/issue templates + RELEASING/CHANGELOG; surfaced pyproject.toml/uv.lock as command sources | transcript in example run 1 |
| repo_audit.py | /tmp/oss-repos/fd | Detected Rust(24), cargo+make, cargo test, GitHub Actions, rustfmt, clippy+CodeQL, CONTRIBUTING/SECURITY/CHANGELOG | transcript in example run 2 |
| repo_audit.py | scratch fixture | languages/package manager/docs detected correctly; JSON mode verified | shell transcript |
| contribution_rules_scan.py | click | Excerpted binding rules: PR template (ticket first; tests that fail without the change; CHANGES entry; fixes #N), docs/contributing.md (stress/random tox envs, no-ternary style, no unnecessary deps, 80-col Markdown); flagged AI-instruction absence | example run 1 profile |
| contribution_rules_scan.py | fd | Surfaced **explicit generative-AI policy** (review yourself; license/patent responsibility) at CONTRIBUTING.md L15–21, ticket-first rule, compile+test requirement | example run 2 profile |
| contribution_rules_scan.py | skill folder itself | Keyword excerpting works on non-OSS docs; tags rendered | shell transcript |
| duplicate_work_scan.py (commands + parse-issue) | pallets/click#3362 | Capture commands printed; captured via `gh` (issue + 2 timeline pages); parsed: 5 open PR references (1 upstream #3782, 4 fork/AI-agent), 6 fork "merged in own repo" PRs, 20 referencing commits; dedupe hints emitted | /tmp capture files + report in example run 1 |
| duplicate_work_scan.py (JSON robustness) | malformed input paths | exits 3/4 with explicit stderr (missing file / not JSON) | code paths exercised in earlier interim run (parse-issue on arrays enforced) |

Honest notes: (a) an initial design had the script shell out to `gh` itself; the
workspace security hook (Mimosa) rejects variable-argv subprocess patterns, so the
final design is parse-only — better for provenance and vendor-neutrality; the
"merged" semantics for cross-repo references were relabeled "merged in own repo"
after the first real run showed the ambiguity.

## 3. RED→GREEN drill (fixture; the anti-fabrication core)

Fixture: `eval/fixtures/divide-fixture/` (bug: `divide(1,0)` returns `None`; fix:
raise `ZeroDivisionError`). Repository `/tmp/oss-skill-scratch`, HEAD `1749b59`.
Commands recorded via `evidence_manifest.py record` (each artifact sha256-stamped,
git HEAD captured):

| # | Purpose | Result | Note |
|---|---------|--------|------|
| 1 | LEVEL 0 baseline (original suite, pre-regression-test) | PASS | artifact 001, sha c1ee481c… |
| 2 | RED on unmodified upstream (`--expect-fail`) | PASS (expected failure — RED proof) | artifact 002: genuine `AssertionError: divide(1, 0) returned instead of raising ZeroDivisionError` |
| 3 | GREEN after minimal fix | PASS | artifact 003 |
| 4 | REGRESSION: full suite | PASS | artifact 004 |
| 5 | LEVEL 7 integration | UNAVAILABLE (reason recorded) | non-execution entry |

`validation_report.py` rendered: 4 executed / 4 passed / 0 failed / 1 not executed,
conclusion **INCOMPLETE — 1 validation step(s) not executed** (exit 4) — skipped work
stays visible, never collapsed into PASS.

### Failures caught by this validation (valuable, recorded honestly)

1. **Dead regression test caught by the RED gate.** The first fixture bug (`1/0`
   raising natively in Python) made the regression test pass with *and* without the
   fix; the RED gate correctly refused the fake proof ("test does not exercise the
   defect"). Fixture bug replaced with a real behavioral defect (`return None`).
2. **Fake GREEN caught by witnessing.** A tool-state glitch left the fix off disk while
   the transcript suggested otherwise; recorded artifacts showed byte-identical output
   for RED and GREEN (sha 81d15a6b…), exposing the bogus GREEN. This is exactly the
   fabrication the manifest exists to prevent.
3. **Tooling gap fixed: `--expect-fail`.** A RED FAIL counted as a validation failure
   (report concluded FAILED). Added `--expect-fail` so expected-failure evidence is
   classified as RED proof, and an unexpected exit 0 becomes the FAIL.
4. **Scope-audit noise fixed.** The audit flagged the evidence dir and `__pycache__` as
   unintended drift; tooling outputs are now excluded from the untracked listing.

## 4. diff_scope_check.py — executed with injected drift

Scratch repo, intended = `calc.py,tests/test_calc.py`, actual working tree also
contained: whitespace-only README edit, `package.json` manifest change, untracked
helper file.

Result (exit 1): README flagged **formatting-only** (via `git diff -w
--ignore-blank-lines`), package.json flagged as dependency-surface change, all three
extras listed as UNINTENDED, conclusion **SCOPE_FINDINGS**. After the drill's clean
state: exactly 2 intended files → **WITHIN_SCOPE** (exit 0).

## 5. Evidence chain integrity

`evidence_manifest.py verify <id>` recomputed artifact sha256 → match. Manifest entries
carry: timestamp (UTC), command argv, exit code, duration, artifact path + sha, git
HEAD at run time, cwd, python/platform. `record-skip` refuses blank reasons.

## 6. Environment note

Windows/`user concurrency`-specific paths were not exercised (macOS arm64, Python
3.14.2, git 2.x, gh CLI authenticated). Scripts are stdlib-only and avoid OS-specific
calls beyond `pathlib`/`subprocess` semantics that are POSIX-and-Windows safe.
