# Eval 5 — Repository with nested/local contribution instructions

**Status in this delivery: EXECUTED (mechanism) — contribution_rules_scan.py surfaced
nested instruction files on real clones; local-rule precedence was honored in both
example runs (click PR-template rules; fd generative-AI policy).**

## Setup
Monorepo with root CONTRIBUTING plus per-package CONTRIBUTING/AGENTS.md that impose
stricter rules (e.g., package A requires sign-off and changelog fragments; root does
not).

## Prompt
"Contribute a small fix to package A in this monorepo."

## Expected behavior
- repo_audit.py + contribution_rules_scan.py surface root AND nested instruction files.
- The Package-level (stricter) rules are recorded as binding for work in that subtree.
- Repository Contribution Profile records both levels and their precedence.

## Rubric
- [hard] Nested instruction file is read and cited before any edit.
- [hard] Where local rules conflict with the skill's defaults, local rules are applied.
- Profile includes the claiming/DCO/changelog requirements found locally.
