# Repository Recon

Recon precedes every edit and every recommendation. Its product is the **Repository
Contribution Profile** (template: assets/repository-recon-report.md).

## Method

1. Run the deterministic collectors from the repository root:

   ```bash
   python3 <skill-dir>/scripts/repo_audit.py .
   python3 <skill-dir>/scripts/contribution_rules_scan.py .
   ```

2. Read every instruction file the scan surfaces, plus anything it cannot know about
   (README badges, docs/ trees, .github/ contents, Makefile/package-script targets).
3. Verify commands by reading the build manifest and CI workflow they come from. A
   command that exists in CI but not locally is a UNAVAILABLE, not a PASS.
4. Write the profile. Only then proceed — and treat profile conflicts as precedence:
   **repository-local rules override this skill's defaults.**

## Files to search for and read (when present)

- Root docs: `README*`, `CONTRIBUTING*`, `CODE_OF_CONDUCT*`, `SECURITY*`,
  `DEVELOPMENT*`, `HACKING*`, `MAINTAINERS*`, `GOVERNANCE*`, `RELEASING*`, `CHANGELOG*`
- Ownership: `CODEOWNERS`, `OWNERS`, `.github/CODEOWNERS`, per-directory `OWNERS`
- AI instructions: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`,
  `.cursor/rules*`, `.cursorrules`, `.claude/` — read and obey these; they are binding
- Nested copies: CONTRIBUTING/AGENTS files may exist in subdirectories (monorepos,
  per-package rules) — `contribution_rules_scan.py` finds them; deeper nesting matters
  when working in that subtree
- Templates: `.github/PULL_REQUEST_TEMPLATE*`, `.github/ISSUE_TEMPLATE/*`,
  `.gitea/`, `docs/pull_request_template*`
- CI: `.github/workflows/*`, `.gitlab-ci.yml`, `.circleci/config.yml`,
  `azure-pipelines.yml`, `Jenkinsfile`, `.drone.yml`, `.woodpecker*`
- Build/test/lint configuration: manifests and lockfiles, formatter/linter/typechecker
  configs (see `repo_audit.py` detection table), pre-commit configs
- Release process: changesets, towncrier fragments, release notes directories

## Repository Contribution Profile (required fields)

- **Project purpose** — one sentence, from the README, in your own words
- **Repository structure** — where the important code, tests, and docs live
- **Contribution process** — PR vs mailing list, forking model, base branch, review path
- **Build/test environment** — language/runtime versions, build system, package manager,
  install steps, env vars, anything requiring credentials or hardware
- **Commands** — test / focused test / lint / format check / typecheck / static analysis /
  build / integration, each annotated with its source file
- **Coding conventions** — style guide, formatter enforcement, comment/doc conventions,
  commit message convention (Conventional Commits? sign-off? issue refs?)
- **Claiming process** — assignment expected? "comment to claim"? offers welcome/needs-help labels?
- **DCO / CLA / sign-off requirements**
- **Changelog requirements** — changesets/towncrier/CHANGES file edits required?
- **AI contribution policy** — explicit disclosure? bans? AGENTS.md rules
- **Maintainer discovery** — CODEOWNERS, MAINTAINERS file, `gh api` org members
- **Risks** — flaky suites, slow builds, secrets needed, areas under active rework

## Recon anti-patterns

- Guessing the test command because a common framework is detected — read the manifest.
- Skipping SECURITY.md because no security work is planned — it matters when a hunt
  finds something sensitive.
- Treating a stale README as truth when AGENTS.md or CI disagrees — newer, enforced
  sources win.
- Running heavy builds during READ_ONLY recon when a manifest read would answer the
  question.
